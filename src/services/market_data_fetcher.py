"""Market data fetcher with fallback strategy."""

import asyncio
import os
from datetime import datetime
from typing import Optional

from src.lib.api_client import APIClient
from src.lib.cache import CacheManager
from src.lib.config import API_RATE_LIMIT_DELAY
from src.lib.db import get_session
from src.lib.quota_tracker import QuotaTracker
from src.models.market_data import MarketData


class MarketDataFetcher:
    """Fetches market data from APIs with fallback strategy."""

    def __init__(self):
        """Initialize market data fetcher."""
        self.api_client = APIClient()
        self.cache = CacheManager()
        self.alpha_vantage_key = os.getenv("ALPHA_VANTAGE_API_KEY", "")
        self.request_delay = API_RATE_LIMIT_DELAY  # Seconds between API requests (rate limiting)
        # Alpha Vantage free tier: 25 requests/day, 5 per minute
        self.quota_tracker = QuotaTracker(
            api_name="alpha_vantage", daily_limit=25, per_minute_limit=5
        )

    async def fetch_daily_data(self, ticker: str) -> Optional[dict]:
        """
        Fetch daily market data for a ticker with fallback strategy.

        Strategy:
        1. Try Alpha Vantage (primary)
        2. Try Yahoo Finance (fallback)
        3. Try cache (if APIs fail)

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with market data or None if all sources fail
        """
        # Try Alpha Vantage first
        try:
            data = await self._fetch_alpha_vantage(ticker)
            if data:
                return data
        except Exception as e:
            print(f"Alpha Vantage failed for {ticker}: {e}")

        # Fallback to Yahoo Finance
        try:
            data = await self._fetch_yahoo_finance(ticker)
            if data:
                return data
        except Exception as e:
            print(f"Yahoo Finance failed for {ticker}: {e}")

        # Try cache as last resort
        cached = self.cache.get("market_data", ticker, ttl_minutes=1440)  # 24 hours
        if cached:
            print(f"Using cached data for {ticker}")
            return cached

        return None

    async def _fetch_alpha_vantage(self, ticker: str) -> Optional[dict]:
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
            print(
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

            # Check for API errors
            if "Error Message" in response:
                raise ValueError(f"Alpha Vantage error: {response['Error Message']}")

            if "Note" in response:
                # Rate limit hit
                raise ValueError("Alpha Vantage rate limit exceeded")

            # Parse response
            if "Time Series (Daily)" not in response:
                return None

            time_series = response["Time Series (Daily)"]

            # Return ALL historical data (for storing in DB)
            # But also identify the latest for caching
            latest_date = max(time_series.keys())

            # Build result with all historical data
            historical_data = []
            for date_str, data in time_series.items():
                historical_data.append(
                    {
                        "ticker": ticker,
                        "timestamp": date_str,
                        "open": float(data["1. open"]),
                        "high": float(data["2. high"]),
                        "low": float(data["3. low"]),
                        "close": float(data["4. close"]),
                        "volume": int(data["5. volume"]),
                        "source": "alpha_vantage",
                        "is_latest": date_str == latest_date,
                    }
                )

            # Cache the latest data point
            latest_data = next(d for d in historical_data if d["is_latest"])
            self.cache.set("alpha_vantage", ticker, latest_data)

            # Return all historical data for database storage
            return {"historical": historical_data, "latest": latest_data}

        except Exception as e:
            print(f"Alpha Vantage fetch failed: {e}")
            return None

    async def _fetch_yahoo_finance(self, ticker: str) -> Optional[dict]:
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
            print("yfinance not installed. Install with: pip install yfinance")
            return None
        except Exception as e:
            print(f"Yahoo Finance fetch failed: {e}")
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

        session = get_session()
        try:
            # Check if we have historical data (Alpha Vantage format)
            if isinstance(data, dict) and "historical" in data:
                # Alpha Vantage - store all historical data
                historical_data = data["historical"]

                # Unmark previous latest
                session.query(MarketData).filter(
                    MarketData.ticker == ticker, MarketData.is_latest
                ).update({"is_latest": False})

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

                session.commit()
                print(f"Stored {len(historical_data)} data points for {ticker}")
                return True

            else:
                # Yahoo Finance or cached data - single data point
                # Unmark previous latest
                session.query(MarketData).filter(
                    MarketData.ticker == ticker, MarketData.is_latest
                ).update({"is_latest": False})

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

                session.commit()
                return True

        except Exception as e:
            session.rollback()
            print(f"Failed to store market data: {e}")
            return False
        finally:
            session.close()

    async def batch_update(self, tickers: list[str]):
        """
        Update market data for multiple tickers with rate limiting.

        Args:
            tickers: List of stock tickers
        """
        for i, ticker in enumerate(tickers):
            print(f"Fetching {ticker} ({i+1}/{len(tickers)})...")
            success = await self.update_market_data(ticker)

            if success:
                print(f"✓ Updated {ticker}")
            else:
                print(f"✗ Failed {ticker}")

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
        session = get_session()
        try:
            market_data = (
                session.query(MarketData)
                .filter(MarketData.ticker == ticker, MarketData.is_latest)
                .first()
            )

            if market_data:
                return market_data.price
            return None

        finally:
            session.close()
