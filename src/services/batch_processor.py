"""Batch processor for daily portfolio updates."""

import asyncio
import logging
from datetime import datetime
from typing import Any

from src.lib.config import CIRCUIT_BREAKER_MAX_FAILURES
from src.lib.db import db_session
from src.lib.errors import BatchProcessingError
from src.models.holding import Holding
from src.models.portfolio import Portfolio
from src.services.currency_converter import CurrencyConverter
from src.services.fundamental_analyzer import FundamentalAnalyzer
from src.services.insight_generator import InsightGenerator
from src.services.market_data_fetcher import MarketDataFetcher
from src.services.recommendation_engine import RecommendationEngine
from src.services.suggestion_engine import SuggestionEngine

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Orchestrates daily batch job for portfolio updates."""

    def __init__(self) -> None:
        """Initialize batch processor."""
        self.market_data_fetcher = MarketDataFetcher()
        self.fundamental_analyzer = FundamentalAnalyzer()
        self.currency_converter = CurrencyConverter()
        self.recommendation_engine = RecommendationEngine()
        self.suggestion_engine = SuggestionEngine()
        self.insight_generator = InsightGenerator()

    async def process_portfolio(self, portfolio_id: str) -> dict[str, Any]:
        """
        Process a single portfolio: fetch data, generate recommendations, insights.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Dict with processing summary
        """
        with db_session() as session:
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

            logger.info(f"\n{'='*60}")
            logger.info(f"Processing Portfolio: {portfolio.name}")
            logger.info(f"{'='*60}")

            # 1. Fetch market data for all tickers
            logger.info(f"\n📊 Fetching market data for {len(tickers)} stocks...")
            market_data_success = 0
            consecutive_failures = 0

            for ticker in tickers:
                try:
                    success = await self.market_data_fetcher.update_market_data(ticker)
                    if success:
                        logger.info(f"  ✓ {ticker}: Market data updated")
                        market_data_success += 1
                        consecutive_failures = 0  # Reset on success
                    else:
                        logger.warning(f"  ✗ {ticker}: Failed to fetch market data")
                        consecutive_failures += 1

                    # Circuit breaker: stop if too many consecutive failures
                    if consecutive_failures >= CIRCUIT_BREAKER_MAX_FAILURES:
                        error_msg = (
                            f"Circuit breaker triggered: {CIRCUIT_BREAKER_MAX_FAILURES} "
                            "consecutive market data failures. Possible API outage."
                        )
                        logger.error(error_msg)
                        raise BatchProcessingError(error_msg)

                except BatchProcessingError:
                    raise  # Re-raise circuit breaker errors
                except Exception as e:
                    logger.error(f"  ✗ {ticker}: Critical error: {e}")
                    consecutive_failures += 1

                    if consecutive_failures >= CIRCUIT_BREAKER_MAX_FAILURES:
                        error_msg = (
                            f"Circuit breaker triggered: {CIRCUIT_BREAKER_MAX_FAILURES} "
                            "consecutive errors in market data fetch"
                        )
                        logger.error(error_msg)
                        raise BatchProcessingError(error_msg)

                # Rate limiting delay
                await asyncio.sleep(1)

            # 2. Fetch fundamental data
            logger.info("\n📈 Fetching fundamental data...")
            fundamental_success = 0

            for ticker in tickers:
                success = await self.fundamental_analyzer.update_fundamental_data(ticker)
                if success:
                    logger.info(f"  ✓ {ticker}: Fundamental data updated")
                    fundamental_success += 1
                else:
                    logger.warning(f"  ⚠️  {ticker}: Fundamental data unavailable")

                # Rate limiting delay
                await asyncio.sleep(1)

            # 3. Update exchange rates (if multi-currency)
            logger.info("\n💱 Updating exchange rates...")
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
                logger.info(f"  ✓ Updated {len(currency_pairs)} currency pairs")
            else:
                logger.info("  ⏭️  Single currency portfolio")

            # 4. Generate recommendations for each holding
            logger.info("\n🎯 Generating recommendations...")
            recommendations_generated = 0

            for ticker in tickers:
                rec = await self.recommendation_engine.generate_recommendation(ticker, portfolio_id)
                if rec:
                    logger.info(
                        f"  ✓ {ticker}: {rec.recommendation.value} "
                        f"(confidence: {rec.confidence.value})"
                    )
                    recommendations_generated += 1
                else:
                    logger.warning(f"  ✗ {ticker}: Failed to generate recommendation")

            # 5. Generate portfolio insights
            logger.info("\n💡 Generating insights...")
            insights = self.insight_generator.generate_all_insights(portfolio_id)
            logger.info(f"  ✓ Generated {len(insights)} insights")

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

            logger.info(f"\n{'='*60}")
            logger.info("✅ Processing Complete")
            logger.info(f"{'='*60}")
            logger.info(f"Tickers processed: {len(tickers)}")
            logger.info(f"Market data updated: {market_data_success}/{len(tickers)}")
            logger.info(f"Fundamentals updated: {fundamental_success}/{len(tickers)}")
            logger.info(f"Recommendations: {recommendations_generated}")
            logger.info(f"Insights: {len(insights)}")
            logger.info(f"{'='*60}\n")

            return summary

    async def process_all_portfolios(self) -> dict[str, Any]:
        """
        Process all portfolios in the system.

        Returns:
            Dict with summary of all portfolio processing
        """
        with db_session() as session:
            portfolios = session.query(Portfolio).all()

            if not portfolios:
                return {
                    "total_portfolios": 0,
                    "message": "No portfolios found",
                }

            logger.info(f"\n{'#'*60}")
            logger.info(f"BATCH JOB STARTED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'#'*60}")
            logger.info(f"Portfolios to process: {len(portfolios)}\n")

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

            logger.info(f"\n{'#'*60}")
            logger.info("BATCH JOB COMPLETED")
            logger.info(f"{'#'*60}")
            logger.info(f"Portfolios: {len(portfolios)}")
            logger.info(f"Total tickers: {total_tickers}")
            logger.info(f"Total recommendations: {total_recommendations}")
            logger.info(f"Total insights: {total_insights}")
            logger.info(f"{'#'*60}\n")

            return overall_summary

    async def run_daily_batch(self) -> dict[str, Any]:
        """
        Run the daily batch job.

        Returns:
            Dict with batch job summary
        """
        logger.info("🚀 Starting daily batch job...")
        return await self.process_all_portfolios()


async def run_batch_once() -> dict[str, Any]:
    """Convenience function to run batch job once."""
    processor = BatchProcessor()
    return await processor.run_daily_batch()


if __name__ == "__main__":
    # Allow running this module directly for testing
    asyncio.run(run_batch_once())
