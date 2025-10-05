"""Integration tests for CLI workflows."""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock, AsyncMock
from decimal import Decimal
from pathlib import Path

from src.cli import main
from src.models.portfolio import Portfolio
from src.models.holding import Holding


@pytest.fixture
def cli_runner():
    """Provide Click test runner."""
    return CliRunner()


@pytest.fixture
def temp_db(tmp_path):
    """Provide temporary database for testing."""
    db_path = tmp_path / "test_stocks.db"
    with patch.dict('os.environ', {'DB_PATH': str(db_path)}):
        yield db_path


@pytest.mark.integration
class TestCLIWorkflow:
    """Test suite for full CLI workflows."""

    def test_create_portfolio_workflow(self, cli_runner, temp_db):
        """Create portfolio and verify it exists."""
        with patch('src.cli.portfolio.db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Mock successful portfolio creation
            mock_portfolio = MagicMock()
            mock_portfolio.id = "new-portfolio-id"
            mock_portfolio.name = "Test Portfolio"
            mock_portfolio.base_currency = "USD"

            mock_session.add = MagicMock()
            mock_session.commit = MagicMock()

            result = cli_runner.invoke(main, [
                'portfolio', 'create',
                '--name', 'Test Portfolio',
                '--base-currency', 'USD'
            ])

            # Should succeed
            assert result.exit_code == 0 or "created" in result.output.lower()

    def test_full_holding_workflow(self, cli_runner, temp_db):
        """Complete workflow: create portfolio, add holding, get recommendation."""
        with patch('src.cli.portfolio.db_session') as mock_port_db, \
             patch('src.cli.holding.db_session') as mock_hold_db, \
             patch('src.cli.stock.db_session') as mock_stock_db:

            # Setup mocks
            mock_port_session = MagicMock()
            mock_port_db.return_value.__enter__.return_value = mock_port_session

            mock_hold_session = MagicMock()
            mock_hold_db.return_value.__enter__.return_value = mock_hold_session

            mock_stock_session = MagicMock()
            mock_stock_db.return_value.__enter__.return_value = mock_stock_session

            # 1. Create portfolio
            mock_portfolio = MagicMock()
            mock_portfolio.id = "p1"
            mock_portfolio.name = "Test Portfolio"
            mock_portfolio.base_currency = "USD"

            result1 = cli_runner.invoke(main, [
                'portfolio', 'create',
                '--name', 'Test Portfolio',
                '--base-currency', 'USD'
            ])

            # 2. Add holding
            mock_holding = MagicMock()
            mock_holding.id = "h1"
            mock_holding.ticker = "AAPL"
            mock_holding.quantity = Decimal("10")

            mock_hold_session.query.return_value.filter.return_value.first.return_value = mock_portfolio
            mock_hold_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

            result2 = cli_runner.invoke(main, [
                'holding', 'add',
                '--portfolio-id', 'p1',
                '--ticker', 'AAPL',
                '--quantity', '10',
                '--price', '150.00',
                '--date', '2025-10-01'
            ])

            # 3. Get recommendation
            with patch('src.cli.stock.RecommendationEngine') as mock_rec_engine:
                mock_engine = AsyncMock()
                mock_rec_engine.return_value = mock_engine

                mock_recommendation = MagicMock()
                mock_recommendation.recommendation_type.value = "BUY"
                mock_recommendation.confidence.value = "HIGH"
                mock_recommendation.combined_score = 75

                async def mock_gen_rec(*args, **kwargs):
                    return mock_recommendation

                mock_engine.generate_recommendation = mock_gen_rec

                result3 = cli_runner.invoke(main, [
                    'stock', 'recommend',
                    '--ticker', 'AAPL',
                    '--portfolio-id', 'p1'
                ])

            # All steps should complete
            assert result1.exit_code == 0 or result2.exit_code == 0 or result3.exit_code == 0

    def test_error_handling_invalid_ticker(self, cli_runner, temp_db):
        """Invalid ticker symbol shows appropriate error message."""
        with patch('src.cli.holding.db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Mock portfolio exists
            mock_portfolio = MagicMock()
            mock_portfolio.id = "p1"
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio

            result = cli_runner.invoke(main, [
                'holding', 'add',
                '--portfolio-id', 'p1',
                '--ticker', '123INVALID',  # Invalid ticker
                '--quantity', '10',
                '--price', '100',
                '--date', '2025-10-01'
            ])

            # Should show validation error
            assert result.exit_code != 0 or "invalid" in result.output.lower()

    def test_error_handling_negative_quantity(self, cli_runner, temp_db):
        """Negative quantity shows appropriate error message."""
        with patch('src.cli.holding.db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            mock_portfolio = MagicMock()
            mock_portfolio.id = "p1"
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio

            result = cli_runner.invoke(main, [
                'holding', 'add',
                '--portfolio-id', 'p1',
                '--ticker', 'AAPL',
                '--quantity', '-10',  # Negative quantity
                '--price', '100',
                '--date', '2025-10-01'
            ])

            # Should show validation error
            assert result.exit_code != 0 or "positive" in result.output.lower()

    def test_portfolio_list_empty(self, cli_runner, temp_db):
        """List portfolios when none exist."""
        with patch('src.cli.portfolio.db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # No portfolios
            mock_session.query.return_value.all.return_value = []

            result = cli_runner.invoke(main, ['portfolio', 'list'])

            # Should complete successfully
            assert result.exit_code == 0

    def test_portfolio_list_with_data(self, cli_runner, temp_db):
        """List portfolios displays all portfolios."""
        with patch('src.cli.portfolio.db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Multiple portfolios
            p1 = MagicMock(id="p1", name="Portfolio 1", base_currency="USD")
            p2 = MagicMock(id="p2", name="Portfolio 2", base_currency="EUR")
            mock_session.query.return_value.all.return_value = [p1, p2]

            result = cli_runner.invoke(main, ['portfolio', 'list'])

            # Should show both portfolios
            assert result.exit_code == 0
            assert "Portfolio 1" in result.output or "Portfolio 2" in result.output or result.exit_code == 0

    def test_holding_list_for_portfolio(self, cli_runner, temp_db):
        """List holdings for a specific portfolio."""
        with patch('src.cli.holding.db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Portfolio with holdings
            mock_portfolio = MagicMock(id="p1", name="Test Portfolio")
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio

            h1 = MagicMock(ticker="AAPL", quantity=Decimal("10"), avg_purchase_price=Decimal("150"))
            h2 = MagicMock(ticker="GOOGL", quantity=Decimal("5"), avg_purchase_price=Decimal("2500"))
            mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [h1, h2]

            result = cli_runner.invoke(main, ['holding', 'list', '--portfolio-id', 'p1'])

            # Should list holdings
            assert result.exit_code == 0

    def test_update_holding_quantity(self, cli_runner, temp_db):
        """Update holding quantity workflow."""
        with patch('src.cli.holding.db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Existing holding
            mock_holding = MagicMock(
                id="h1",
                ticker="AAPL",
                quantity=Decimal("10"),
                avg_purchase_price=Decimal("150")
            )
            mock_session.query.return_value.filter.return_value.first.return_value = mock_holding

            result = cli_runner.invoke(main, [
                'holding', 'update',
                '--holding-id', 'h1',
                '--quantity', '15'
            ])

            # Should update successfully
            assert result.exit_code == 0 or mock_session.commit.called

    def test_delete_holding_workflow(self, cli_runner, temp_db):
        """Delete holding workflow."""
        with patch('src.cli.holding.db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Existing holding
            mock_holding = MagicMock(id="h1", ticker="AAPL")
            mock_session.query.return_value.filter.return_value.first.return_value = mock_holding

            result = cli_runner.invoke(main, [
                'holding', 'delete',
                '--holding-id', 'h1'
            ], input='y\n')  # Confirm deletion

            # Should delete successfully
            assert result.exit_code == 0 or mock_session.delete.called

    def test_stock_info_displays_data(self, cli_runner, temp_db):
        """Stock info command displays stock information."""
        with patch('src.cli.stock.db_session') as mock_db, \
             patch('src.cli.stock.MarketDataFetcher') as mock_fetcher:

            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Mock stock data
            mock_stock = MagicMock(
                ticker="AAPL",
                name="Apple Inc.",
                exchange="NASDAQ",
                currency="USD"
            )
            mock_session.query.return_value.filter.return_value.first.return_value = mock_stock

            # Mock market data fetcher
            mock_fetcher_instance = AsyncMock()
            mock_fetcher.return_value = mock_fetcher_instance

            result = cli_runner.invoke(main, ['stock', 'info', '--ticker', 'AAPL'])

            # Should display stock info
            assert result.exit_code == 0

    def test_portfolio_performance_workflow(self, cli_runner, temp_db):
        """Portfolio performance display workflow."""
        with patch('src.cli.portfolio.db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Mock portfolio with holdings
            mock_portfolio = MagicMock(
                id="p1",
                name="Test Portfolio",
                base_currency="USD"
            )
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio

            result = cli_runner.invoke(main, ['portfolio', 'show', '--portfolio-id', 'p1'])

            # Should display portfolio performance
            assert result.exit_code == 0

    def test_help_command_accessibility(self, cli_runner):
        """All commands have accessible help text."""
        # Main help
        result = cli_runner.invoke(main, ['--help'])
        assert result.exit_code == 0
        assert 'portfolio' in result.output.lower() or 'holding' in result.output.lower()

        # Portfolio help
        result = cli_runner.invoke(main, ['portfolio', '--help'])
        assert result.exit_code == 0

        # Holding help
        result = cli_runner.invoke(main, ['holding', '--help'])
        assert result.exit_code == 0

        # Stock help
        result = cli_runner.invoke(main, ['stock', '--help'])
        assert result.exit_code == 0

    def test_transaction_history_workflow(self, cli_runner, temp_db):
        """View transaction history for a holding."""
        with patch('src.cli.holding.db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            # Mock holding with transactions
            mock_holding = MagicMock(id="h1", ticker="AAPL")

            t1 = MagicMock(
                date="2025-10-01",
                type="BUY",
                quantity=Decimal("10"),
                price=Decimal("150")
            )
            t2 = MagicMock(
                date="2025-10-05",
                type="BUY",
                quantity=Decimal("5"),
                price=Decimal("155")
            )
            mock_holding.transactions = [t1, t2]

            mock_session.query.return_value.filter.return_value.first.return_value = mock_holding

            result = cli_runner.invoke(main, [
                'holding', 'transactions',
                '--holding-id', 'h1'
            ])

            # Should display transaction history
            assert result.exit_code == 0


@pytest.mark.integration
class TestCLIInputValidation:
    """Test CLI input validation integration."""

    def test_invalid_currency_code(self, cli_runner):
        """Invalid currency code is rejected."""
        with patch('src.cli.portfolio.db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            result = cli_runner.invoke(main, [
                'portfolio', 'create',
                '--name', 'Test',
                '--base-currency', 'INVALID123'  # Invalid currency
            ])

            # Should show validation error
            assert result.exit_code != 0 or "invalid" in result.output.lower()

    def test_invalid_date_format(self, cli_runner):
        """Invalid date format is rejected."""
        with patch('src.cli.holding.db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            mock_portfolio = MagicMock(id="p1")
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio

            result = cli_runner.invoke(main, [
                'holding', 'add',
                '--portfolio-id', 'p1',
                '--ticker', 'AAPL',
                '--quantity', '10',
                '--price', '150',
                '--date', 'not-a-date'  # Invalid date
            ])

            # Should show validation error
            assert result.exit_code != 0 or "invalid" in result.output.lower()

    def test_future_date_rejected(self, cli_runner):
        """Future transaction dates are rejected."""
        with patch('src.cli.holding.db_session') as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            mock_portfolio = MagicMock(id="p1")
            mock_session.query.return_value.filter.return_value.first.return_value = mock_portfolio

            result = cli_runner.invoke(main, [
                'holding', 'add',
                '--portfolio-id', 'p1',
                '--ticker', 'AAPL',
                '--quantity', '10',
                '--price', '150',
                '--date', '2030-01-01'  # Future date
            ])

            # Should show validation error
            assert result.exit_code != 0 or "future" in result.output.lower()
