"""Market data fetcher with fallback strategy."""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import yfinance as yf
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.lib.api_client import APIClient
from src.lib.api_models import validate_alpha_vantage_response
from src.lib.cache import CacheManager
from src.lib.config import API_RATE_LIMIT_DELAY
from src.lib.db import db_session
from src.lib.quota_tracker import QuotaTracker
from src.models.market_data import MarketData

logger = logging.getLogger(__name__)


class MarketDataFetcher:
    """Fetches market data from APIs with fallback strategy."""

    # Class-level cache shared across instances (persists between CLI calls)
    _price_cache: dict[str, tuple[float, datetime]] = {}

    def __init__(self) -> None:
        """Initialize market data fetcher."""
        self.api_client = APIClient()
        self.cache = CacheManager()
        self.alpha_vantage_key = os.getenv("ALPHA_VANTAGE_API_KEY", "")

        if not self.alpha_vantage_key:
            logger.warning(
                "ALPHA_VANTAGE_API_KEY not set. Will use Yahoo Finance and cache fallbacks only. "
                "For better data quality, set: export ALPHA_VANTAGE_API_KEY=your-key-here"
            )

        self.request_delay = API_RATE_LIMIT_DELAY  # Seconds between API requests (rate limiting)
        # Alpha Vantage free tier: 25 requests/day, 5 per minute
        self.quota_tracker = QuotaTracker(
            api_name="alpha_vantage", daily_limit=25, per_minute_limit=5
        )

    async def fetch_daily_data(self, ticker: str) -> Optional[dict[str, Any]]:
        """
        Fetch daily market data for a ticker with fallback strategy.

        Strategy (optimized to preserve Alpha Vantage quota):
        1. Try Yahoo Finance (primary - unlimited, free)
        2. Try Alpha Vantage (fallback - 25 requests/day limit)
        3. Try cache (if APIs fail)

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with market data or None if all sources fail
        """
        # Try Yahoo Finance first (unlimited, free)
        try:
            data = await self._fetch_yahoo_finance(ticker)
            if data:
                logger.info(f"Fetched {ticker} from Yahoo Finance")
                return data
        except Exception as e:
            logger.warning(f"Yahoo Finance failed for {ticker}: {e}")

        # Fallback to Alpha Vantage (preserve quota for fundamentals)
        try:
            data = await self._fetch_alpha_vantage(ticker)
            if data:
                logger.info(f"Fetched {ticker} from Alpha Vantage (fallback)")
                return data
        except Exception as e:
            logger.warning(f"Alpha Vantage failed for {ticker}: {e}")

        # Try cache as last resort
        cached = self.cache.get("market_data", ticker, ttl_minutes=1440)  # 24 hours
        if cached:
            logger.info(f"Using cached data for {ticker}")
            return cached

        return None

    async def _fetch_alpha_vantage(self, ticker: str) -> Optional[dict[str, Any]]:
        """
        Fetch data from Alpha Vantage API.

        Args:
            ticker: Stock ticker

        Returns:
            Market data dict or None
        """
        if not self.alpha_vantage_key:
            return None

        # Check cache first (15-minute TTL)
        cached = self.cache.get("alpha_vantage", ticker)
        if cached:
            return cached

        # Check quota before making API request
        if not self.quota_tracker.can_make_request():
            quota_info = self.quota_tracker.get_remaining_quota()
            logger.warning(
                f"Alpha Vantage quota exceeded: "
                f"{quota_info['daily_used']}/{quota_info['daily_limit']} daily"
            )
            return None

        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": ticker,
            "apikey": self.alpha_vantage_key,
            "outputsize": "compact",
        }

        try:
            async with self.api_client as client:
                response = await client.get(url, params=params)

            # Record successful request
            self.quota_tracker.record_request()

            # Validate response with Pydantic
            try:
                validated_response = validate_alpha_vantage_response(response)
            except ValidationError as e:
                logger.error(f"Alpha Vantage response validation failed: {e}")
                return None

            time_series = validated_response.time_series
            if not time_series:
                return None

            # Return ALL historical data (for storing in DB)
            # But also identify the latest for caching
            latest_date = max(time_series.keys())

            # Build result with all historical data
            historical_data = []
            for date_str, data_point in time_series.items():
                historical_data.append(
                    {
                        "ticker": ticker,
                        "timestamp": date_str,
                        "open": float(data_point.open),
                        "high": float(data_point.high),
                        "low": float(data_point.low),
                        "close": float(data_point.close),
                        "volume": int(data_point.volume),
                        "source": "alpha_vantage",
                        "is_latest": date_str == latest_date,
                    }
                )

            # Cache the latest data point
            latest_data = next(d for d in historical_data if d["is_latest"])
            self.cache.set("alpha_vantage", ticker, latest_data)

            # Return all historical data for database storage
            return {"historical": historical_data, "latest": latest_data}

        except ValueError as e:
            # API errors from validation
            logger.error(f"Alpha Vantage API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Alpha Vantage fetch failed: {e}")
            return None

    async def _fetch_yahoo_finance(self, ticker: str) -> Optional[dict[str, Any]]:
        """
        Fetch historical data from Yahoo Finance using yfinance.

        Args:
            ticker: Stock ticker

        Returns:
            Market data dict with historical data or None
        """
        # Check cache first
        cached = self.cache.get("yahoo_finance", ticker)
        if cached:
            return cached

        try:
            # Import yfinance only when needed
            import yfinance as yf

            stock = yf.Ticker(ticker)
            # Fetch 6 months of historical data (enough for technical analysis)
            hist = stock.history(period="6mo")

            if hist.empty:
                return None

            # Get latest date
            latest_date = hist.index[-1]

            # Build historical data list
            historical_data = []
            for date, row in hist.iterrows():
                date_str = date.strftime("%Y-%m-%d")
                historical_data.append(
                    {
                        "ticker": ticker,
                        "timestamp": date_str,
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row["Volume"]),
                        "source": "yahoo_finance",
                        "is_latest": date == latest_date,
                    }
                )

            # Cache the latest data point
            latest_data = next(d for d in historical_data if d["is_latest"])
            self.cache.set("yahoo_finance", ticker, latest_data)

            # Return all historical data for database storage
            return {"historical": historical_data, "latest": latest_data}

        except ImportError:
            logger.error("yfinance not installed. Install with: pip install yfinance")
            return None
        except Exception as e:
            logger.error(f"Yahoo Finance fetch failed: {e}")
            return None

    async def update_market_data(self, ticker: str) -> bool:
        """
        Fetch and store market data in database.

        If Alpha Vantage returns historical data, stores all of it.
        If Yahoo Finance returns single data point, stores just that.

        Args:
            ticker: Stock ticker

        Returns:
            True if successful, False otherwise
        """
        from src.models import Security

        data = await self.fetch_daily_data(ticker)
        if not data:
            return False

        try:
            with db_session() as session:
                # Get or create Security
                security = session.query(Security).filter(Security.ticker == ticker).first()
                if not security:
                    # Create a basic Security entry if it doesn't exist
                    security = Security(ticker=ticker, name=ticker)
                    session.add(security)
                    session.flush()

                # Check if we have historical data (Alpha Vantage format)
                if isinstance(data, dict) and "historical" in data:
                    # Alpha Vantage - store all historical data
                    historical_data = data["historical"]

                    # Unmark previous latest with row locking to prevent race conditions
                    with session.begin_nested():  # Savepoint for atomicity
                        session.query(MarketData).filter(
                            MarketData.security_id == security.id, MarketData.is_latest
                        ).with_for_update().update({"is_latest": False}, synchronize_session=False)

                    # Store all historical data points
                    for data_point in historical_data:
                        # Convert timestamp string to datetime
                        timestamp = data_point["timestamp"]
                        if isinstance(timestamp, str):
                            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

                        # Check if this data point already exists
                        existing = (
                            session.query(MarketData)
                            .filter(
                                MarketData.security_id == security.id,
                                MarketData.timestamp == timestamp,
                            )
                            .first()
                        )

                        if existing:
                            # Update existing record
                            existing.price = data_point["close"]
                            existing.open = data_point["open"]
                            existing.high = data_point["high"]
                            existing.low = data_point["low"]
                            existing.close = data_point["close"]
                            existing.volume = data_point["volume"]
                            existing.data_source = data_point["source"]
                            existing.is_latest = data_point.get("is_latest", False)
                        else:
                            # Create new record
                            market_data = MarketData(
                                security_id=security.id,
                                timestamp=timestamp,
                                price=data_point["close"],
                                volume=data_point["volume"],
                                open=data_point["open"],
                                high=data_point["high"],
                                low=data_point["low"],
                                close=data_point["close"],
                                data_source=data_point["source"],
                                is_latest=data_point.get("is_latest", False),
                            )
                            session.add(market_data)

                    logger.info(f"Stored {len(historical_data)} data points for {ticker}")
                    return True

                else:
                    # Yahoo Finance or cached data - single data point
                    # Unmark previous latest with row locking to prevent race conditions
                    with session.begin_nested():  # Savepoint for atomicity
                        session.query(MarketData).filter(
                            MarketData.security_id == security.id, MarketData.is_latest
                        ).with_for_update().update({"is_latest": False}, synchronize_session=False)

                    # Convert timestamp string back to datetime if needed
                    timestamp = data["timestamp"]
                    if isinstance(timestamp, str):
                        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

                    # Check if this data point already exists
                    existing = (
                        session.query(MarketData)
                        .filter(
                            MarketData.security_id == security.id, MarketData.timestamp == timestamp
                        )
                        .first()
                    )

                    if existing:
                        # Update existing
                        existing.price = data["close"]
                        existing.open = data["open"]
                        existing.high = data["high"]
                        existing.low = data["low"]
                        existing.close = data["close"]
                        existing.volume = data["volume"]
                        existing.data_source = data["source"]
                        existing.is_latest = True
                    else:
                        # Create new
                        market_data = MarketData(
                            security_id=security.id,
                            timestamp=timestamp,
                            price=data["close"],
                            volume=data["volume"],
                            open=data["open"],
                            high=data["high"],
                            low=data["low"],
                            close=data["close"],
                            data_source=data["source"],
                            is_latest=True,
                        )
                        session.add(market_data)

                    return True

        except IntegrityError as e:
            logger.warning(f"Race condition detected for {ticker}, retrying: {e}")
            # Race condition - another process marked a record as is_latest
            # The unique partial index prevents data corruption
            # Return success as the data is already stored by another process
            return True
        except Exception as e:
            logger.error(f"Failed to store market data: {e}")
            return False

    async def batch_update(self, tickers: list[str]) -> None:
        """
        Update market data for multiple tickers with rate limiting.

        Args:
            tickers: List of stock tickers
        """
        for i, ticker in enumerate(tickers):
            logger.info(f"Fetching {ticker} ({i+1}/{len(tickers)})...")
            success = await self.update_market_data(ticker)

            if success:
                logger.info(f"✓ Updated {ticker}")
            else:
                logger.warning(f"✗ Failed {ticker}")

            # Rate limiting: wait between requests
            if i < len(tickers) - 1:
                await asyncio.sleep(self.request_delay)

    def get_current_prices(self, tickers: list[str]) -> dict[str, float]:
        """
        Bulk fetch current prices for multiple tickers from Yahoo Finance.

        Uses 15-minute in-memory caching. Fetches only uncached/stale tickers.

        Args:
            tickers: List of stock tickers

        Returns:
            Dictionary mapping ticker to current price (only includes successful fetches)
        """
        if not tickers:
            return {}

        result: dict[str, float] = {}
        tickers_to_fetch: list[str] = []
        now = datetime.now(timezone.utc)

        # Check in-memory cache first (fast path)
        for ticker in tickers:
            # Try in-memory cache
            if ticker in self._price_cache:
                cached_price, cached_time = self._price_cache[ticker]
                age = now - cached_time
                if age.total_seconds() < 900:  # 15 minutes
                    result[ticker] = cached_price
                    continue

            # Try file cache (survives across CLI calls)
            cached = self.cache.get("current_price", ticker, ttl_minutes=15)
            if cached and isinstance(cached, dict) and "price" in cached:
                price = float(cached["price"])
                # Store in memory for this request
                self._price_cache[ticker] = (price, now)
                result[ticker] = price
            else:
                tickers_to_fetch.append(ticker)

        # Bulk fetch uncached tickers
        if tickers_to_fetch:
            # Filter out obvious invalid tickers to speed up bulk fetch
            # (bonds, complex ISINs, etc. that won't have Yahoo Finance data)

            # Temporarily exclude known problematic tickers
            EXCLUDED_TICKERS = {
                "MAGIC",
                "LHVGRP290933",
                "IUTECR061026",
                "ICSUSSDP",
                "EGR1T",
                "BIG25-2035/1",
            }

            valid_tickers = []
            for ticker in tickers_to_fetch:
                # Skip temporarily excluded tickers
                if ticker in EXCLUDED_TICKERS:
                    continue

                # Skip bonds/ISINs: long tickers or tickers with many digits
                # But allow European stocks that end with exchange suffix
                is_european_stock = any(
                    ticker.endswith(suffix) for suffix in [".HE", ".OL", ".VS", ".TL", ".AS", ".DE"]
                )

                has_digits = any(char.isdigit() for char in ticker[1:])

                # Skip if:
                # 1. Too long (likely ISIN/bond code)
                # 2. Has digits AND is not a European stock (bonds usually have many digits)
                if len(ticker) > 15 or (has_digits and not is_european_stock):
                    continue

                valid_tickers.append(ticker)

            # Log filtering results
            logger.info(
                f"Filtered {len(tickers_to_fetch)} tickers -> {len(valid_tickers)} valid "
                f"(skipped {len(tickers_to_fetch) - len(valid_tickers)} bonds/ISINs)"
            )

            if not valid_tickers:
                return result

            try:
                # Use yf.download() for bulk fetching (faster than individual requests)
                # Suppress yfinance errors for invalid tickers (bonds, delisted stocks, etc.)
                import concurrent.futures
                import logging as yf_logging
                import time

                yf_logging.getLogger("yfinance").setLevel(yf_logging.CRITICAL)

                # Use thread executor with timeout to prevent hanging
                def download_with_timeout() -> Any:
                    return yf.download(
                        valid_tickers,
                        period="1d",
                        progress=False,
                        auto_adjust=True,
                        show_errors=False,
                        threads=False,  # Single-threaded for easier timeout handling
                    )

                start = time.time()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(download_with_timeout)
                    try:
                        data = future.result(timeout=10.0)  # 10 second timeout
                        elapsed = time.time() - start
                        logger.info(
                            f"yf.download took {elapsed:.2f}s for {len(valid_tickers)} tickers"
                        )
                    except concurrent.futures.TimeoutError:
                        logger.warning(
                            f"yf.download timed out after 10s for {len(valid_tickers)} tickers, "
                            "falling back to individual requests"
                        )
                        raise

                yf_logging.getLogger("yfinance").setLevel(yf_logging.WARNING)

                # Handle single ticker vs multiple tickers (different DataFrame structure)
                if len(valid_tickers) == 1:
                    ticker = valid_tickers[0]
                    if not data.empty and "Close" in data.columns:
                        price = float(data["Close"].iloc[-1])
                        self._price_cache[ticker] = (price, now)
                        self.cache.set("current_price", ticker, {"price": price})
                        result[ticker] = price
                else:
                    # Multiple tickers - Close is a DataFrame with ticker columns
                    if not data.empty and "Close" in data:
                        for ticker in valid_tickers:
                            if ticker in data["Close"].columns:
                                price = float(data["Close"][ticker].iloc[-1])
                                self._price_cache[ticker] = (price, now)
                                self.cache.set("current_price", ticker, {"price": price})
                                result[ticker] = price

            except Exception as e:
                # Bulk fetch failed - fall back to individual fetching for valid-looking tickers
                logger.debug(f"Bulk fetch failed ({e}), falling back to individual requests")
                for ticker in valid_tickers:
                    # Skip obviously invalid tickers
                    if "/" in ticker or len(ticker) > 10:
                        continue

                    try:
                        yf_ticker = yf.Ticker(ticker)
                        info = yf_ticker.info
                        price = (
                            info.get("currentPrice")
                            or info.get("regularMarketPrice")
                            or info.get("previousClose")
                        )
                        if price:
                            price_float = float(price)
                            self._price_cache[ticker] = (price_float, now)
                            self.cache.set("current_price", ticker, {"price": price_float})
                            result[ticker] = price_float
                    except Exception:
                        pass  # Silently skip tickers that fail

        return result

    def get_current_price(self, ticker: str) -> Optional[float]:
        """
        Get current price from Yahoo Finance with 15-minute in-memory caching.

        For fetching multiple tickers, use get_current_prices() for better performance.

        Args:
            ticker: Stock ticker

        Returns:
            Current price or None
        """
        # Use bulk fetch for single ticker
        prices = self.get_current_prices([ticker])
        return prices.get(ticker)
