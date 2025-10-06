"""Fundamental analysis service for extracting financial metrics."""

import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from src.lib.api_client import APIClient
from src.lib.db import db_session
from src.models.fundamental_data import FundamentalData

logger = logging.getLogger(__name__)


class FundamentalAnalyzer:
    """Extracts and analyzes fundamental metrics from API data."""

    def __init__(self) -> None:
        """Initialize fundamental analyzer."""
        self.api_client = APIClient()
        self.alpha_vantage_key = os.getenv("ALPHA_VANTAGE_API_KEY", "")

    async def fetch_fundamental_data(self, ticker: str) -> Optional[dict[str, Any]]:
        """
        Fetch fundamental data from Alpha Vantage OVERVIEW endpoint.

        Args:
            ticker: Stock ticker

        Returns:
            Dict with fundamental metrics or None
        """
        if not self.alpha_vantage_key:
            logger.warning("ALPHA_VANTAGE_API_KEY not set")
            return None

        url = "https://www.alphavantage.co/query"
        params = {
            "function": "OVERVIEW",
            "symbol": ticker,
            "apikey": self.alpha_vantage_key,
        }

        try:
            async with self.api_client as client:
                response = await client.get(url, params=params)

            # Check for errors
            if "Error Message" in response or not response:
                return None

            if "Note" in response:
                logger.warning("Alpha Vantage rate limit exceeded")
                return None

            # Extract fundamental metrics
            metrics = self._parse_overview_response(response, ticker)
            return metrics

        except Exception as e:
            logger.error(f"Failed to fetch fundamental data for {ticker}: {e}")
            return None

    def _parse_overview_response(self, data: dict[str, Any], ticker: str) -> dict[str, Any]:
        """
        Parse Alpha Vantage OVERVIEW response into standardized metrics.

        Args:
            data: API response data
            ticker: Stock ticker

        Returns:
            Dict with fundamental metrics
        """

        def safe_float(value: Any, default: float = 0.0) -> float:
            """Safely convert string to float."""
            try:
                if value is None or value == "None" or value == "-":
                    return default
                return float(value)
            except (ValueError, TypeError):
                return default

        metrics: dict[str, Any] = {
            "ticker": ticker,
            "timestamp": datetime.now(),
            # Valuation ratios
            "pe_ratio": safe_float(data.get("PERatio")),
            "pb_ratio": safe_float(data.get("PriceToBookRatio")),
            "peg_ratio": safe_float(data.get("PEGRatio")),
            # Profitability
            "roe": safe_float(data.get("ReturnOnEquityTTM")),
            "roa": safe_float(data.get("ReturnOnAssetsTTM")),
            "profit_margin": safe_float(data.get("ProfitMargin")),
            # Growth
            "revenue_growth_yoy": safe_float(data.get("QuarterlyRevenueGrowthYOY")),
            "earnings_growth_yoy": safe_float(data.get("QuarterlyEarningsGrowthYOY")),
            # Financial health
            "debt_to_equity": safe_float(data.get("DebtToEquity")),
            "current_ratio": safe_float(data.get("CurrentRatio")),
            # Dividend
            "dividend_yield": safe_float(data.get("DividendYield")),
            # Source
            "data_source": "alpha_vantage",
        }

        return metrics

    async def update_fundamental_data(self, ticker: str) -> bool:
        """
        Fetch and store fundamental data in database.

        Args:
            ticker: Stock ticker

        Returns:
            True if successful, False otherwise
        """
        data = await self.fetch_fundamental_data(ticker)
        if not data:
            return False

        try:
            with db_session() as session:
                # Create new fundamental data entry
                fundamental = FundamentalData(
                    ticker=data["ticker"],
                    timestamp=data["timestamp"],
                    pe_ratio=data["pe_ratio"],
                    pb_ratio=data["pb_ratio"],
                    peg_ratio=data["peg_ratio"],
                    roe=data["roe"],
                    roa=data["roa"],
                    profit_margin=data["profit_margin"],
                    revenue_growth_yoy=data["revenue_growth_yoy"],
                    earnings_growth_yoy=data["earnings_growth_yoy"],
                    debt_to_equity=data["debt_to_equity"],
                    current_ratio=data["current_ratio"],
                    dividend_yield=data["dividend_yield"],
                    data_source=data["data_source"],
                )

                session.add(fundamental)
                return True

        except Exception as e:
            logger.error(f"Failed to store fundamental data: {e}")
            return False

    def get_latest_fundamentals(self, ticker: str) -> Optional[FundamentalData]:
        """
        Get latest fundamental data from database.

        Args:
            ticker: Stock ticker

        Returns:
            FundamentalData object or None
        """
        with db_session() as session:
            fundamentals = (
                session.query(FundamentalData)
                .filter(FundamentalData.ticker == ticker)
                .order_by(FundamentalData.timestamp.desc())
                .first()
            )

            return fundamentals

    def analyze_valuation(self, fundamentals: FundamentalData) -> dict[str, Any]:
        """
        Analyze valuation metrics and assign score.

        Args:
            fundamentals: FundamentalData object

        Returns:
            Dict with valuation analysis
        """
        score = 0
        signals: list[str] = []

        # P/E ratio (lower is better, but not negative)
        if fundamentals.pe_ratio is not None and 0 < fundamentals.pe_ratio < 15:
            score += 30
            signals.append("Low P/E (undervalued)")
        elif fundamentals.pe_ratio is not None and 15 <= fundamentals.pe_ratio < 25:
            score += 20
            signals.append("Moderate P/E")
        elif fundamentals.pe_ratio is not None and fundamentals.pe_ratio >= 25:
            score += 5
            signals.append("High P/E (potentially overvalued)")

        # P/B ratio (lower is better)
        if fundamentals.pb_ratio is not None and 0 < fundamentals.pb_ratio < 1:
            score += 20
            signals.append("Low P/B (trading below book value)")
        elif fundamentals.pb_ratio is not None and 1 <= fundamentals.pb_ratio < 3:
            score += 15
            signals.append("Moderate P/B")
        elif fundamentals.pb_ratio is not None and fundamentals.pb_ratio >= 3:
            score += 5
            signals.append("High P/B")

        # PEG ratio (lower is better, ideal < 1)
        if fundamentals.peg_ratio is not None and 0 < fundamentals.peg_ratio < 1:
            score += 30
            signals.append("Excellent PEG (growth at reasonable price)")
        elif fundamentals.peg_ratio is not None and 1 <= fundamentals.peg_ratio < 2:
            score += 20
            signals.append("Good PEG")
        elif fundamentals.peg_ratio is not None and fundamentals.peg_ratio >= 2:
            score += 10
            signals.append("High PEG")

        return {"score": min(score, 100), "signals": signals}

    def analyze_profitability(self, fundamentals: FundamentalData) -> dict[str, Any]:
        """Analyze profitability metrics."""
        score = 0
        signals: list[str] = []

        # ROE (higher is better)
        if fundamentals.roe is not None and fundamentals.roe > Decimal("0.15"):  # 15%+
            score += 30
            signals.append("Strong ROE")
        elif fundamentals.roe is not None and fundamentals.roe > Decimal("0.10"):
            score += 20
            signals.append("Good ROE")
        elif fundamentals.roe is not None and fundamentals.roe > 0:
            score += 10
            signals.append("Positive ROE")

        # Profit margin
        if fundamentals.profit_margin is not None and fundamentals.profit_margin > Decimal(
            "0.20"
        ):  # 20%+
            score += 30
            signals.append("High profit margin")
        elif fundamentals.profit_margin is not None and fundamentals.profit_margin > Decimal(
            "0.10"
        ):
            score += 20
            signals.append("Good profit margin")
        elif fundamentals.profit_margin is not None and fundamentals.profit_margin > 0:
            score += 10
            signals.append("Profitable")

        return {"score": min(score, 100), "signals": signals}

    def analyze_growth(self, fundamentals: FundamentalData) -> dict[str, Any]:
        """Analyze growth metrics."""
        score = 0
        signals: list[str] = []

        # Revenue growth
        if (
            fundamentals.revenue_growth_yoy is not None
            and fundamentals.revenue_growth_yoy > Decimal("0.20")
        ):  # 20%+
            score += 40
            signals.append("Strong revenue growth")
        elif (
            fundamentals.revenue_growth_yoy is not None
            and fundamentals.revenue_growth_yoy > Decimal("0.10")
        ):
            score += 25
            signals.append("Moderate revenue growth")
        elif fundamentals.revenue_growth_yoy is not None and fundamentals.revenue_growth_yoy > 0:
            score += 10
            signals.append("Positive revenue growth")

        # Earnings growth
        if (
            fundamentals.earnings_growth_yoy is not None
            and fundamentals.earnings_growth_yoy > Decimal("0.20")
        ):
            score += 40
            signals.append("Strong earnings growth")
        elif (
            fundamentals.earnings_growth_yoy is not None
            and fundamentals.earnings_growth_yoy > Decimal("0.10")
        ):
            score += 25
            signals.append("Moderate earnings growth")
        elif fundamentals.earnings_growth_yoy is not None and fundamentals.earnings_growth_yoy > 0:
            score += 10
            signals.append("Positive earnings growth")

        return {"score": min(score, 100), "signals": signals}

    def analyze_financial_health(self, fundamentals: FundamentalData) -> dict[str, Any]:
        """Analyze financial health metrics."""
        score = 0
        signals: list[str] = []

        # Debt to equity (lower is better)
        if fundamentals.debt_to_equity is not None and fundamentals.debt_to_equity < Decimal("0.5"):
            score += 40
            signals.append("Low debt levels")
        elif fundamentals.debt_to_equity is not None and fundamentals.debt_to_equity < Decimal(
            "1.0"
        ):
            score += 25
            signals.append("Moderate debt")
        elif fundamentals.debt_to_equity is not None and fundamentals.debt_to_equity < Decimal(
            "2.0"
        ):
            score += 10
            signals.append("High debt")

        # Current ratio (> 1 is healthy)
        if fundamentals.current_ratio is not None and fundamentals.current_ratio > Decimal("2.0"):
            score += 30
            signals.append("Strong liquidity")
        elif fundamentals.current_ratio is not None and fundamentals.current_ratio > Decimal("1.0"):
            score += 20
            signals.append("Adequate liquidity")

        return {"score": min(score, 100), "signals": signals}
