"""Unit tests for ledger reporting service."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.models import (
    AccountType,
    ChartAccount,
    JournalEntry,
    JournalEntryStatus,
    JournalEntryType,
    JournalLine,
    Portfolio,
)
from src.models.chart_of_accounts import AccountCategory
from src.services.analytics.ledger_reports import (
    get_balance_sheet,
    get_general_ledger,
    get_income_statement,
    get_trial_balance,
)


@pytest.fixture
def mock_session():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def sample_portfolio():
    """Sample portfolio for testing."""
    return Portfolio(
        id=str(uuid4()),
        name="Test Portfolio",
        base_currency="EUR",
    )


@pytest.fixture
def sample_cash_account(sample_portfolio):
    """Sample cash account."""
    return ChartAccount(
        id=str(uuid4()),
        portfolio_id=sample_portfolio.id,
        code="1000",
        name="Cash",
        type=AccountType.ASSET,
        category=AccountCategory.CASH,
        currency="EUR",
    )


@pytest.fixture
def sample_revenue_account(sample_portfolio):
    """Sample revenue account."""
    return ChartAccount(
        id=str(uuid4()),
        portfolio_id=sample_portfolio.id,
        code="4000",
        name="Dividend Income",
        type=AccountType.REVENUE,
        category=AccountCategory.DIVIDEND_INCOME,
        currency="EUR",
    )


@pytest.fixture
def sample_journal_entry(sample_portfolio):
    """Sample journal entry."""
    return JournalEntry(
        id=str(uuid4()),
        portfolio_id=sample_portfolio.id,
        entry_number=1,
        entry_date=date(2025, 1, 1),
        type=JournalEntryType.TRANSACTION,
        status=JournalEntryStatus.POSTED,
        description="Test entry",
        created_by="system",
    )


class TestGetGeneralLedger:
    """Tests for get_general_ledger function."""

    def test_get_general_ledger_returns_entries(
        self, mock_session, sample_cash_account, sample_journal_entry
    ):
        """Test general ledger returns entries for an account."""
        # Create journal line
        journal_line = JournalLine(
            id=str(uuid4()),
            journal_entry_id=sample_journal_entry.id,
            account_id=sample_cash_account.id,
            line_number=1,
            debit_amount=Decimal("100.00"),
            credit_amount=Decimal("0"),
            currency="EUR",
        )

        # Mock account retrieval
        mock_session.get.return_value = sample_cash_account

        # Mock query execution
        mock_execute = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.all.return_value = [(journal_line, sample_journal_entry)]

        ledger = get_general_ledger(mock_session, sample_cash_account.id)

        assert len(ledger) == 1
        assert ledger[0].debit_amount == Decimal("100.00")
        assert ledger[0].credit_amount == Decimal("0")
        assert ledger[0].balance == Decimal("100.00")  # Debit normal balance

    def test_get_general_ledger_calculates_running_balance(
        self, mock_session, sample_cash_account, sample_journal_entry
    ):
        """Test general ledger calculates running balance correctly."""
        # Create multiple journal lines
        line1 = JournalLine(
            id=str(uuid4()),
            journal_entry_id=sample_journal_entry.id,
            account_id=sample_cash_account.id,
            line_number=1,
            debit_amount=Decimal("100.00"),
            credit_amount=Decimal("0"),
            currency="EUR",
        )
        line2 = JournalLine(
            id=str(uuid4()),
            journal_entry_id=sample_journal_entry.id,
            account_id=sample_cash_account.id,
            line_number=2,
            debit_amount=Decimal("50.00"),
            credit_amount=Decimal("0"),
            currency="EUR",
        )

        mock_session.get.return_value = sample_cash_account
        mock_execute = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.all.return_value = [
            (line1, sample_journal_entry),
            (line2, sample_journal_entry),
        ]

        ledger = get_general_ledger(mock_session, sample_cash_account.id)

        assert len(ledger) == 2
        assert ledger[0].balance == Decimal("100.00")
        assert ledger[1].balance == Decimal("150.00")  # Running balance

    def test_get_general_ledger_with_date_range(self, mock_session, sample_cash_account):
        """Test general ledger with date range filter."""
        mock_session.get.return_value = sample_cash_account
        mock_execute = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.all.return_value = []

        ledger = get_general_ledger(
            mock_session,
            sample_cash_account.id,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )

        # Should execute without error
        assert ledger == []

    def test_get_general_ledger_invalid_account(self, mock_session):
        """Test general ledger raises error for invalid account."""
        mock_session.get.return_value = None

        with pytest.raises(ValueError, match="Account .* not found"):
            get_general_ledger(mock_session, "invalid-id")


class TestGetTrialBalance:
    """Tests for get_trial_balance function."""

    def test_get_trial_balance_returns_all_accounts(
        self, mock_session, sample_portfolio, sample_cash_account, sample_revenue_account
    ):
        """Test trial balance returns all active accounts."""
        # Mock accounts query
        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        # First call returns accounts, subsequent calls return empty journal lines
        mock_scalars.all.side_effect = [
            [sample_cash_account, sample_revenue_account],
            [],  # Lines for cash account
            [],  # Lines for revenue account
        ]

        trial_balance = get_trial_balance(mock_session, sample_portfolio.id)

        assert len(trial_balance) == 2

    def test_get_trial_balance_debit_credit_columns(
        self, mock_session, sample_portfolio, sample_cash_account
    ):
        """Test trial balance puts balances in correct debit/credit columns."""
        # Cash account with debit balance
        line = JournalLine(
            id=str(uuid4()),
            journal_entry_id=str(uuid4()),
            account_id=sample_cash_account.id,
            line_number=1,
            debit_amount=Decimal("100.00"),
            credit_amount=Decimal("0"),
            currency="EUR",
        )

        # Mock session.get() for _calculate_account_balance
        mock_session.get.return_value = sample_cash_account

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        mock_scalars.all.side_effect = [
            [sample_cash_account],
            [line],  # Lines for cash account
        ]

        trial_balance = get_trial_balance(mock_session, sample_portfolio.id)

        assert len(trial_balance) == 1
        # Asset with debit balance should be in debit column
        assert trial_balance[0].debit_balance == Decimal("100.00")
        assert trial_balance[0].credit_balance == Decimal("0")

    def test_get_trial_balance_with_as_of_date(
        self, mock_session, sample_portfolio, sample_cash_account
    ):
        """Test trial balance with as_of_date parameter."""
        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        mock_scalars.all.side_effect = [
            [sample_cash_account],
            [],
        ]

        trial_balance = get_trial_balance(
            mock_session, sample_portfolio.id, as_of_date=date(2025, 6, 30)
        )

        # Should execute without error
        assert isinstance(trial_balance, list)


class TestGetIncomeStatement:
    """Tests for get_income_statement function."""

    def test_get_income_statement_calculates_net_income(
        self, mock_session, sample_portfolio, sample_revenue_account
    ):
        """Test income statement calculates net income correctly."""
        # Create expense account
        expense_account = ChartAccount(
            id=str(uuid4()),
            portfolio_id=sample_portfolio.id,
            code="5000",
            name="Fees",
            type=AccountType.EXPENSE,
            category=AccountCategory.FEES_AND_COMMISSIONS,
            currency="EUR",
        )

        # Mock revenue line
        revenue_line = JournalLine(
            id=str(uuid4()),
            journal_entry_id=str(uuid4()),
            account_id=sample_revenue_account.id,
            line_number=1,
            debit_amount=Decimal("0"),
            credit_amount=Decimal("100.00"),
            currency="EUR",
        )

        # Mock expense line
        expense_line = JournalLine(
            id=str(uuid4()),
            journal_entry_id=str(uuid4()),
            account_id=expense_account.id,
            line_number=1,
            debit_amount=Decimal("20.00"),
            credit_amount=Decimal("0"),
            currency="EUR",
        )

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        # First call returns revenue/expense accounts, then lines for each
        mock_scalars.all.side_effect = [
            [sample_revenue_account, expense_account],
            [revenue_line],  # Revenue lines
            [expense_line],  # Expense lines
        ]

        statement = get_income_statement(
            mock_session,
            sample_portfolio.id,
            date(2025, 1, 1),
            date(2025, 12, 31),
        )

        assert statement.total_revenue == Decimal("100.00")
        assert statement.total_expenses == Decimal("20.00")
        assert statement.net_income == Decimal("80.00")

    def test_get_income_statement_skips_zero_balances(
        self, mock_session, sample_portfolio, sample_revenue_account
    ):
        """Test income statement skips accounts with no activity."""
        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        mock_scalars.all.side_effect = [
            [sample_revenue_account],
            [],  # No lines for revenue account
        ]

        statement = get_income_statement(
            mock_session,
            sample_portfolio.id,
            date(2025, 1, 1),
            date(2025, 12, 31),
        )

        # Should have no revenue lines
        assert len(statement.revenue_lines) == 0
        assert statement.total_revenue == Decimal("0")

    def test_get_income_statement_date_range(self, mock_session, sample_portfolio):
        """Test income statement uses date range filter."""
        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        mock_scalars.all.return_value = []

        statement = get_income_statement(
            mock_session,
            sample_portfolio.id,
            date(2025, 1, 1),
            date(2025, 3, 31),
        )

        assert statement.start_date == date(2025, 1, 1)
        assert statement.end_date == date(2025, 3, 31)


class TestGetBalanceSheet:
    """Tests for get_balance_sheet function."""

    def test_get_balance_sheet_shows_assets_liabilities_equity(
        self, mock_session, sample_portfolio, sample_cash_account
    ):
        """Test balance sheet shows assets, liabilities, and equity."""
        # Create liability account
        liability_account = ChartAccount(
            id=str(uuid4()),
            portfolio_id=sample_portfolio.id,
            code="2000",
            name="Accounts Payable",
            type=AccountType.LIABILITY,
            category=AccountCategory.ACCOUNTS_PAYABLE,
            currency="EUR",
        )

        # Create equity account
        equity_account = ChartAccount(
            id=str(uuid4()),
            portfolio_id=sample_portfolio.id,
            code="3000",
            name="Owner's Capital",
            type=AccountType.EQUITY,
            category=AccountCategory.CAPITAL,
            currency="EUR",
        )

        # Mock asset line
        asset_line = JournalLine(
            id=str(uuid4()),
            journal_entry_id=str(uuid4()),
            account_id=sample_cash_account.id,
            line_number=1,
            debit_amount=Decimal("1000.00"),
            credit_amount=Decimal("0"),
            currency="EUR",
        )

        # Mock liability line
        liability_line = JournalLine(
            id=str(uuid4()),
            journal_entry_id=str(uuid4()),
            account_id=liability_account.id,
            line_number=1,
            debit_amount=Decimal("0"),
            credit_amount=Decimal("200.00"),
            currency="EUR",
        )

        # Mock equity line
        equity_line = JournalLine(
            id=str(uuid4()),
            journal_entry_id=str(uuid4()),
            account_id=equity_account.id,
            line_number=1,
            debit_amount=Decimal("0"),
            credit_amount=Decimal("800.00"),
            currency="EUR",
        )

        # Mock session.get() for _calculate_account_balance
        # Each account will be retrieved once per balance calculation
        mock_session.get.side_effect = [
            sample_cash_account,
            liability_account,
            equity_account,
        ]

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        mock_scalars.all.side_effect = [
            [sample_cash_account, liability_account, equity_account],
            [asset_line],  # Asset lines
            [liability_line],  # Liability lines
            [equity_line],  # Equity lines
        ]

        balance_sheet = get_balance_sheet(mock_session, sample_portfolio.id)

        assert balance_sheet.total_assets == Decimal("1000.00")
        assert balance_sheet.total_liabilities == Decimal("200.00")
        assert balance_sheet.total_equity == Decimal("800.00")
        # Accounting equation: Assets = Liabilities + Equity
        assert (
            balance_sheet.total_assets
            == balance_sheet.total_liabilities + balance_sheet.total_equity
        )

    def test_get_balance_sheet_skips_zero_balances(
        self, mock_session, sample_portfolio, sample_cash_account
    ):
        """Test balance sheet skips accounts with zero balance."""
        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        mock_scalars.all.side_effect = [
            [sample_cash_account],
            [],  # No lines, so balance is zero
        ]

        balance_sheet = get_balance_sheet(mock_session, sample_portfolio.id)

        # Should skip zero balance accounts
        assert len(balance_sheet.asset_lines) == 0
        assert balance_sheet.total_assets == Decimal("0")

    def test_get_balance_sheet_with_as_of_date(
        self, mock_session, sample_portfolio, sample_cash_account
    ):
        """Test balance sheet with as_of_date parameter."""
        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        mock_scalars.all.side_effect = [
            [sample_cash_account],
            [],
        ]

        balance_sheet = get_balance_sheet(
            mock_session, sample_portfolio.id, as_of_date=date(2025, 6, 30)
        )

        assert balance_sheet.as_of_date == date(2025, 6, 30)

    def test_get_balance_sheet_defaults_to_today(
        self, mock_session, sample_portfolio, sample_cash_account
    ):
        """Test balance sheet defaults to today if no date specified."""
        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        mock_scalars.all.side_effect = [
            [sample_cash_account],
            [],
        ]

        from datetime import date as date_class

        balance_sheet = get_balance_sheet(mock_session, sample_portfolio.id)

        # Should use today's date
        assert balance_sheet.as_of_date == date_class.today()
