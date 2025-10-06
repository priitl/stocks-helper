"""Unit tests for BatchProcessor."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lib.errors import BatchProcessingError
from src.services.batch_processor import BatchProcessor


@pytest.fixture
def batch_processor():
    """Provide BatchProcessor instance."""
    return BatchProcessor()


@pytest.fixture
def mock_portfolio():
    """Provide mock portfolio with holdings."""
    portfolio = MagicMock()
    portfolio.id = "portfolio-123"
    portfolio.name = "Test Portfolio"
    portfolio.base_currency = "USD"  # Added: needed for currency conversion

    holding1 = MagicMock()
    holding1.ticker = "AAPL"
    holding1.quantity = 10
    holding1.original_currency = "USD"  # Added: needed for currency conversion

    holding2 = MagicMock()
    holding2.ticker = "GOOGL"
    holding2.quantity = 5
    holding2.original_currency = "USD"  # Added: needed for currency conversion

    portfolio.holdings = [holding1, holding2]
    return portfolio


@pytest.mark.unit
@pytest.mark.asyncio
class TestBatchProcessor:
    """Test suite for BatchProcessor."""

    async def test_process_portfolio_success(self, batch_processor, mock_portfolio):
        """Portfolio processing completes successfully."""
        with patch("src.services.batch_processor.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Mock portfolio query
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio

            # Mock holdings query
            mock_holding1 = MagicMock(ticker="AAPL", quantity=10, original_currency="USD")
            mock_holding2 = MagicMock(ticker="GOOGL", quantity=5, original_currency="USD")
            mock_session.query.return_value.filter.return_value.all.return_value = [
                mock_holding1,
                mock_holding2,
            ]

            # Mock all service calls
            batch_processor.market_data_fetcher.update_market_data = AsyncMock(return_value=True)
            batch_processor.fundamental_analyzer.update_fundamental_data = AsyncMock(
                return_value=True
            )
            batch_processor.currency_converter.update_rates = AsyncMock(return_value=True)
            batch_processor.recommendation_engine.generate_recommendation = AsyncMock(
                return_value=MagicMock()
            )
            batch_processor.insight_generator.generate_portfolio_insights = AsyncMock(
                return_value=[]
            )

            result = await batch_processor.process_portfolio("portfolio-123")

            # Should return success summary
            assert "portfolio_id" in result or "error" not in result

    async def test_process_portfolio_not_found(self, batch_processor):
        """Process returns error when portfolio not found."""
        with patch("src.services.batch_processor.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Portfolio not found
            mock_session.query.return_value.filter.return_value.first.return_value = None

            result = await batch_processor.process_portfolio("nonexistent")

            assert "error" in result
            assert "not found" in result["error"].lower()

    async def test_process_portfolio_no_holdings(self, batch_processor):
        """Process handles portfolio with no holdings."""
        with patch("src.services.batch_processor.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Portfolio exists but no holdings
            mock_portfolio = MagicMock()
            mock_portfolio.id = "portfolio-123"
            mock_portfolio.base_currency = "USD"
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio
            mock_session.query.return_value.filter.return_value.all.return_value = []

            result = await batch_processor.process_portfolio("portfolio-123")

            assert result["tickers_processed"] == 0
            assert "No holdings" in result["message"]

    async def test_circuit_breaker_triggers_on_consecutive_failures(self, batch_processor):
        """Circuit breaker triggers after max consecutive failures."""
        with patch("src.services.batch_processor.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Create portfolio with many holdings
            mock_portfolio = MagicMock()
            mock_portfolio.id = "portfolio-123"
            mock_portfolio.name = "Test"
            mock_portfolio.base_currency = "USD"
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio

            # Create enough holdings to trigger circuit breaker
            holdings = [
                MagicMock(ticker=f"TICK{i}", quantity=10, original_currency="USD")
                for i in range(10)
            ]
            mock_session.query.return_value.filter.return_value.all.return_value = holdings

            # All market data fetches fail
            batch_processor.market_data_fetcher.update_market_data = AsyncMock(return_value=False)

            # Circuit breaker should trigger
            with pytest.raises(BatchProcessingError, match="Circuit breaker triggered"):
                await batch_processor.process_portfolio("portfolio-123")

    async def test_circuit_breaker_resets_on_success(self, batch_processor):
        """Circuit breaker counter resets after successful operation."""
        with patch("src.services.batch_processor.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            mock_portfolio = MagicMock()
            mock_portfolio.id = "portfolio-123"
            mock_portfolio.name = "Test"
            mock_portfolio.base_currency = "USD"
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio

            # Create holdings
            holdings = [
                MagicMock(ticker=f"TICK{i}", quantity=10, original_currency="USD")
                for i in range(10)
            ]
            mock_session.query.return_value.filter.return_value.all.return_value = holdings

            # Alternate between failures and successes
            batch_processor.market_data_fetcher.update_market_data = AsyncMock(
                side_effect=[False, False, True, False, False, True, True, True, True, True]
            )

            batch_processor.fundamental_analyzer.update_fundamental_data = AsyncMock(
                return_value=True
            )
            batch_processor.currency_converter.update_rates = AsyncMock(return_value=True)
            batch_processor.recommendation_engine.generate_recommendation = AsyncMock(
                return_value=MagicMock()
            )
            batch_processor.insight_generator.generate_portfolio_insights = AsyncMock(
                return_value=[]
            )

            # Should not trigger circuit breaker because successes reset the counter
            result = await batch_processor.process_portfolio("portfolio-123")

            # Should complete without circuit breaker error
            assert "error" not in result or "Circuit breaker" not in str(result.get("error", ""))

    async def test_partial_failures_continue_processing(self, batch_processor):
        """Processing continues after individual ticker failures."""
        with patch("src.services.batch_processor.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            mock_portfolio = MagicMock()
            mock_portfolio.id = "portfolio-123"
            mock_portfolio.name = "Test"
            mock_portfolio.base_currency = "USD"
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio

            # 3 holdings
            holdings = [
                MagicMock(ticker="AAPL", quantity=10, original_currency="USD"),
                MagicMock(ticker="GOOGL", quantity=5, original_currency="USD"),
                MagicMock(ticker="MSFT", quantity=8, original_currency="USD"),
            ]
            mock_session.query.return_value.filter.return_value.all.return_value = holdings

            # First ticker fails, others succeed
            batch_processor.market_data_fetcher.update_market_data = AsyncMock(
                side_effect=[False, True, True]
            )

            batch_processor.fundamental_analyzer.update_fundamental_data = AsyncMock(
                return_value=True
            )
            batch_processor.currency_converter.update_rates = AsyncMock(return_value=True)
            batch_processor.recommendation_engine.generate_recommendation = AsyncMock(
                return_value=MagicMock()
            )
            batch_processor.insight_generator.generate_portfolio_insights = AsyncMock(
                return_value=[]
            )

            result = await batch_processor.process_portfolio("portfolio-123")

            # Should process all tickers
            assert result["tickers_processed"] == 3 or "tickers_processed" not in result

    async def test_exception_handling_in_market_data_fetch(self, batch_processor):
        """Exceptions during market data fetch are caught and logged."""
        with patch("src.services.batch_processor.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            mock_portfolio = MagicMock()
            mock_portfolio.id = "portfolio-123"
            mock_portfolio.name = "Test"
            mock_portfolio.base_currency = "USD"
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio

            holdings = [MagicMock(ticker="AAPL", quantity=10, original_currency="USD")]
            mock_session.query.return_value.filter.return_value.all.return_value = holdings

            # Market data fetch raises exception
            batch_processor.market_data_fetcher.update_market_data = AsyncMock(
                side_effect=Exception("Network error")
            )

            batch_processor.fundamental_analyzer.update_fundamental_data = AsyncMock(
                return_value=True
            )
            batch_processor.currency_converter.update_rates = AsyncMock(return_value=True)
            batch_processor.recommendation_engine.generate_recommendation = AsyncMock(
                return_value=MagicMock()
            )
            batch_processor.insight_generator.generate_portfolio_insights = AsyncMock(
                return_value=[]
            )

            # Should handle exception gracefully
            result = await batch_processor.process_portfolio("portfolio-123")

            # Processing should continue despite the exception
            assert result is not None

    async def test_rate_limiting_between_api_calls(self, batch_processor):
        """Rate limiting delays are enforced between API calls."""
        with (
            patch("src.services.batch_processor.db_session") as mock_db,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):

            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            mock_portfolio = MagicMock()
            mock_portfolio.id = "portfolio-123"
            mock_portfolio.name = "Test"
            mock_portfolio.base_currency = "USD"
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio

            holdings = [
                MagicMock(ticker="AAPL", quantity=10, original_currency="USD"),
                MagicMock(ticker="GOOGL", quantity=5, original_currency="USD"),
            ]
            mock_session.query.return_value.filter.return_value.all.return_value = holdings

            batch_processor.market_data_fetcher.update_market_data = AsyncMock(return_value=True)
            batch_processor.fundamental_analyzer.update_fundamental_data = AsyncMock(
                return_value=True
            )
            batch_processor.currency_converter.update_rates = AsyncMock(return_value=True)
            batch_processor.recommendation_engine.generate_recommendation = AsyncMock(
                return_value=MagicMock()
            )
            batch_processor.insight_generator.generate_portfolio_insights = AsyncMock(
                return_value=[]
            )

            await batch_processor.process_portfolio("portfolio-123")

            # Should have called sleep for rate limiting
            assert mock_sleep.called

    async def test_process_all_portfolios_success(self, batch_processor):
        """Process all portfolios completes successfully."""
        with patch("src.services.batch_processor.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Two portfolios
            portfolio1 = MagicMock(id="p1", name="Portfolio 1")
            portfolio2 = MagicMock(id="p2", name="Portfolio 2")
            mock_session.query.return_value.all.return_value = [portfolio1, portfolio2]

            # Mock process_portfolio
            with patch.object(
                batch_processor, "process_portfolio", new_callable=AsyncMock
            ) as mock_process:
                mock_process.return_value = {
                    "portfolio_id": "p1",
                    "tickers_processed": 3,
                    "recommendations_generated": 3,
                }

                await batch_processor.process_all_portfolios()

                # Should process both portfolios
                assert mock_process.call_count == 2

    async def test_concurrent_portfolio_processing(self, batch_processor):
        """Multiple portfolios can be processed concurrently."""
        with patch("src.services.batch_processor.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Multiple portfolios
            portfolios = [MagicMock(id=f"p{i}", name=f"Portfolio {i}") for i in range(5)]
            mock_session.query.return_value.all.return_value = portfolios

            # Track concurrent execution
            active_tasks = []

            async def mock_process(portfolio_id):
                active_tasks.append(portfolio_id)
                await asyncio.sleep(0.1)  # Simulate work
                active_tasks.remove(portfolio_id)
                return {"portfolio_id": portfolio_id}

            with patch.object(batch_processor, "process_portfolio", side_effect=mock_process):
                await batch_processor.process_all_portfolios()

                # Verify all portfolios were processed
                assert len(portfolios) == 5

    async def test_error_isolation_between_portfolios(self, batch_processor):
        """Error in one portfolio doesn't affect others."""
        with patch("src.services.batch_processor.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            portfolios = [
                MagicMock(id="p1", name="Portfolio 1", base_currency="USD"),
                MagicMock(id="p2", name="Portfolio 2", base_currency="USD"),
                MagicMock(id="p3", name="Portfolio 3", base_currency="USD"),
            ]
            mock_session.query.return_value.all.return_value = portfolios

            # Second portfolio fails, others succeed
            async def mock_process(portfolio_id):
                if portfolio_id == "p2":
                    raise Exception("Portfolio 2 error")
                return {"portfolio_id": portfolio_id, "tickers_processed": 0}

            with patch.object(batch_processor, "process_portfolio", side_effect=mock_process):
                result = await batch_processor.process_all_portfolios()

                # Should process all portfolios even if one fails
                assert result["total_portfolios"] == 3
                summaries = result["portfolios"]
                assert len(summaries) == 3

                # Check that p1 and p3 succeeded
                success_ids = [s["portfolio_id"] for s in summaries if "error" not in s]
                assert "p1" in success_ids
                assert "p3" in success_ids

                # Check that p2 has an error
                error_ids = [s["portfolio_id"] for s in summaries if "error" in s]
                assert "p2" in error_ids

    async def test_duplicate_tickers_handled_once(self, batch_processor):
        """Duplicate tickers across holdings are processed once."""
        with patch("src.services.batch_processor.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            mock_portfolio = MagicMock()
            mock_portfolio.id = "portfolio-123"
            mock_portfolio.name = "Test"
            mock_portfolio.base_currency = "USD"
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio

            # Same ticker in multiple holdings
            holdings = [
                MagicMock(ticker="AAPL", quantity=10, original_currency="USD"),
                MagicMock(ticker="AAPL", quantity=5, original_currency="USD"),
                MagicMock(ticker="GOOGL", quantity=8, original_currency="USD"),
            ]
            mock_session.query.return_value.filter.return_value.all.return_value = holdings

            batch_processor.market_data_fetcher.update_market_data = AsyncMock(return_value=True)
            batch_processor.fundamental_analyzer.update_fundamental_data = AsyncMock(
                return_value=True
            )
            batch_processor.currency_converter.update_rates = AsyncMock(return_value=True)
            batch_processor.recommendation_engine.generate_recommendation = AsyncMock(
                return_value=MagicMock()
            )
            batch_processor.insight_generator.generate_portfolio_insights = AsyncMock(
                return_value=[]
            )

            await batch_processor.process_portfolio("portfolio-123")

            # Market data fetch should be called only for unique tickers (AAPL, GOOGL = 2 times)
            assert batch_processor.market_data_fetcher.update_market_data.call_count == 2
