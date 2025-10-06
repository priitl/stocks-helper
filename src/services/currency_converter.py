"""Currency converter service with exchange rate API integration."""

import logging
import os
from datetime import date
from decimal import Decimal
from typing import Optional

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

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

    @retry(  # type: ignore[misc]
        stop=stop_after_attempt(3),
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

    async def _fetch_from_yfinance(self, from_currency: str, to_currency: str) -> Optional[float]:
        """
        Fetch exchange rate from Yahoo Finance using forex pairs.

        Yahoo Finance forex pairs use format: "BASEQUOTE=X" (e.g., "EURUSD=X")

        Args:
            from_currency: Source currency code
            to_currency: Target currency code

        Returns:
            Exchange rate or None if unavailable
        """
        try:
            import yfinance as yf

            # Construct forex pair symbol
            forex_symbol = f"{from_currency}{to_currency}=X"

            # Fetch current data
            ticker = yf.Ticker(forex_symbol)
            info = ticker.info

            # Try to get current price from info
            if "regularMarketPrice" in info and info["regularMarketPrice"]:
                rate = float(info["regularMarketPrice"])
                logger.info(f"Yahoo Finance forex {forex_symbol}: {rate}")
                return rate

            # Fallback: try history
            hist = ticker.history(period="1d")
            if not hist.empty and "Close" in hist.columns:
                rate = float(hist["Close"].iloc[-1])
                logger.info(f"Yahoo Finance forex {forex_symbol} (from history): {rate}")
                return rate

            logger.warning(f"No forex data available for {forex_symbol}")
            return None

        except ImportError:
            logger.error("yfinance not installed. Install with: pip install yfinance")
            return None
        except Exception as e:
            logger.warning(f"Yahoo Finance forex error for {from_currency}/{to_currency}: {e}")
            return None

    async def fetch_exchange_rate(
        self, from_currency: str, to_currency: str, rate_date: Optional[date] = None
    ) -> Optional[float]:
        """
        Fetch exchange rate from API and cache in database.

        Strategy:
        1. Check database cache
        2. Try exchangerate-api.com (if API key set)
        3. Try Yahoo Finance forex pairs (free, unlimited)
        4. Raise error (no hardcoded fallback - prevents financial calculation errors)

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

        # Check database cache first
        cached_rate = self._get_cached_rate(from_currency, to_currency, rate_date)
        if cached_rate:
            logger.info(f"Using cached rate {from_currency}/{to_currency}: {cached_rate}")
            return cached_rate

        # Try primary API if key is set
        if self.api_key:
            try:
                rate: Optional[float] = await self._fetch_from_api(from_currency, to_currency)
                if rate is not None:
                    # Cache the rate
                    self._cache_rate(from_currency, to_currency, rate, rate_date)
                    logger.info(f"Fetched {from_currency}/{to_currency} from exchangerate-api.com")
                    return rate
            except Exception as e:
                logger.warning(
                    f"exchangerate-api.com failed for {from_currency}/{to_currency}: {e}"
                )

        # Fallback to Yahoo Finance forex
        try:
            rate_yf: Optional[float] = await self._fetch_from_yfinance(from_currency, to_currency)
            if rate_yf:
                # Cache the rate
                self._cache_rate(from_currency, to_currency, rate_yf, rate_date)
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
