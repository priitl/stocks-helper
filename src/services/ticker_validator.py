"""Ticker validation service with exchange suffix detection and fuzzy matching.

Validates stock tickers against market data APIs with intelligent fallback:
1. Try exact ticker match
2. Try with exchange suffixes (e.g., TKM1T → TKM1T.TL)
3. Try fuzzy matching for typo detection
"""

from dataclasses import dataclass


@dataclass
class TickerValidationResult:
    """Result of ticker validation."""

    ticker: str  # Original ticker from CSV
    valid: bool  # True if ticker found in market data
    suggestions: list[str]  # Suggested corrections (fuzzy matches or suffix variants)
    confidence: list[str]  # Confidence per suggestion ("high", "medium", "low")
    validation_source: str  # Source of validation (e.g., "exact_match", "suffix_detected_Tallinn")


class TickerValidator:
    """Validates stock tickers with exchange suffix detection and fuzzy matching.

    Strategy:
    1. Try exact ticker (e.g., "AAPL")
    2. Try with exchange suffixes (e.g., "TKM1T" → "TKM1T.TL")
    3. Try fuzzy matching for typos (e.g., "APPL" → "AAPL")
    """

    # Common exchange suffixes for regional markets
    EXCHANGE_SUFFIXES = {
        "TL": "Tallinn Stock Exchange",
        "HE": "Helsinki Stock Exchange",
        "ST": "Stockholm Stock Exchange",
        "OL": "Oslo Stock Exchange",
        "CO": "Copenhagen Stock Exchange",
        "IC": "Iceland Stock Exchange",
        "L": "London Stock Exchange",
        "DE": "XETRA (Germany)",
        "PA": "Paris Euronext",
        "AS": "Amsterdam Euronext",
    }

    def __init__(self, known_tickers: set[str] | None = None):
        """Initialize ticker validator.

        Args:
            known_tickers: Set of known valid tickers for fuzzy matching.
                          If None, fuzzy matching will be disabled.
        """
        self.known_tickers = known_tickers or set()

    def validate_ticker_sync(self, ticker: str) -> TickerValidationResult:
        """Validate ticker with 3-step strategy (synchronous version).

        Args:
            ticker: Ticker to validate

        Returns:
            TickerValidationResult with validation status and suggestions
        """
        if not ticker:
            return TickerValidationResult(
                ticker="",
                valid=False,
                suggestions=[],
                confidence=[],
                validation_source="empty_ticker",
            )

        # Step 1: Try exact ticker match
        if self._ticker_exists_sync(ticker):
            return TickerValidationResult(
                ticker=ticker,
                valid=True,
                suggestions=[],
                confidence=[],
                validation_source="exact_match",
            )

        # Step 2: Try with exchange suffixes
        suffix_result = self._try_exchange_suffixes_sync(ticker)
        if suffix_result:
            return suffix_result

        # Step 3: Try fuzzy matching
        fuzzy_result = self._try_fuzzy_matching(ticker)
        if fuzzy_result:
            return fuzzy_result

        # No matches found
        return TickerValidationResult(
            ticker=ticker,
            valid=False,
            suggestions=[],
            confidence=[],
            validation_source="not_found",
        )

    async def validate_ticker(self, ticker: str) -> TickerValidationResult:
        """Validate ticker with 3-step strategy.

        Args:
            ticker: Ticker to validate

        Returns:
            TickerValidationResult with validation status and suggestions
        """
        if not ticker:
            return TickerValidationResult(
                ticker="",
                valid=False,
                suggestions=[],
                confidence=[],
                validation_source="empty_ticker",
            )

        # Step 1: Try exact ticker match
        if await self._ticker_exists(ticker):
            return TickerValidationResult(
                ticker=ticker,
                valid=True,
                suggestions=[],
                confidence=[],
                validation_source="exact_match",
            )

        # Step 2: Try with exchange suffixes
        suffix_result = await self._try_exchange_suffixes(ticker)
        if suffix_result:
            return suffix_result

        # Step 3: Try fuzzy matching
        fuzzy_result = self._try_fuzzy_matching(ticker)
        if fuzzy_result:
            return fuzzy_result

        # No matches found
        return TickerValidationResult(
            ticker=ticker,
            valid=False,
            suggestions=[],
            confidence=[],
            validation_source="not_found",
        )

    def _ticker_exists_sync(self, ticker: str) -> bool:
        """Check if ticker exists (synchronous version).

        Args:
            ticker: Ticker to check

        Returns:
            True if ticker exists
        """
        return ticker.upper() in self.known_tickers

    async def _ticker_exists(self, ticker: str) -> bool:
        """Check if ticker exists in market data.

        ⏳ DEFERRED: Real-time API validation (low priority)
        Currently checks against known_tickers set for fast validation.

        Trade-offs of adding API calls:
        - ✅ Would catch brand new tickers not in known_tickers
        - ❌ Would slow down CSV validation significantly (API call per ticker)
        - ❌ Would consume API rate limits during bulk imports

        Note: Actual ticker validation happens later via yfinance in
        ImportService._enrich_stock_metadata() when fetching metadata.

        Args:
            ticker: Ticker to check

        Returns:
            True if ticker exists in known_tickers set
        """
        return ticker.upper() in self.known_tickers

    def _try_exchange_suffixes_sync(self, ticker: str) -> TickerValidationResult | None:
        """Try ticker with regional exchange suffixes (synchronous version).

        Args:
            ticker: Base ticker (e.g., "TKM1T")

        Returns:
            TickerValidationResult if a suffixed variant is found, None otherwise
        """
        suggestions = []
        confidence_list = []

        for suffix, exchange_name in self.EXCHANGE_SUFFIXES.items():
            suffixed_ticker = f"{ticker}.{suffix}"
            if self._ticker_exists_sync(suffixed_ticker):
                suggestions.append(suffixed_ticker)
                confidence_list.append("high")

        if suggestions:
            return TickerValidationResult(
                ticker=ticker,
                valid=False,  # Original ticker not found
                suggestions=suggestions,
                confidence=confidence_list,
                validation_source=f"suffix_detected_{self.EXCHANGE_SUFFIXES[suggestions[0].split('.')[-1]]}",
            )

        return None

    async def _try_exchange_suffixes(self, ticker: str) -> TickerValidationResult | None:
        """Try ticker with regional exchange suffixes.

        Args:
            ticker: Base ticker (e.g., "TKM1T")

        Returns:
            TickerValidationResult if a suffixed variant is found, None otherwise
        """
        suggestions = []
        confidence_list = []

        for suffix, exchange_name in self.EXCHANGE_SUFFIXES.items():
            suffixed_ticker = f"{ticker}.{suffix}"
            if await self._ticker_exists(suffixed_ticker):
                suggestions.append(suffixed_ticker)
                confidence_list.append("high")

        if suggestions:
            return TickerValidationResult(
                ticker=ticker,
                valid=False,  # Original ticker not found
                suggestions=suggestions,
                confidence=confidence_list,
                validation_source=f"suffix_detected_{self.EXCHANGE_SUFFIXES[suggestions[0].split('.')[-1]]}",
            )

        return None

    def _try_fuzzy_matching(self, ticker: str) -> TickerValidationResult | None:
        """Try fuzzy matching for typo detection.

        Args:
            ticker: Ticker to match

        Returns:
            TickerValidationResult if fuzzy matches found, None otherwise
        """
        from src.lib.fuzzy_match import fuzzy_match_ticker

        if not self.known_tickers:
            return None

        matches = fuzzy_match_ticker(ticker, self.known_tickers, threshold=2, max_results=3)

        if matches:
            # Assign confidence based on Levenshtein distance
            from src.lib.fuzzy_match import levenshtein_distance

            confidence_list = []
            for match in matches:
                distance = levenshtein_distance(ticker.upper(), match.upper())
                if distance == 1:
                    confidence_list.append("high")
                elif distance == 2:
                    confidence_list.append("medium")
                else:
                    confidence_list.append("low")

            return TickerValidationResult(
                ticker=ticker,
                valid=False,
                suggestions=matches,
                confidence=confidence_list,
                validation_source="fuzzy_match",
            )

        return None

    async def validate_batch(self, tickers: list[str]) -> dict[str, TickerValidationResult]:
        """Validate multiple tickers in batch.

        Args:
            tickers: List of tickers to validate

        Returns:
            Dictionary mapping ticker to validation result
        """
        results = {}
        for ticker in tickers:
            results[ticker] = await self.validate_ticker(ticker)
        return results
