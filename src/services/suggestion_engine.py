"""Suggestion engine for discovering new stock opportunities."""

from datetime import datetime

from src.lib.db import get_session
from src.models.holding import Holding
from src.models.stock import Stock
from src.models.suggestion import StockSuggestion, SuggestionType
from src.services.fundamental_analyzer import FundamentalAnalyzer
from src.services.indicator_calculator import IndicatorCalculator
from src.services.recommendation_engine import RecommendationEngine


class SuggestionEngine:
    """Generates new stock suggestions based on portfolio analysis."""

    def __init__(self):
        """Initialize suggestion engine."""
        self.indicator_calc = IndicatorCalculator()
        self.fundamental_analyzer = FundamentalAnalyzer()
        self.recommendation_engine = RecommendationEngine()

    def analyze_portfolio_gaps(self, portfolio_id: str) -> dict:
        """
        Analyze portfolio for diversification gaps.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Dict with gap analysis (sectors, regions, market caps)
        """
        session = get_session()
        try:
            # Get all holdings with stock info
            holdings = session.query(Holding).filter(Holding.portfolio_id == portfolio_id).all()

            if not holdings:
                return {"sectors": {}, "regions": {}, "market_caps": {}}

            # Get stock details for each holding
            sector_allocation = {}
            region_allocation = {}
            market_cap_allocation = {}

            total_value = 0

            for holding in holdings:
                stock = session.query(Stock).filter(Stock.ticker == holding.ticker).first()
                if not stock:
                    continue

                # Use quantity * some estimated price (simplified)
                # In real implementation, would use current market price
                holding_value = holding.quantity * holding.avg_purchase_price
                total_value += holding_value

                # Sector allocation
                sector = stock.sector or "Unknown"
                sector_allocation[sector] = sector_allocation.get(sector, 0) + holding_value

                # Region allocation
                region = stock.country or "Unknown"
                region_allocation[region] = region_allocation.get(region, 0) + holding_value

                # Market cap allocation
                if stock.market_cap:
                    if stock.market_cap > 200_000_000_000:  # $200B+
                        cap_category = "Mega Cap"
                    elif stock.market_cap > 10_000_000_000:  # $10B+
                        cap_category = "Large Cap"
                    elif stock.market_cap > 2_000_000_000:  # $2B+
                        cap_category = "Mid Cap"
                    else:
                        cap_category = "Small Cap"

                    market_cap_allocation[cap_category] = (
                        market_cap_allocation.get(cap_category, 0) + holding_value
                    )

            # Convert to percentages
            if total_value > 0:
                sector_pct = {k: (v / total_value) * 100 for k, v in sector_allocation.items()}
                region_pct = {k: (v / total_value) * 100 for k, v in region_allocation.items()}
                market_cap_pct = {
                    k: (v / total_value) * 100 for k, v in market_cap_allocation.items()
                }
            else:
                sector_pct = {}
                region_pct = {}
                market_cap_pct = {}

            return {
                "sectors": sector_pct,
                "regions": region_pct,
                "market_caps": market_cap_pct,
            }

        finally:
            session.close()

    def identify_high_performers(self, portfolio_id: str) -> list[str]:
        """
        Identify top performing stocks in portfolio.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            List of ticker symbols (top 3 performers by gain %)
        """
        session = get_session()
        try:
            holdings = (
                session.query(Holding)
                .filter(Holding.portfolio_id == portfolio_id, Holding.quantity > 0)
                .all()
            )

            # Calculate gain % for each (simplified - using purchase price)
            performers = []
            for holding in holdings:
                # In real implementation, would use current market price
                # For now, use a placeholder gain calculation
                performers.append({"ticker": holding.ticker, "gain_pct": 0})  # Placeholder

            # Sort by gain % descending
            performers.sort(key=lambda x: x["gain_pct"], reverse=True)

            return [p["ticker"] for p in performers[:3]]

        finally:
            session.close()

    def get_owned_tickers(self, portfolio_id: str) -> set[str]:
        """Get set of tickers already owned in portfolio."""
        session = get_session()
        try:
            holdings = (
                session.query(Holding.ticker)
                .filter(Holding.portfolio_id == portfolio_id, Holding.quantity > 0)
                .all()
            )
            return {h.ticker for h in holdings}

        finally:
            session.close()

    async def generate_diversification_suggestions(
        self, portfolio_id: str, candidate_tickers: list[str]
    ) -> list[StockSuggestion]:
        """
        Generate suggestions to fill diversification gaps.

        Args:
            portfolio_id: Portfolio ID
            candidate_tickers: List of candidate tickers to evaluate

        Returns:
            List of StockSuggestion objects
        """
        gaps = self.analyze_portfolio_gaps(portfolio_id)
        owned_tickers = self.get_owned_tickers(portfolio_id)
        suggestions = []

        session = get_session()
        try:
            # Find underrepresented sectors/regions (< 10%)
            gap_sectors = [sector for sector, pct in gaps["sectors"].items() if pct < 10]
            gap_regions = [region for region, pct in gaps["regions"].items() if pct < 10]

            for ticker in candidate_tickers:
                if ticker in owned_tickers:
                    continue

                # Get stock info
                stock = session.query(Stock).filter(Stock.ticker == ticker).first()
                if not stock:
                    continue

                # Check if fills a gap
                fills_gap = False
                gap_description = []

                if stock.sector in gap_sectors:
                    fills_gap = True
                    gap_description.append(f"Underrepresented sector: {stock.sector}")

                if stock.country in gap_regions:
                    fills_gap = True
                    gap_description.append(f"Underrepresented region: {stock.country}")

                if not fills_gap:
                    continue

                # Calculate scores
                technical_score, tech_signals = (
                    self.recommendation_engine.calculate_technical_score(
                        self.indicator_calc.calculate_all_indicators(ticker) or {}
                    )
                )
                fundamental_score, fund_signals = (
                    self.recommendation_engine.calculate_fundamental_score(ticker)
                )
                overall_score = (technical_score + fundamental_score) / 2

                # Create suggestion
                suggestion = StockSuggestion(
                    ticker=ticker,
                    portfolio_id=portfolio_id,
                    timestamp=datetime.now(),
                    suggestion_type=SuggestionType.DIVERSIFICATION,
                    technical_score=technical_score,
                    fundamental_score=fundamental_score,
                    overall_score=int(overall_score),
                    technical_summary=", ".join(tech_signals[:3]),
                    fundamental_summary=", ".join(fund_signals[:3]),
                    portfolio_fit="\n".join(gap_description),
                    related_holding_ticker=None,
                )

                suggestions.append(suggestion)

            return suggestions

        finally:
            session.close()

    async def generate_similar_to_winners_suggestions(
        self, portfolio_id: str, candidate_tickers: list[str]
    ) -> list[StockSuggestion]:
        """
        Generate suggestions for stocks similar to high performers.

        Args:
            portfolio_id: Portfolio ID
            candidate_tickers: List of candidate tickers

        Returns:
            List of StockSuggestion objects
        """
        high_performers = self.identify_high_performers(portfolio_id)
        owned_tickers = self.get_owned_tickers(portfolio_id)
        suggestions = []

        session = get_session()
        try:
            for winner_ticker in high_performers:
                winner_stock = session.query(Stock).filter(Stock.ticker == winner_ticker).first()
                if not winner_stock:
                    continue

                # Find similar stocks (same sector, similar market cap)
                for ticker in candidate_tickers:
                    if ticker in owned_tickers:
                        continue

                    candidate = session.query(Stock).filter(Stock.ticker == ticker).first()
                    if not candidate:
                        continue

                    # Check similarity
                    is_similar = False
                    similarity_reasons = []

                    if candidate.sector == winner_stock.sector:
                        is_similar = True
                        similarity_reasons.append(
                            f"Same sector as {winner_ticker}: {candidate.sector}"
                        )

                    # Market cap similarity (within 50% range)
                    if winner_stock.market_cap and candidate.market_cap:
                        ratio = candidate.market_cap / winner_stock.market_cap
                        if 0.5 <= ratio <= 2.0:
                            is_similar = True
                            similarity_reasons.append(f"Similar market cap to {winner_ticker}")

                    if not is_similar:
                        continue

                    # Calculate scores
                    technical_score, tech_signals = (
                        self.recommendation_engine.calculate_technical_score(
                            self.indicator_calc.calculate_all_indicators(ticker) or {}
                        )
                    )
                    fundamental_score, fund_signals = (
                        self.recommendation_engine.calculate_fundamental_score(ticker)
                    )
                    overall_score = (technical_score + fundamental_score) / 2

                    # Create suggestion
                    suggestion = StockSuggestion(
                        ticker=ticker,
                        portfolio_id=portfolio_id,
                        timestamp=datetime.now(),
                        suggestion_type=SuggestionType.SIMILAR_TO_WINNERS,
                        technical_score=technical_score,
                        fundamental_score=fundamental_score,
                        overall_score=int(overall_score),
                        technical_summary=", ".join(tech_signals[:3]),
                        fundamental_summary=", ".join(fund_signals[:3]),
                        portfolio_fit="\n".join(similarity_reasons),
                        related_holding_ticker=winner_ticker,
                    )

                    suggestions.append(suggestion)

            return suggestions

        finally:
            session.close()

    async def generate_market_opportunities(
        self, portfolio_id: str, candidate_tickers: list[str]
    ) -> list[StockSuggestion]:
        """
        Generate suggestions for strong market opportunities.

        Args:
            portfolio_id: Portfolio ID
            candidate_tickers: List of candidate tickers

        Returns:
            List of StockSuggestion objects
        """
        owned_tickers = self.get_owned_tickers(portfolio_id)
        suggestions = []

        for ticker in candidate_tickers:
            if ticker in owned_tickers:
                continue

            # Calculate scores
            technical_score, tech_signals = self.recommendation_engine.calculate_technical_score(
                self.indicator_calc.calculate_all_indicators(ticker) or {}
            )
            fundamental_score, fund_signals = (
                self.recommendation_engine.calculate_fundamental_score(ticker)
            )
            overall_score = (technical_score + fundamental_score) / 2

            # Only suggest if overall score is high (> 70)
            if overall_score < 70:
                continue

            # Create suggestion
            suggestion = StockSuggestion(
                ticker=ticker,
                portfolio_id=portfolio_id,
                timestamp=datetime.now(),
                suggestion_type=SuggestionType.MARKET_OPPORTUNITY,
                technical_score=technical_score,
                fundamental_score=fundamental_score,
                overall_score=int(overall_score),
                technical_summary=", ".join(tech_signals[:3]),
                fundamental_summary=", ".join(fund_signals[:3]),
                portfolio_fit="Strong technical and fundamental signals",
                related_holding_ticker=None,
            )

            suggestions.append(suggestion)

        return suggestions

    async def generate_all_suggestions(
        self, portfolio_id: str, candidate_tickers: list[str]
    ) -> list[StockSuggestion]:
        """
        Generate all types of suggestions.

        Args:
            portfolio_id: Portfolio ID
            candidate_tickers: List of candidate tickers to evaluate

        Returns:
            List of all suggestions
        """
        session = get_session()
        try:
            # Generate all types
            diversification = await self.generate_diversification_suggestions(
                portfolio_id, candidate_tickers
            )
            similar = await self.generate_similar_to_winners_suggestions(
                portfolio_id, candidate_tickers
            )
            opportunities = await self.generate_market_opportunities(
                portfolio_id, candidate_tickers
            )

            all_suggestions = diversification + similar + opportunities

            # Store in database
            for suggestion in all_suggestions:
                session.add(suggestion)

            session.commit()

            return all_suggestions

        except Exception as e:
            session.rollback()
            print(f"Failed to generate suggestions: {e}")
            return []
        finally:
            session.close()
