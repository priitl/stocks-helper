"""Unit tests for tax reporting service."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.models import (
    Holding,
    Security,
    Transaction,
    TransactionType,
)
from src.services.tax_reporting import (
    CostBasisMethod,
    TaxLot,
    calculate_capital_gains,
    get_annual_tax_summary,
    get_dividend_income,
    get_tax_lots,
)


@pytest.fixture
def mock_session():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def sample_security():
    """Sample security for testing."""
    return Security(
        id=str(uuid4()),
        ticker="AAPL",
        name="Apple Inc",
    )


@pytest.fixture
def sample_holding(sample_security):
    """Sample holding for testing."""
    return Holding(
        id=str(uuid4()),
        security_id=sample_security.id,
        quantity=Decimal("100"),
        avg_purchase_price=Decimal("150.00"),
    )


@pytest.fixture
def sample_buy_transaction():
    """Sample buy transaction."""
    return Transaction(
        id=str(uuid4()),
        type=TransactionType.BUY,
        date=date(2024, 1, 1),
        quantity=Decimal("100"),
        price=Decimal("150.00"),
        fees=Decimal("5.00"),
        currency="USD",
    )


@pytest.fixture
def sample_sell_transaction():
    """Sample sell transaction."""
    return Transaction(
        id=str(uuid4()),
        type=TransactionType.SELL,
        date=date(2025, 1, 1),
        quantity=Decimal("50"),
        price=Decimal("200.00"),
        fees=Decimal("5.00"),
        currency="USD",
    )


class TestGetTaxLots:
    """Tests for get_tax_lots function."""

    def test_get_tax_lots_returns_fifo_order(
        self, mock_session, sample_security, sample_buy_transaction
    ):
        """Test that tax lots are returned in FIFO order."""
        # Create multiple buy transactions
        buy1 = Transaction(
            id=str(uuid4()),
            type=TransactionType.BUY,
            date=date(2024, 1, 1),
            quantity=Decimal("100"),
            price=Decimal("150.00"),
            fees=Decimal("5.00"),
            currency="USD",
        )
        buy2 = Transaction(
            id=str(uuid4()),
            type=TransactionType.BUY,
            date=date(2024, 6, 1),
            quantity=Decimal("50"),
            price=Decimal("160.00"),
            fees=Decimal("3.00"),
            currency="USD",
        )

        # Mock queries
        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        # First query returns buy transactions, second returns empty sell list
        mock_scalars.all.side_effect = [[buy1, buy2], []]

        lots = get_tax_lots(mock_session, sample_security.id)

        assert len(lots) == 2
        assert lots[0].quantity == Decimal("100")
        assert lots[1].quantity == Decimal("50")
        assert lots[0].price_per_share == Decimal("150.00")
        assert lots[1].price_per_share == Decimal("160.00")

    def test_get_tax_lots_reduces_by_sales(self, mock_session, sample_security):
        """Test that tax lots are reduced by sell transactions."""
        buy_txn = Transaction(
            id=str(uuid4()),
            type=TransactionType.BUY,
            date=date(2024, 1, 1),
            quantity=Decimal("100"),
            price=Decimal("150.00"),
            fees=Decimal("5.00"),
            currency="USD",
        )
        sell_txn = Transaction(
            id=str(uuid4()),
            type=TransactionType.SELL,
            date=date(2024, 6, 1),
            quantity=Decimal("30"),
            price=Decimal("200.00"),
            fees=Decimal("3.00"),
            currency="USD",
        )

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        mock_scalars.all.side_effect = [[buy_txn], [sell_txn]]

        lots = get_tax_lots(mock_session, sample_security.id)

        # Should have one lot with remaining quantity of 70 (100 - 30)
        assert len(lots) == 1
        assert lots[0].remaining_quantity == Decimal("70")

    def test_get_tax_lots_with_as_of_date(self, mock_session, sample_security):
        """Test get_tax_lots with as_of_date filter."""
        buy_txn = Transaction(
            id=str(uuid4()),
            type=TransactionType.BUY,
            date=date(2024, 1, 1),
            quantity=Decimal("100"),
            price=Decimal("150.00"),
            fees=Decimal("5.00"),
            currency="USD",
        )

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        mock_scalars.all.side_effect = [[buy_txn], []]

        lots = get_tax_lots(mock_session, sample_security.id, as_of_date=date(2024, 6, 1))

        # Should return lots up to the as_of_date
        assert len(lots) == 1

    def test_get_tax_lots_skips_invalid_data(self, mock_session, sample_security):
        """Test that tax lots skip transactions with missing quantity/price."""
        buy_invalid = Transaction(
            id=str(uuid4()),
            type=TransactionType.BUY,
            date=date(2024, 1, 1),
            quantity=None,  # Missing quantity
            price=Decimal("150.00"),
            fees=Decimal("5.00"),
            currency="USD",
        )

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        mock_scalars.all.side_effect = [[buy_invalid], []]

        lots = get_tax_lots(mock_session, sample_security.id)

        # Should skip invalid transaction
        assert len(lots) == 0


class TestCalculateCapitalGains:
    """Tests for calculate_capital_gains function."""

    def test_calculate_capital_gains_fifo(
        self, mock_session, sample_holding, sample_security, sample_sell_transaction
    ):
        """Test capital gains calculation using FIFO method."""
        # Create tax lots
        buy1 = Transaction(
            id=str(uuid4()),
            type=TransactionType.BUY,
            date=date(2024, 1, 1),
            quantity=Decimal("100"),
            price=Decimal("150.00"),
            fees=Decimal("5.00"),
            currency="USD",
        )

        mock_session.get.side_effect = [sample_holding, sample_security]

        # Mock get_tax_lots to return a lot
        with patch("src.services.tax_reporting.get_tax_lots") as mock_get_lots:
            tax_lot = TaxLot(
                transaction_id=buy1.id,
                purchase_date=buy1.date,
                quantity=buy1.quantity,
                price_per_share=buy1.price,
                remaining_quantity=buy1.quantity,
                cost_basis=(buy1.quantity * buy1.price) + buy1.fees,
            )
            mock_get_lots.return_value = [tax_lot]

            # Create sell transaction
            sell_txn = Transaction(
                id=str(uuid4()),
                type=TransactionType.SELL,
                date=date(2025, 1, 1),
                quantity=Decimal("50"),
                price=Decimal("200.00"),
                fees=Decimal("5.00"),
                currency="USD",
            )

            result = calculate_capital_gains(
                mock_session,
                sample_holding.id,
                sell_txn,
                CostBasisMethod.FIFO,
            )

            # Proceeds: 50 * 200 - 5 = 9995
            # Cost basis: (50/100) * 15005 = 7502.50
            # Gain: 9995 - 7502.50 = 2492.50
            assert result.quantity_sold == Decimal("50")
            assert result.proceeds == Decimal("9995.00")
            assert result.gain_loss > 0  # Should be a gain
            assert result.is_long_term is True  # Held > 365 days

    def test_calculate_capital_gains_short_term(
        self, mock_session, sample_holding, sample_security
    ):
        """Test short-term capital gains (held <= 365 days)."""
        buy1 = Transaction(
            id=str(uuid4()),
            type=TransactionType.BUY,
            date=date(2024, 6, 1),
            quantity=Decimal("100"),
            price=Decimal("150.00"),
            fees=Decimal("5.00"),
            currency="USD",
        )

        mock_session.get.side_effect = [sample_holding, sample_security]

        with patch("src.services.tax_reporting.get_tax_lots") as mock_get_lots:
            tax_lot = TaxLot(
                transaction_id=buy1.id,
                purchase_date=buy1.date,
                quantity=buy1.quantity,
                price_per_share=buy1.price,
                remaining_quantity=buy1.quantity,
                cost_basis=(buy1.quantity * buy1.price) + buy1.fees,
            )
            mock_get_lots.return_value = [tax_lot]

            sell_txn = Transaction(
                id=str(uuid4()),
                type=TransactionType.SELL,
                date=date(2024, 12, 1),  # Only 6 months later
                quantity=Decimal("50"),
                price=Decimal("200.00"),
                fees=Decimal("5.00"),
                currency="USD",
            )

            result = calculate_capital_gains(
                mock_session,
                sample_holding.id,
                sell_txn,
                CostBasisMethod.FIFO,
            )

            assert result.is_long_term is False  # Held <= 365 days
            assert result.holding_period_days < 365

    def test_calculate_capital_gains_average_cost(
        self, mock_session, sample_holding, sample_security
    ):
        """Test capital gains using average cost method."""
        mock_session.get.side_effect = [sample_holding, sample_security]

        with patch("src.services.tax_reporting.get_tax_lots") as mock_get_lots:
            # Two lots with different prices
            lot1 = TaxLot(
                transaction_id=str(uuid4()),
                purchase_date=date(2024, 1, 1),
                quantity=Decimal("100"),
                price_per_share=Decimal("150.00"),
                remaining_quantity=Decimal("100"),
                cost_basis=Decimal("15005.00"),
            )
            lot2 = TaxLot(
                transaction_id=str(uuid4()),
                purchase_date=date(2024, 6, 1),
                quantity=Decimal("100"),
                price_per_share=Decimal("160.00"),
                remaining_quantity=Decimal("100"),
                cost_basis=Decimal("16003.00"),
            )
            mock_get_lots.return_value = [lot1, lot2]

            sell_txn = Transaction(
                id=str(uuid4()),
                type=TransactionType.SELL,
                date=date(2025, 1, 1),
                quantity=Decimal("100"),
                price=Decimal("200.00"),
                fees=Decimal("5.00"),
                currency="USD",
            )

            result = calculate_capital_gains(
                mock_session,
                sample_holding.id,
                sell_txn,
                CostBasisMethod.AVERAGE,
            )

            # Average cost should be used
            assert result.quantity_sold == Decimal("100")
            assert len(result.tax_lots_used) == 1  # Virtual average lot

    def test_calculate_capital_gains_missing_data(
        self, mock_session, sample_holding, sample_security
    ):
        """Test that missing quantity/price raises ValueError."""
        mock_session.get.side_effect = [sample_holding, sample_security]

        with patch("src.services.tax_reporting.get_tax_lots") as mock_get_lots:
            mock_get_lots.return_value = []

            sell_txn = Transaction(
                id=str(uuid4()),
                type=TransactionType.SELL,
                date=date(2025, 1, 1),
                quantity=None,  # Missing quantity
                price=Decimal("200.00"),
                fees=Decimal("5.00"),
                currency="USD",
            )

            with pytest.raises(ValueError, match="missing quantity or price"):
                calculate_capital_gains(
                    mock_session,
                    sample_holding.id,
                    sell_txn,
                    CostBasisMethod.FIFO,
                )


class TestGetDividendIncome:
    """Tests for get_dividend_income function."""

    def test_get_dividend_income_returns_list(self, mock_session):
        """Test getting dividend income for a period."""
        dividend_txn = Transaction(
            id=str(uuid4()),
            type=TransactionType.DIVIDEND,
            date=date(2024, 3, 15),
            amount=Decimal("100.00"),
            tax_amount=Decimal("15.00"),
            currency="USD",
        )
        security = Security(id=str(uuid4()), ticker="AAPL", name="Apple Inc")

        # Mock execute().all()
        mock_execute = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.all.return_value = [(dividend_txn, security)]

        results = get_dividend_income(
            mock_session,
            "portfolio-id",
            date(2024, 1, 1),
            date(2024, 12, 31),
        )

        assert len(results) == 1
        assert results[0].security_id == security.id
        assert results[0].security_name == "Apple Inc"
        assert results[0].gross_amount == Decimal("100.00")
        assert results[0].withholding_tax == Decimal("15.00")
        assert results[0].net_amount == Decimal("85.00")

    def test_get_dividend_income_no_tax(self, mock_session):
        """Test dividend income without withholding tax."""
        dividend_txn = Transaction(
            id=str(uuid4()),
            type=TransactionType.DIVIDEND,
            date=date(2024, 3, 15),
            amount=Decimal("100.00"),
            tax_amount=None,  # No tax withheld
            currency="USD",
        )
        security = Security(id=str(uuid4()), ticker="AAPL", name="Apple Inc")

        mock_execute = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.all.return_value = [(dividend_txn, security)]

        results = get_dividend_income(
            mock_session,
            "portfolio-id",
            date(2024, 1, 1),
            date(2024, 12, 31),
        )

        assert len(results) == 1
        assert results[0].withholding_tax == Decimal("0")
        assert results[0].net_amount == Decimal("100.00")


class TestGetAnnualTaxSummary:
    """Tests for get_annual_tax_summary function."""

    def test_get_annual_tax_summary_calculates_totals(self, mock_session):
        """Test annual tax summary calculates all totals correctly."""
        # Mock dividend income
        with patch("src.services.tax_reporting.get_dividend_income") as mock_div:
            from src.services.tax_reporting import DividendIncome

            mock_div.return_value = [
                DividendIncome(
                    security_id="sec-1",
                    security_name="AAPL",
                    transaction_id="txn-1",
                    payment_date=date(2024, 3, 15),
                    gross_amount=Decimal("100.00"),
                    withholding_tax=Decimal("15.00"),
                    net_amount=Decimal("85.00"),
                    currency="USD",
                )
            ]

            # Mock sell transactions (empty)
            mock_execute = MagicMock()
            mock_scalars = MagicMock()
            mock_session.execute.return_value = mock_execute
            mock_execute.scalars.return_value = mock_scalars
            # Returns: sell_txns, interest_txns, fee_txns, tax_txns
            mock_scalars.all.side_effect = [[], [], [], []]

            summary = get_annual_tax_summary(mock_session, "portfolio-id", 2024)

            assert summary.year == 2024
            assert summary.total_dividends == Decimal("100.00")
            assert summary.total_withholding_tax == Decimal("15.00")
            assert summary.short_term_gains == Decimal("0")
            assert summary.long_term_gains == Decimal("0")
            assert summary.interest_income == Decimal("0")
            assert summary.fees_paid == Decimal("0")
            assert summary.tax_paid == Decimal("0")

    def test_get_annual_tax_summary_with_capital_gains(self, mock_session):
        """Test annual tax summary includes capital gains."""
        with patch("src.services.tax_reporting.get_dividend_income") as mock_div:
            mock_div.return_value = []

            # Mock sell transaction
            sell_txn = Transaction(
                id=str(uuid4()),
                type=TransactionType.SELL,
                date=date(2024, 6, 1),
                quantity=Decimal("50"),
                price=Decimal("200.00"),
                fees=Decimal("5.00"),
                currency="USD",
            )
            sell_txn.holding_id = "holding-1"

            mock_execute = MagicMock()
            mock_scalars = MagicMock()
            mock_session.execute.return_value = mock_execute
            mock_execute.scalars.return_value = mock_scalars
            mock_scalars.all.side_effect = [
                [sell_txn],  # sell transactions
                [],  # interest
                [],  # fees
                [],  # tax
            ]

            # Mock capital gains calculation
            with patch("src.services.tax_reporting.calculate_capital_gains") as mock_calc:
                from src.services.tax_reporting import CapitalGain

                mock_calc.return_value = CapitalGain(
                    security_id="sec-1",
                    security_name="AAPL",
                    sell_transaction_id=sell_txn.id,
                    sell_date=sell_txn.date,
                    quantity_sold=Decimal("50"),
                    proceeds=Decimal("9995.00"),
                    cost_basis=Decimal("7500.00"),
                    gain_loss=Decimal("2495.00"),
                    holding_period_days=400,
                    is_long_term=True,
                    tax_lots_used=[],
                )

                summary = get_annual_tax_summary(mock_session, "portfolio-id", 2024)

                assert summary.long_term_gains == Decimal("2495.00")
                assert summary.total_capital_gains == Decimal("2495.00")

    def test_get_annual_tax_summary_with_all_income_types(self, mock_session):
        """Test annual tax summary with all income types."""
        with patch("src.services.tax_reporting.get_dividend_income") as mock_div:
            from src.services.tax_reporting import DividendIncome

            mock_div.return_value = [
                DividendIncome(
                    security_id="sec-1",
                    security_name="AAPL",
                    transaction_id="txn-1",
                    payment_date=date(2024, 3, 15),
                    gross_amount=Decimal("100.00"),
                    withholding_tax=Decimal("15.00"),
                    net_amount=Decimal("85.00"),
                    currency="USD",
                )
            ]

            # Mock various transaction types
            interest_txn = Transaction(
                id=str(uuid4()),
                type=TransactionType.INTEREST,
                date=date(2024, 6, 1),
                amount=Decimal("50.00"),
                currency="USD",
            )
            fee_txn = Transaction(
                id=str(uuid4()),
                type=TransactionType.FEE,
                date=date(2024, 7, 1),
                amount=Decimal("10.00"),
                currency="USD",
            )
            tax_txn = Transaction(
                id=str(uuid4()),
                type=TransactionType.TAX,
                date=date(2024, 8, 1),
                amount=Decimal("20.00"),
                currency="USD",
            )

            mock_execute = MagicMock()
            mock_scalars = MagicMock()
            mock_session.execute.return_value = mock_execute
            mock_execute.scalars.return_value = mock_scalars
            mock_scalars.all.side_effect = [
                [],  # sell
                [interest_txn],
                [fee_txn],
                [tax_txn],
            ]

            summary = get_annual_tax_summary(mock_session, "portfolio-id", 2024)

            assert summary.total_dividends == Decimal("100.00")
            assert summary.interest_income == Decimal("50.00")
            assert summary.fees_paid == Decimal("10.00")
            assert summary.tax_paid == Decimal("20.00")
