"""Currency converter service with exchange rate API integration."""

import logging
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)

from src.lib.api_client import APIClient
from src.lib.db import db_session
from src.models.exchange_rate import ExchangeRate

logger = logging.getLogger(__name__)


class CurrencyConverter:
    """Handles currency conversion with exchange rate caching."""

    def __init__(self) -> None:
        """Initialize currency converter."""
        self.api_client = APIClient()
        self.api_key = os.getenv("EXCHANGE_RATE_API_KEY", "")
        # Free tier: exchangerate-api.com
        self.base_url = "https://v6.exchangerate-api.com/v6"
        # In-memory cache for rates: {(from, to, date): (rate, timestamp)}
        self._rate_cache: dict[tuple[str, str, date], tuple[float, datetime]] = {}

    @retry(
        stop=(stop_after_attempt(3) | stop_after_delay(30)),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, ValueError)),
        reraise=True,
    )
    async def _fetch_from_api(self, from_currency: str, to_currency: str) -> Optional[float]:
        """
        Fetch exchange rate from API with retry logic.

        Args:
            from_currency: Source currency
            to_currency: Target currency

        Returns:
            Exchange rate

        Raises:
            ValueError: If API returns error
            ConnectionError: If network error occurs
        """
        url = f"{self.base_url}/{self.api_key}/pair/{from_currency}/{to_currency}"

        async with self.api_client as client:
            response = await client.get(url)

        if response.get("result") != "success":
            raise ValueError(f"API error: {response.get('error-type', 'Unknown')}")

        conversion_rate: float = float(response["conversion_rate"])
        return conversion_rate

    async def _fetch_from_yfinance(
        self, from_currency: str, to_currency: str, rate_date: Optional[date] = None
    ) -> Optional[float]:
        """
        Fetch exchange rate from Yahoo Finance using forex pairs.

        Yahoo Finance forex pairs use format: "BASEQUOTE=X" (e.g., "EURUSD=X")

        Args:
            from_currency: Source currency code
            to_currency: Target currency code
            rate_date: Date for historical rate (None = today)

        Returns:
            Exchange rate or None if unavailable
        """
        try:
            import yfinance as yf
            from datetime import timedelta

            # Construct forex pair symbol
            forex_symbol = f"{from_currency}{to_currency}=X"
            ticker = yf.Ticker(forex_symbol)

            if rate_date is None:
                rate_date = date.today()

            # For today or recent dates, try current price first
            if rate_date >= date.today() - timedelta(days=1):
                info = ticker.info
                if "regularMarketPrice" in info and info["regularMarketPrice"]:
                    rate = float(info["regularMarketPrice"])
                    logger.info(f"Yahoo Finance forex {forex_symbol}: {rate}")
                    return rate

            # Fetch historical data for the specific date
            # Request a 3-day window around the target date to handle weekends/holidays
            start_date = rate_date - timedelta(days=3)
            end_date = rate_date + timedelta(days=1)

            hist = ticker.history(start=start_date, end=end_date)

            if not hist.empty and "Close" in hist.columns:
                # Try to find rate for exact date
                if rate_date in hist.index.date:
                    rate = float(hist.loc[hist.index.date == rate_date, "Close"].iloc[0])
                    logger.info(f"Yahoo Finance forex {forex_symbol} on {rate_date}: {rate}")
                    return rate
                # Fallback: use closest available date
                else:
                    rate = float(hist["Close"].iloc[-1])
                    actual_date = hist.index[-1].date()
                    logger.info(
                        f"Yahoo Finance forex {forex_symbol}: using {actual_date} rate {rate} "
                        f"(requested {rate_date}, weekend/holiday)"
                    )
                    return rate

            logger.warning(f"No forex data available for {forex_symbol} on {rate_date}")
            return None

        except ImportError:
            logger.error("yfinance not installed. Install with: pip install yfinance")
            return None
        except Exception as e:
            logger.warning(f"Yahoo Finance forex error for {from_currency}/{to_currency} on {rate_date}: {e}")
            return None

    async def fetch_exchange_rate(
        self, from_currency: str, to_currency: str, rate_date: Optional[date] = None
    ) -> Optional[float]:
        """
        Fetch exchange rate from API and cache in database.

        Strategy:
        1. Check in-memory cache (15-minute TTL)
        2. Check database cache
        3. Try exchangerate-api.com (if API key set)
        4. Try Yahoo Finance forex pairs (free, unlimited)
        5. Raise error (no hardcoded fallback - prevents financial calculation errors)

        Args:
            from_currency: Source currency code (e.g., 'USD')
            to_currency: Target currency code (e.g., 'EUR')
            rate_date: Date for historical rate (None = today)

        Returns:
            Exchange rate or None if fetch fails

        Raises:
            ValueError: If all data sources fail (prevents using stale/incorrect rates)
        """
        # Self-conversion always returns 1.0
        if from_currency == to_currency:
            return 1.0

        if rate_date is None:
            rate_date = date.today()

        # Check in-memory cache first (15-minute TTL)
        cache_key = (from_currency, to_currency, rate_date)
        if cache_key in self._rate_cache:
            cached_rate, cached_time = self._rate_cache[cache_key]
            age = datetime.now(timezone.utc) - cached_time
            if age.total_seconds() < 900:  # 15 minutes
                logger.debug(
                    f"Using in-memory cached rate {from_currency}/{to_currency}: {cached_rate}"
                )
                return cached_rate

        # Check database cache
        db_cached_rate: Optional[float] = self._get_cached_rate(
            from_currency, to_currency, rate_date
        )
        if db_cached_rate is not None:
            # Store in memory cache for subsequent requests
            self._rate_cache[cache_key] = (db_cached_rate, datetime.now(timezone.utc))
            logger.info(
                f"Using database cached rate {from_currency}/{to_currency}: {db_cached_rate}"
            )
            return db_cached_rate

        # Try primary API if key is set
        if self.api_key:
            try:
                rate: Optional[float] = await self._fetch_from_api(from_currency, to_currency)
                if rate is not None:
                    # Cache in database and memory
                    self._cache_rate(from_currency, to_currency, rate, rate_date)
                    self._rate_cache[cache_key] = (rate, datetime.now(timezone.utc))
                    logger.info(f"Fetched {from_currency}/{to_currency} from exchangerate-api.com")
                    return rate
            except Exception as e:
                logger.warning(
                    f"exchangerate-api.com failed for {from_currency}/{to_currency}: {e}"
                )

        # Fallback to Yahoo Finance forex
        try:
            rate_yf: Optional[float] = await self._fetch_from_yfinance(from_currency, to_currency, rate_date)
            if rate_yf:
                # Cache in database and memory
                self._cache_rate(from_currency, to_currency, rate_yf, rate_date)
                self._rate_cache[cache_key] = (rate_yf, datetime.now(timezone.utc))
                logger.info(f"Fetched {from_currency}/{to_currency} from Yahoo Finance")
                return rate_yf
        except Exception as e:
            logger.warning(f"Yahoo Finance forex failed for {from_currency}/{to_currency}: {e}")

        # No fallback - raise error to prevent incorrect financial calculations
        error_msg = (
            f"Failed to fetch exchange rate {from_currency}/{to_currency} from all sources. "
            "Cannot proceed with transaction - exchange rate required for accurate calculations."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    def _get_cached_rate(
        self, from_currency: str, to_currency: str, rate_date: date
    ) -> Optional[float]:
        """
        Get cached exchange rate from database.

        Args:
            from_currency: Source currency
            to_currency: Target currency
            rate_date: Rate date

        Returns:
            Cached rate or None
        """
        with db_session() as session:
            rate_entry = (
                session.query(ExchangeRate)
                .filter(
                    ExchangeRate.from_currency == from_currency,
                    ExchangeRate.to_currency == to_currency,
                    ExchangeRate.date == rate_date,
                )
                .first()
            )

            if rate_entry:
                return float(rate_entry.rate)
            return None

    def _cache_rate(
        self, from_currency: str, to_currency: str, rate: float, rate_date: date
    ) -> None:
        """
        Cache exchange rate in database.

        Args:
            from_currency: Source currency
            to_currency: Target currency
            rate: Exchange rate
            rate_date: Rate date
        """
        try:
            with db_session() as session:
                # Check if already exists
                existing = (
                    session.query(ExchangeRate)
                    .filter(
                        ExchangeRate.from_currency == from_currency,
                        ExchangeRate.to_currency == to_currency,
                        ExchangeRate.date == rate_date,
                    )
                    .first()
                )

                if existing:
                    existing.rate = Decimal(str(rate))
                else:
                    rate_entry = ExchangeRate(
                        from_currency=from_currency,
                        to_currency=to_currency,
                        date=rate_date,
                        rate=rate,
                    )
                    session.add(rate_entry)

        except Exception as e:
            logger.error(f"Failed to cache exchange rate: {e}")

    async def convert(
        self,
        amount: float,
        from_currency: str,
        to_currency: str,
        rate_date: Optional[date] = None,
    ) -> Optional[float]:
        """
        Convert amount from one currency to another.

        Args:
            amount: Amount to convert
            from_currency: Source currency code
            to_currency: Target currency code
            rate_date: Date for historical rate (None = today)

        Returns:
            Converted amount or None if conversion fails
        """
        if from_currency == to_currency:
            return amount

        rate = await self.fetch_exchange_rate(from_currency, to_currency, rate_date)
        if rate is None:
            return None

        return amount * rate

    async def get_rate(
        self, from_currency: str, to_currency: str, rate_date: Optional[date] = None
    ) -> Optional[float]:
        """
        Get exchange rate (wrapper for fetch_exchange_rate).

        Args:
            from_currency: Source currency
            to_currency: Target currency
            rate_date: Date for rate (None = today)

        Returns:
            Exchange rate or None
        """
        return await self.fetch_exchange_rate(from_currency, to_currency, rate_date)

    async def update_rates_batch(self, currency_pairs: list[tuple[str, str]]) -> None:
        """
        Update multiple currency pairs at once.

        Args:
            currency_pairs: List of (from_currency, to_currency) tuples
        """
        for from_curr, to_curr in currency_pairs:
            logger.info(f"Fetching {from_curr}/{to_curr}...")
            rate = await self.fetch_exchange_rate(from_curr, to_curr)
            if rate:
                logger.info(f"✓ {from_curr}/{to_curr} = {rate:.4f}")
            else:
                logger.warning(f"✗ Failed {from_curr}/{to_curr}")
