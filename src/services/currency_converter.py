"""Currency converter service with exchange rate API integration."""

import logging
import os
from datetime import date, datetime
from typing import Optional

from src.lib.api_client import APIClient
from src.lib.db import get_session
from src.models.exchange_rate import ExchangeRate

logger = logging.getLogger(__name__)


class CurrencyConverter:
    """Handles currency conversion with exchange rate caching."""

    def __init__(self):
        """Initialize currency converter."""
        self.api_client = APIClient()
        self.api_key = os.getenv("EXCHANGE_RATE_API_KEY", "")
        # Free tier: exchangerate-api.com
        self.base_url = "https://v6.exchangerate-api.com/v6"

    async def fetch_exchange_rate(
        self, from_currency: str, to_currency: str, rate_date: Optional[date] = None
    ) -> Optional[float]:
        """
        Fetch exchange rate from API and cache in database.

        Args:
            from_currency: Source currency code (e.g., 'USD')
            to_currency: Target currency code (e.g., 'EUR')
            rate_date: Date for historical rate (None = today)

        Returns:
            Exchange rate or None if fetch fails
        """
        # Self-conversion always returns 1.0
        if from_currency == to_currency:
            return 1.0

        if rate_date is None:
            rate_date = date.today()

        # Check database cache first
        cached_rate = self._get_cached_rate(from_currency, to_currency, rate_date)
        if cached_rate:
            return cached_rate

        # Fetch from API
        try:
            if not self.api_key:
                logger.warning("EXCHANGE_RATE_API_KEY not set, using fallback")
                return await self._fallback_rate(from_currency, to_currency)

            url = f"{self.base_url}/{self.api_key}/pair/{from_currency}/{to_currency}"

            async with self.api_client as client:
                response = await client.get(url)

            if response.get("result") != "success":
                raise ValueError(f"API error: {response.get('error-type', 'Unknown')}")

            rate = float(response["conversion_rate"])

            # Cache the rate
            self._cache_rate(from_currency, to_currency, rate, rate_date)

            return rate

        except Exception as e:
            logger.error(f"Failed to fetch exchange rate {from_currency}/{to_currency}: {e}")
            return await self._fallback_rate(from_currency, to_currency)

    async def _fallback_rate(self, from_currency: str, to_currency: str) -> Optional[float]:
        """
        Fallback to hardcoded approximate rates when API is unavailable.

        Args:
            from_currency: Source currency
            to_currency: Target currency

        Returns:
            Approximate rate or None
        """
        # Approximate rates (USD-based, as of Oct 2025)
        usd_rates = {
            "USD": 1.0,
            "EUR": 0.85,
            "GBP": 0.73,
            "JPY": 110.0,
            "CHF": 0.88,
            "CAD": 1.25,
            "AUD": 1.35,
            "CNY": 6.5,
        }

        if from_currency in usd_rates and to_currency in usd_rates:
            # Convert through USD: from -> USD -> to
            from_usd = 1.0 / usd_rates[from_currency]
            to_rate = usd_rates[to_currency]
            return from_usd * to_rate

        logger.warning(f"No fallback rate available for {from_currency}/{to_currency}")
        return None

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
        session = get_session()
        try:
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
                return rate_entry.rate
            return None

        finally:
            session.close()

    def _cache_rate(self, from_currency: str, to_currency: str, rate: float, rate_date: date) -> None:
        """
        Cache exchange rate in database.

        Args:
            from_currency: Source currency
            to_currency: Target currency
            rate: Exchange rate
            rate_date: Rate date
        """
        session = get_session()
        try:
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
                existing.rate = rate
            else:
                rate_entry = ExchangeRate(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    date=rate_date,
                    rate=rate,
                )
                session.add(rate_entry)

            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to cache exchange rate: {e}")
        finally:
            session.close()

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
            print(f"Fetching {from_curr}/{to_curr}...")
            rate = await self.fetch_exchange_rate(from_curr, to_curr)
            if rate:
                print(f"✓ {from_curr}/{to_curr} = {rate:.4f}")
            else:
                print(f"✗ Failed {from_curr}/{to_curr}")
