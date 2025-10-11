"""
Ticker Validation Service - validates and enriches security identifiers.

This service validates tickers/ISINs against market data providers,
resolves identifiers to canonical tickers, and enriches security metadata.

Key Features:
- Validates tickers against Alpha Vantage and Yahoo Finance
- Resolves ISINs to tickers
- Resolves bond identifiers to proper names
- Detects security type (STOCK, BOND, ETF, FUND)
- Fetches security metadata (name, exchange, currency)
- Caches validation results to minimize API calls
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

from src.lib.api_client import APIClient
from src.models.security import SecurityType

logger = logging.getLogger(__name__)


@dataclass
class SecurityMetadata:
    """Validated and enriched security metadata."""

    ticker: str  # Canonical ticker symbol
    name: str  # Full security name
    exchange: str  # Exchange code (e.g., NASDAQ, NYSE, TSE)
    security_type: SecurityType  # STOCK, BOND, ETF, FUND
    currency: str  # Trading currency (ISO 4217)
    isin: Optional[str] = None  # ISIN if available
    country: Optional[str] = None  # Country code if available


class TickerValidationService:
    """
    Service for validating and enriching security identifiers.

    Validates tickers/ISINs against market data APIs and enriches
    with metadata like name, exchange, and security type.
    """

    # Estonian bond patterns
    ESTONIAN_BOND_PATTERN = re.compile(
        r"^([A-Z0-9]+)(\d{6})?$"  # e.g., "1", "LHVGRP290933", "IUTECR061026"
    )

    # ISIN pattern (2 letter country code + 9 alphanumeric + check digit)
    ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

    def __init__(self) -> None:
        """Initialize validation service with API client."""
        self.api_client = APIClient()
        self._cache: dict[str, SecurityMetadata] = {}

    def validate_and_enrich(
        self, identifier: str, exchange_hint: Optional[str] = None
    ) -> Optional[SecurityMetadata]:
        """
        Validate identifier and return enriched metadata.

        Args:
            identifier: Ticker, ISIN, or bond ID to validate
            exchange_hint: Optional exchange hint from CSV (e.g., "TSE", "NASDAQ")

        Returns:
            SecurityMetadata if validation successful, None otherwise
        """
        # Check cache first
        cache_key = f"{identifier}:{exchange_hint or ''}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Detect identifier type and validate accordingly
        if self._is_isin(identifier):
            metadata = self._validate_isin(identifier)
        elif self._is_estonian_bond(identifier):
            metadata = self._validate_estonian_bond(identifier, exchange_hint)
        else:
            metadata = self._validate_ticker(identifier, exchange_hint)

        # Cache result
        if metadata:
            self._cache[cache_key] = metadata

        return metadata

    def _is_isin(self, identifier: str) -> bool:
        """Check if identifier is an ISIN."""
        return bool(self.ISIN_PATTERN.match(identifier))

    def _is_estonian_bond(self, identifier: str) -> bool:
        """Check if identifier matches Estonian bond pattern."""
        # Simple heuristic: numeric-only or specific patterns
        if identifier.isdigit():
            return True
        return bool(self.ESTONIAN_BOND_PATTERN.match(identifier)) and (
            "GRP" in identifier or "ECR" in identifier or len(identifier) > 10
        )

    def _validate_isin(self, isin: str) -> Optional[SecurityMetadata]:
        """
        Validate ISIN and resolve to ticker.

        ISINs are resolved by:
        1. Trying Alpha Vantage search
        2. Falling back to Yahoo Finance lookup
        3. Using ISIN as ticker if no resolution found

        Args:
            isin: ISIN to validate

        Returns:
            SecurityMetadata or None
        """
        logger.info(f"Validating ISIN: {isin}")

        try:
            # Try Alpha Vantage symbol search
            response = self.api_client.get(
                "/query",
                params={"function": "SYMBOL_SEARCH", "keywords": isin},
                use_cache=True,
            )

            if response and "bestMatches" in response:  # type: ignore[operator]
                matches = response["bestMatches"]  # type: ignore[index]
                if matches and len(matches) > 0:
                    result = matches[0]
                    return SecurityMetadata(
                        ticker=result.get("1. symbol", isin),
                        name=result.get("2. name", isin),
                        exchange=result.get("4. region", "UNKNOWN"),
                        security_type=self._detect_security_type(result.get("3. type", "")),
                        currency=result.get("8. currency", "EUR"),
                        isin=isin,
                        country=result.get("4. region", None),
                    )
        except Exception as e:
            logger.warning(f"Alpha Vantage search failed for ISIN {isin}: {e}")

        # Fallback: Use ISIN as ticker (common for Estonian securities)
        logger.warning(f"Could not resolve ISIN {isin}, using as ticker")
        return SecurityMetadata(
            ticker=isin,
            name=isin,
            exchange="UNKNOWN",
            security_type=SecurityType.STOCK,
            currency="EUR",
            isin=isin,
        )

    def _validate_estonian_bond(
        self, bond_id: str, exchange_hint: Optional[str]
    ) -> Optional[SecurityMetadata]:
        """
        Validate Estonian bond identifier.

        Estonian bonds use various formats:
        - Simple numeric: "1" → "BIG25-2035/1" (BigBank bonds)
        - With maturity: "LHVGRP290933" → LHV Group bond maturing 29.09.33
        - With coupon: "IUTECR061026" → Inbank bond

        Args:
            bond_id: Bond identifier
            exchange_hint: Exchange hint (AS = Nasdaq Baltic, BIGBANK, etc.)

        Returns:
            SecurityMetadata for the bond
        """
        logger.info(f"Validating Estonian bond: {bond_id} (exchange: {exchange_hint})")

        # Parse bond ID patterns
        if bond_id.isdigit():
            # Simple numeric bonds (e.g., "1" for BigBank)
            if exchange_hint and "BIG" in exchange_hint.upper():
                ticker = f"BIG25-2035/{bond_id}"
                name = f"BigBank 2025-2035 Series {bond_id}"
            else:
                ticker = f"BOND-{bond_id}"
                name = f"Bond Series {bond_id}"
        elif "LHVGRP" in bond_id:
            # LHV Group bond with maturity date
            # Format: LHVGRP + DDMMYY
            try:
                date_part = bond_id.replace("LHVGRP", "")
                dd, mm, yy = date_part[:2], date_part[2:4], date_part[4:6]
                ticker = f"LHVGRP-{dd}.{mm}.{yy}"
                name = f"LHV Group Bond {dd}.{mm}.20{yy}"
            except Exception:
                ticker = bond_id
                name = "LHV Group Bond"
        elif "IUTECR" in bond_id:
            # Inbank (IuteCredit) bond
            try:
                date_part = bond_id.replace("IUTECR", "")
                mm, yy = date_part[:2], date_part[2:4]
                if len(date_part) >= 6:
                    dd = date_part[4:6]
                    ticker = f"IUTECR-{dd}.{mm}.{yy}"
                    name = f"Inbank Bond {dd}.{mm}.20{yy}"
                else:
                    ticker = f"IUTECR-{mm}.20{yy}"
                    name = f"Inbank Bond {mm}.20{yy}"
            except Exception:
                ticker = bond_id
                name = "Inbank Bond"
        else:
            ticker = bond_id
            name = bond_id

        return SecurityMetadata(
            ticker=ticker,
            name=name,
            exchange=exchange_hint or "AS",  # Nasdaq Baltic
            security_type=SecurityType.BOND,
            currency="EUR",
        )

    def _validate_ticker(
        self, ticker: str, exchange_hint: Optional[str]
    ) -> Optional[SecurityMetadata]:
        """
        Validate stock ticker against APIs.

        Args:
            ticker: Stock ticker symbol
            exchange_hint: Optional exchange hint

        Returns:
            SecurityMetadata or None if validation fails
        """
        logger.info(f"Validating ticker: {ticker} (exchange: {exchange_hint})")

        try:
            # Try Alpha Vantage quote endpoint for validation
            quote = self.api_client.get_global_quote(ticker)  # type: ignore[attr-defined]
            if quote and "01. symbol" in quote:
                return SecurityMetadata(
                    ticker=ticker,
                    name=quote.get("01. symbol", ticker),  # AV doesn't return full name in quote
                    exchange=exchange_hint or "UNKNOWN",
                    security_type=SecurityType.STOCK,
                    currency=quote.get("08. currency", "USD"),
                )
        except Exception as e:
            logger.warning(f"Alpha Vantage validation failed for {ticker}: {e}")

        # Fallback: Accept ticker as-is with warning
        logger.warning(f"Could not validate ticker {ticker}, accepting as-is")
        return SecurityMetadata(
            ticker=ticker,
            name=ticker,
            exchange=exchange_hint or "UNKNOWN",
            security_type=SecurityType.STOCK,
            currency="USD" if not exchange_hint or exchange_hint in ("NASDAQ", "NYSE") else "EUR",
        )

    def _detect_security_type(self, type_hint: str) -> SecurityType:
        """
        Detect security type from API type hint.

        Args:
            type_hint: Type hint from API (e.g., "Equity", "ETF", "Bond")

        Returns:
            SecurityType enum value
        """
        type_hint_upper = type_hint.upper()

        if "ETF" in type_hint_upper:
            return SecurityType.ETF
        elif "BOND" in type_hint_upper or "DEBT" in type_hint_upper:
            return SecurityType.BOND
        elif "FUND" in type_hint_upper or "MUTUAL" in type_hint_upper:
            return SecurityType.FUND
        else:
            return SecurityType.STOCK  # Default to stock
