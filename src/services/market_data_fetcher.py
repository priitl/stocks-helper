"""Market data fetcher with fallback strategy."""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Optional

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
        data = await self.fetch_daily_data(ticker)
        if not data:
            return False

        try:
            with db_session() as session:
                # Check if we have historical data (Alpha Vantage format)
                if isinstance(data, dict) and "historical" in data:
                    # Alpha Vantage - store all historical data
                    historical_data = data["historical"]

                    # Unmark previous latest with row locking to prevent race conditions
                    with session.begin_nested():  # Savepoint for atomicity
                        session.query(MarketData).filter(
                            MarketData.ticker == ticker, MarketData.is_latest
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
                            .filter(MarketData.ticker == ticker, MarketData.timestamp == timestamp)
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
                                ticker=data_point["ticker"],
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
                            MarketData.ticker == ticker, MarketData.is_latest
                        ).with_for_update().update({"is_latest": False}, synchronize_session=False)

                    # Convert timestamp string back to datetime if needed
                    timestamp = data["timestamp"]
                    if isinstance(timestamp, str):
                        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

                    # Check if this data point already exists
                    existing = (
                        session.query(MarketData)
                        .filter(MarketData.ticker == ticker, MarketData.timestamp == timestamp)
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
                            ticker=data["ticker"],
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

    def get_current_price(self, ticker: str) -> Optional[float]:
        """
        Get current price from database (latest market data).

        Args:
            ticker: Stock ticker

        Returns:
            Current price or None
        """
        with db_session() as session:
            market_data = (
                session.query(MarketData)
                .filter(MarketData.ticker == ticker, MarketData.is_latest)
                .first()
            )

            if market_data:
                return float(market_data.price)
            return None
