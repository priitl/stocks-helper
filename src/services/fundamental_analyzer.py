"""Fundamental analysis service for extracting financial metrics."""

import os
from datetime import datetime
from typing import Optional

from src.lib.api_client import APIClient
from src.lib.db import get_session
from src.models.fundamental_data import FundamentalData


class FundamentalAnalyzer:
    """Extracts and analyzes fundamental metrics from API data."""

    def __init__(self):
        """Initialize fundamental analyzer."""
        self.api_client = APIClient()
        self.alpha_vantage_key = os.getenv("ALPHA_VANTAGE_API_KEY", "")

    async def fetch_fundamental_data(self, ticker: str) -> Optional[dict]:
        """
        Fetch fundamental data from Alpha Vantage OVERVIEW endpoint.

        Args:
            ticker: Stock ticker

        Returns:
            Dict with fundamental metrics or None
        """
        if not self.alpha_vantage_key:
            print("Warning: ALPHA_VANTAGE_API_KEY not set")
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
                print("Alpha Vantage rate limit exceeded")
                return None

            # Extract fundamental metrics
            metrics = self._parse_overview_response(response, ticker)
            return metrics

        except Exception as e:
            print(f"Failed to fetch fundamental data for {ticker}: {e}")
            return None

    def _parse_overview_response(self, data: dict, ticker: str) -> dict:
        """
        Parse Alpha Vantage OVERVIEW response into standardized metrics.

        Args:
            data: API response data
            ticker: Stock ticker

        Returns:
            Dict with fundamental metrics
        """

        def safe_float(value: str, default: float = 0.0) -> float:
            """Safely convert string to float."""
            try:
                if value == "None" or value == "-":
                    return default
                return float(value)
            except (ValueError, TypeError):
                return default

        metrics = {
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

        session = get_session()
        try:
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
            session.commit()
            return True

        except Exception as e:
            session.rollback()
            print(f"Failed to store fundamental data: {e}")
            return False
        finally:
            session.close()

    def get_latest_fundamentals(self, ticker: str) -> Optional[FundamentalData]:
        """
        Get latest fundamental data from database.

        Args:
            ticker: Stock ticker

        Returns:
            FundamentalData object or None
        """
        session = get_session()
        try:
            fundamentals = (
                session.query(FundamentalData)
                .filter(FundamentalData.ticker == ticker)
                .order_by(FundamentalData.timestamp.desc())
                .first()
            )

            return fundamentals

        finally:
            session.close()

    def analyze_valuation(self, fundamentals: FundamentalData) -> dict:
        """
        Analyze valuation metrics and assign score.

        Args:
            fundamentals: FundamentalData object

        Returns:
            Dict with valuation analysis
        """
        score = 0
        signals = []

        # P/E ratio (lower is better, but not negative)
        if 0 < fundamentals.pe_ratio < 15:
            score += 30
            signals.append("Low P/E (undervalued)")
        elif 15 <= fundamentals.pe_ratio < 25:
            score += 20
            signals.append("Moderate P/E")
        elif fundamentals.pe_ratio >= 25:
            score += 5
            signals.append("High P/E (potentially overvalued)")

        # P/B ratio (lower is better)
        if 0 < fundamentals.pb_ratio < 1:
            score += 20
            signals.append("Low P/B (trading below book value)")
        elif 1 <= fundamentals.pb_ratio < 3:
            score += 15
            signals.append("Moderate P/B")
        elif fundamentals.pb_ratio >= 3:
            score += 5
            signals.append("High P/B")

        # PEG ratio (lower is better, ideal < 1)
        if 0 < fundamentals.peg_ratio < 1:
            score += 30
            signals.append("Excellent PEG (growth at reasonable price)")
        elif 1 <= fundamentals.peg_ratio < 2:
            score += 20
            signals.append("Good PEG")
        elif fundamentals.peg_ratio >= 2:
            score += 10
            signals.append("High PEG")

        return {"score": min(score, 100), "signals": signals}

    def analyze_profitability(self, fundamentals: FundamentalData) -> dict:
        """Analyze profitability metrics."""
        score = 0
        signals = []

        # ROE (higher is better)
        if fundamentals.roe > 0.15:  # 15%+
            score += 30
            signals.append("Strong ROE")
        elif fundamentals.roe > 0.10:
            score += 20
            signals.append("Good ROE")
        elif fundamentals.roe > 0:
            score += 10
            signals.append("Positive ROE")

        # Profit margin
        if fundamentals.profit_margin > 0.20:  # 20%+
            score += 30
            signals.append("High profit margin")
        elif fundamentals.profit_margin > 0.10:
            score += 20
            signals.append("Good profit margin")
        elif fundamentals.profit_margin > 0:
            score += 10
            signals.append("Profitable")

        return {"score": min(score, 100), "signals": signals}

    def analyze_growth(self, fundamentals: FundamentalData) -> dict:
        """Analyze growth metrics."""
        score = 0
        signals = []

        # Revenue growth
        if fundamentals.revenue_growth_yoy > 0.20:  # 20%+
            score += 40
            signals.append("Strong revenue growth")
        elif fundamentals.revenue_growth_yoy > 0.10:
            score += 25
            signals.append("Moderate revenue growth")
        elif fundamentals.revenue_growth_yoy > 0:
            score += 10
            signals.append("Positive revenue growth")

        # Earnings growth
        if fundamentals.earnings_growth_yoy > 0.20:
            score += 40
            signals.append("Strong earnings growth")
        elif fundamentals.earnings_growth_yoy > 0.10:
            score += 25
            signals.append("Moderate earnings growth")
        elif fundamentals.earnings_growth_yoy > 0:
            score += 10
            signals.append("Positive earnings growth")

        return {"score": min(score, 100), "signals": signals}

    def analyze_financial_health(self, fundamentals: FundamentalData) -> dict:
        """Analyze financial health metrics."""
        score = 0
        signals = []

        # Debt to equity (lower is better)
        if fundamentals.debt_to_equity < 0.5:
            score += 40
            signals.append("Low debt levels")
        elif fundamentals.debt_to_equity < 1.0:
            score += 25
            signals.append("Moderate debt")
        elif fundamentals.debt_to_equity < 2.0:
            score += 10
            signals.append("High debt")

        # Current ratio (> 1 is healthy)
        if fundamentals.current_ratio > 2.0:
            score += 30
            signals.append("Strong liquidity")
        elif fundamentals.current_ratio > 1.0:
            score += 20
            signals.append("Adequate liquidity")

        return {"score": min(score, 100), "signals": signals}
