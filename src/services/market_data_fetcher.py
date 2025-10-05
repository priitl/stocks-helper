"""Market data fetcher with fallback strategy."""

import asyncio
import os
from datetime import datetime
from typing import Optional

import aiohttp

from src.lib.api_client import APIClient
from src.lib.cache import CacheManager
from src.lib.db import get_session
from src.models.market_data import MarketData
from src.models.stock import Stock


class MarketDataFetcher:
    """Fetches market data from APIs with fallback strategy."""

    def __init__(self):
        """Initialize market data fetcher."""
        self.api_client = APIClient()
        self.cache = CacheManager()
        self.alpha_vantage_key = os.getenv("ALPHA_VANTAGE_API_KEY", "")
        self.request_delay = 15  # Seconds between API requests (rate limiting)

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

        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": ticker,
            "apikey": self.alpha_vantage_key,
            "outputsize": "compact",
        }

        try:
            response = await self.api_client.get(url, params=params)

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
            latest_date = max(time_series.keys())
            latest_data = time_series[latest_date]

            result = {
                "ticker": ticker,
                "timestamp": datetime.fromisoformat(latest_date),
                "open": float(latest_data["1. open"]),
                "high": float(latest_data["2. high"]),
                "low": float(latest_data["3. low"]),
                "close": float(latest_data["4. close"]),
                "volume": int(latest_data["5. volume"]),
                "source": "alpha_vantage",
            }

            # Cache successful response
            self.cache.set("alpha_vantage", ticker, result)
            return result

        except Exception as e:
            print(f"Alpha Vantage fetch failed: {e}")
            return None

    async def _fetch_yahoo_finance(self, ticker: str) -> Optional[dict]:
        """
        Fetch data from Yahoo Finance using yfinance.

        Args:
            ticker: Stock ticker

        Returns:
            Market data dict or None
        """
        # Check cache first
        cached = self.cache.get("yahoo_finance", ticker)
        if cached:
            return cached

        try:
            # Import yfinance only when needed
            import yfinance as yf

            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")

            if hist.empty:
                return None

            latest = hist.iloc[-1]
            latest_date = hist.index[-1]

            result = {
                "ticker": ticker,
                "timestamp": latest_date.to_pydatetime(),
                "open": float(latest["Open"]),
                "high": float(latest["High"]),
                "low": float(latest["Low"]),
                "close": float(latest["Close"]),
                "volume": int(latest["Volume"]),
                "source": "yahoo_finance",
            }

            # Cache successful response
            self.cache.set("yahoo_finance", ticker, result)
            return result

        except ImportError:
            print("yfinance not installed. Install with: pip install yfinance")
            return None
        except Exception as e:
            print(f"Yahoo Finance fetch failed: {e}")
            return None

    async def update_market_data(self, ticker: str) -> bool:
        """
        Fetch and store latest market data in database.

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
            # Unmark previous latest
            session.query(MarketData).filter(
                MarketData.ticker == ticker, MarketData.is_latest == True
            ).update({"is_latest": False})

            # Create new market data entry
            market_data = MarketData(
                ticker=data["ticker"],
                timestamp=data["timestamp"],
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
                .filter(MarketData.ticker == ticker, MarketData.is_latest == True)
                .first()
            )

            if market_data:
                return market_data.price
            return None

        finally:
            session.close()
