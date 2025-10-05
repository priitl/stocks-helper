"""Batch processor for daily portfolio updates."""

import asyncio
from datetime import datetime

from src.lib.db import get_session
from src.models.holding import Holding
from src.models.portfolio import Portfolio
from src.services.currency_converter import CurrencyConverter
from src.services.fundamental_analyzer import FundamentalAnalyzer
from src.services.insight_generator import InsightGenerator
from src.services.market_data_fetcher import MarketDataFetcher
from src.services.recommendation_engine import RecommendationEngine
from src.services.suggestion_engine import SuggestionEngine


class BatchProcessor:
    """Orchestrates daily batch job for portfolio updates."""

    def __init__(self):
        """Initialize batch processor."""
        self.market_data_fetcher = MarketDataFetcher()
        self.fundamental_analyzer = FundamentalAnalyzer()
        self.currency_converter = CurrencyConverter()
        self.recommendation_engine = RecommendationEngine()
        self.suggestion_engine = SuggestionEngine()
        self.insight_generator = InsightGenerator()

    async def process_portfolio(self, portfolio_id: str) -> dict:
        """
        Process a single portfolio: fetch data, generate recommendations, insights.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Dict with processing summary
        """
        session = get_session()
        try:
            portfolio = session.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
            if not portfolio:
                return {"error": "Portfolio not found"}

            # Get all unique tickers from holdings
            holdings = (
                session.query(Holding)
                .filter(Holding.portfolio_id == portfolio_id, Holding.quantity > 0)
                .all()
            )

            tickers = list(set(h.ticker for h in holdings))

            if not tickers:
                return {
                    "portfolio_id": portfolio_id,
                    "tickers_processed": 0,
                    "recommendations_generated": 0,
                    "insights_generated": 0,
                    "message": "No holdings in portfolio",
                }

            print(f"\n{'='*60}")
            print(f"Processing Portfolio: {portfolio.name}")
            print(f"{'='*60}")

            # 1. Fetch market data for all tickers
            print(f"\n📊 Fetching market data for {len(tickers)} stocks...")
            market_data_success = 0

            for ticker in tickers:
                success = await self.market_data_fetcher.update_market_data(ticker)
                if success:
                    print(f"  ✓ {ticker}: Market data updated")
                    market_data_success += 1
                else:
                    print(f"  ✗ {ticker}: Failed to fetch market data")

                # Rate limiting delay
                await asyncio.sleep(1)

            # 2. Fetch fundamental data
            print("\n📈 Fetching fundamental data...")
            fundamental_success = 0

            for ticker in tickers:
                success = await self.fundamental_analyzer.update_fundamental_data(ticker)
                if success:
                    print(f"  ✓ {ticker}: Fundamental data updated")
                    fundamental_success += 1
                else:
                    print(f"  ⚠️  {ticker}: Fundamental data unavailable")

                # Rate limiting delay
                await asyncio.sleep(1)

            # 3. Update exchange rates (if multi-currency)
            print("\n💱 Updating exchange rates...")
            currencies = set()
            for holding in holdings:
                if holding.original_currency:
                    currencies.add(holding.original_currency)

            if portfolio.base_currency:
                currencies.add(portfolio.base_currency)

            currency_pairs = []
            for curr in currencies:
                if curr != portfolio.base_currency:
                    currency_pairs.append((curr, portfolio.base_currency))

            if currency_pairs:
                await self.currency_converter.update_rates_batch(currency_pairs)
                print(f"  ✓ Updated {len(currency_pairs)} currency pairs")
            else:
                print("  ⏭️  Single currency portfolio")

            # 4. Generate recommendations for each holding
            print("\n🎯 Generating recommendations...")
            recommendations_generated = 0

            for ticker in tickers:
                rec = await self.recommendation_engine.generate_recommendation(ticker, portfolio_id)
                if rec:
                    print(
                        f"  ✓ {ticker}: {rec.recommendation.value} "
                        f"(confidence: {rec.confidence.value})"
                    )
                    recommendations_generated += 1
                else:
                    print(f"  ✗ {ticker}: Failed to generate recommendation")

            # 5. Generate portfolio insights
            print("\n💡 Generating insights...")
            insights = self.insight_generator.generate_all_insights(portfolio_id)
            print(f"  ✓ Generated {len(insights)} insights")

            # Summary
            summary = {
                "portfolio_id": portfolio_id,
                "portfolio_name": portfolio.name,
                "timestamp": datetime.now().isoformat(),
                "tickers_processed": len(tickers),
                "market_data_updated": market_data_success,
                "fundamentals_updated": fundamental_success,
                "currency_pairs_updated": len(currency_pairs),
                "recommendations_generated": recommendations_generated,
                "insights_generated": len(insights),
            }

            print(f"\n{'='*60}")
            print("✅ Processing Complete")
            print(f"{'='*60}")
            print(f"Tickers processed: {len(tickers)}")
            print(f"Market data updated: {market_data_success}/{len(tickers)}")
            print(f"Fundamentals updated: {fundamental_success}/{len(tickers)}")
            print(f"Recommendations: {recommendations_generated}")
            print(f"Insights: {len(insights)}")
            print(f"{'='*60}\n")

            return summary

        except Exception as e:
            print(f"\n❌ Error processing portfolio {portfolio_id}: {e}")
            return {
                "portfolio_id": portfolio_id,
                "error": str(e),
            }
        finally:
            session.close()

    async def process_all_portfolios(self) -> dict:
        """
        Process all portfolios in the system.

        Returns:
            Dict with summary of all portfolio processing
        """
        session = get_session()
        try:
            portfolios = session.query(Portfolio).all()

            if not portfolios:
                return {
                    "total_portfolios": 0,
                    "message": "No portfolios found",
                }

            print(f"\n{'#'*60}")
            print(f"BATCH JOB STARTED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'#'*60}")
            print(f"Portfolios to process: {len(portfolios)}\n")

            summaries = []

            for portfolio in portfolios:
                summary = await self.process_portfolio(portfolio.id)
                summaries.append(summary)

            # Overall summary
            total_tickers = sum(s.get("tickers_processed", 0) for s in summaries)
            total_recommendations = sum(s.get("recommendations_generated", 0) for s in summaries)
            total_insights = sum(s.get("insights_generated", 0) for s in summaries)

            overall_summary = {
                "timestamp": datetime.now().isoformat(),
                "total_portfolios": len(portfolios),
                "total_tickers_processed": total_tickers,
                "total_recommendations": total_recommendations,
                "total_insights": total_insights,
                "portfolios": summaries,
            }

            print(f"\n{'#'*60}")
            print("BATCH JOB COMPLETED")
            print(f"{'#'*60}")
            print(f"Portfolios: {len(portfolios)}")
            print(f"Total tickers: {total_tickers}")
            print(f"Total recommendations: {total_recommendations}")
            print(f"Total insights: {total_insights}")
            print(f"{'#'*60}\n")

            return overall_summary

        finally:
            session.close()

    async def run_daily_batch(self) -> dict:
        """
        Run the daily batch job.

        Returns:
            Dict with batch job summary
        """
        print("🚀 Starting daily batch job...")
        return await self.process_all_portfolios()


async def run_batch_once():
    """Convenience function to run batch job once."""
    processor = BatchProcessor()
    return await processor.run_daily_batch()


if __name__ == "__main__":
    # Allow running this module directly for testing
    asyncio.run(run_batch_once())
