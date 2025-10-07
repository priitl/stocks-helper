"""Unit tests for accounting service."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.models import (
    Account,
    AccountCategory,
    AccountType,
    ChartAccount,
    JournalEntryStatus,
    JournalEntryType,
    Portfolio,
    Transaction,
    TransactionType,
)
from src.services.accounting_service import (
    get_account_balance,
    get_next_entry_number,
    initialize_chart_of_accounts,
    record_transaction_as_journal_entry,
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
def sample_broker_account(sample_portfolio):
    """Sample broker account."""
    return Account(
        id=str(uuid4()),
        portfolio_id=sample_portfolio.id,
        name="Test Account",
        broker_source="test_broker",
        account_number="TEST123",
        base_currency="EUR",
    )


@pytest.fixture
def sample_accounts(sample_portfolio):
    """Sample chart of accounts."""
    return {
        "cash": ChartAccount(
            id=str(uuid4()),
            portfolio_id=sample_portfolio.id,
            code="1000",
            name="Cash",
            type=AccountType.ASSET,
            category=AccountCategory.CASH,
            currency="EUR",
        ),
        "investments": ChartAccount(
            id=str(uuid4()),
            portfolio_id=sample_portfolio.id,
            code="1200",
            name="Investments",
            type=AccountType.ASSET,
            category=AccountCategory.INVESTMENTS,
            currency="EUR",
        ),
        "capital": ChartAccount(
            id=str(uuid4()),
            portfolio_id=sample_portfolio.id,
            code="3000",
            name="Owner's Capital",
            type=AccountType.EQUITY,
            category=AccountCategory.CAPITAL,
            currency="EUR",
        ),
        "dividend_income": ChartAccount(
            id=str(uuid4()),
            portfolio_id=sample_portfolio.id,
            code="4000",
            name="Dividend Income",
            type=AccountType.REVENUE,
            category=AccountCategory.DIVIDEND_INCOME,
            currency="EUR",
        ),
        "interest_income": ChartAccount(
            id=str(uuid4()),
            portfolio_id=sample_portfolio.id,
            code="4100",
            name="Interest Income",
            type=AccountType.REVENUE,
            category=AccountCategory.INTEREST_INCOME,
            currency="EUR",
        ),
        "fees": ChartAccount(
            id=str(uuid4()),
            portfolio_id=sample_portfolio.id,
            code="5000",
            name="Fees",
            type=AccountType.EXPENSE,
            category=AccountCategory.FEES_AND_COMMISSIONS,
            currency="EUR",
        ),
        "taxes": ChartAccount(
            id=str(uuid4()),
            portfolio_id=sample_portfolio.id,
            code="5100",
            name="Taxes",
            type=AccountType.EXPENSE,
            category=AccountCategory.TAX_EXPENSE,
            currency="EUR",
        ),
    }


class TestInitializeChartOfAccounts:
    """Tests for initialize_chart_of_accounts function."""

    def test_initialize_chart_of_accounts_creates_accounts(self, mock_session, sample_portfolio):
        """Test that initialize_chart_of_accounts creates all standard accounts."""
        mock_session.get.return_value = sample_portfolio

        accounts = initialize_chart_of_accounts(mock_session, sample_portfolio.id)

        # Should create 11 accounts
        assert len(accounts) == 11
        assert "cash" in accounts
        assert "bank" in accounts
        assert "investments" in accounts
        assert "capital" in accounts
        assert "retained_earnings" in accounts
        assert "dividend_income" in accounts
        assert "interest_income" in accounts
        assert "capital_gains" in accounts
        assert "fees" in accounts
        assert "taxes" in accounts
        assert "capital_losses" in accounts

        # Verify accounts were added to session
        assert mock_session.add.call_count == 11
        mock_session.flush.assert_called_once()

    def test_initialize_chart_of_accounts_sets_portfolio_currency(
        self, mock_session, sample_portfolio
    ):
        """Test that accounts use portfolio's base currency."""
        mock_session.get.return_value = sample_portfolio

        accounts = initialize_chart_of_accounts(mock_session, sample_portfolio.id)

        # All accounts should have EUR currency
        for account in accounts.values():
            assert account.currency == "EUR"

    def test_initialize_chart_of_accounts_marks_system_accounts(
        self, mock_session, sample_portfolio
    ):
        """Test that all accounts are marked as system accounts."""
        mock_session.get.return_value = sample_portfolio

        accounts = initialize_chart_of_accounts(mock_session, sample_portfolio.id)

        # All accounts should be system accounts
        for account in accounts.values():
            assert account.is_system is True

    def test_initialize_chart_of_accounts_invalid_portfolio(self, mock_session):
        """Test that invalid portfolio raises error."""
        mock_session.get.return_value = None

        with pytest.raises(ValueError, match="Portfolio .* not found"):
            initialize_chart_of_accounts(mock_session, "invalid-id")


class TestGetNextEntryNumber:
    """Tests for get_next_entry_number function."""

    def test_get_next_entry_number_first_entry(self, mock_session):
        """Test that first entry gets number 1."""
        mock_session.execute.return_value.scalar.return_value = None

        entry_number = get_next_entry_number(mock_session, "portfolio-id")

        assert entry_number == 1

    def test_get_next_entry_number_sequential(self, mock_session):
        """Test that entry numbers are sequential."""
        mock_session.execute.return_value.scalar.return_value = 5

        entry_number = get_next_entry_number(mock_session, "portfolio-id")

        assert entry_number == 6


class TestRecordTransactionBuy:
    """Tests for recording BUY transactions."""

    def test_record_buy_transaction_creates_journal_entry(
        self, mock_session, sample_broker_account, sample_accounts
    ):
        """Test recording BUY transaction."""
        transaction = Transaction(
            id=str(uuid4()),
            account_id=sample_broker_account.id,
            type=TransactionType.BUY,
            date=date(2025, 1, 1),
            quantity=Decimal("10"),
            price=Decimal("150.00"),
            fees=Decimal("5.00"),
            amount=Decimal("1505.00"),
            currency="EUR",
            debit_credit="D",
        )

        # Mock account lookup
        mock_session.get.side_effect = [sample_broker_account]

        # Mock entry number lookup
        mock_session.execute.return_value.scalar.return_value = 0

        entry = record_transaction_as_journal_entry(mock_session, transaction, sample_accounts)

        # Verify journal entry was created
        assert entry.type == JournalEntryType.TRANSACTION
        assert entry.status == JournalEntryStatus.POSTED
        assert entry.entry_number == 1

        # Verify 2 journal lines were added (DR Investments, CR Cash)
        assert mock_session.add.call_count >= 3  # entry + 2 lines + reconciliation

    def test_record_buy_transaction_missing_quantity(
        self, mock_session, sample_broker_account, sample_accounts
    ):
        """Test that BUY transaction without quantity raises error."""
        transaction = Transaction(
            id=str(uuid4()),
            account_id=sample_broker_account.id,
            type=TransactionType.BUY,
            date=date(2025, 1, 1),
            quantity=None,
            price=Decimal("150.00"),
            fees=Decimal("5.00"),
            amount=Decimal("1505.00"),
            currency="EUR",
            debit_credit="D",
        )

        mock_session.get.side_effect = [sample_broker_account]
        mock_session.execute.return_value.scalar.return_value = 0

        with pytest.raises(ValueError, match="missing quantity or price"):
            record_transaction_as_journal_entry(mock_session, transaction, sample_accounts)


class TestRecordTransactionSell:
    """Tests for recording SELL transactions."""

    def test_record_sell_transaction_creates_journal_entry(
        self, mock_session, sample_broker_account, sample_accounts
    ):
        """Test recording SELL transaction."""
        transaction = Transaction(
            id=str(uuid4()),
            account_id=sample_broker_account.id,
            type=TransactionType.SELL,
            date=date(2025, 1, 1),
            quantity=Decimal("10"),
            price=Decimal("160.00"),
            fees=Decimal("5.00"),
            amount=Decimal("1595.00"),
            currency="EUR",
            debit_credit="K",
        )

        mock_session.get.side_effect = [sample_broker_account]
        mock_session.execute.return_value.scalar.return_value = 0

        entry = record_transaction_as_journal_entry(mock_session, transaction, sample_accounts)

        assert entry.type == JournalEntryType.TRANSACTION
        assert entry.status == JournalEntryStatus.POSTED


class TestRecordTransactionDividend:
    """Tests for recording DIVIDEND transactions."""

    def test_record_dividend_transaction_without_tax(
        self, mock_session, sample_broker_account, sample_accounts
    ):
        """Test recording dividend without withholding tax."""
        transaction = Transaction(
            id=str(uuid4()),
            account_id=sample_broker_account.id,
            type=TransactionType.DIVIDEND,
            date=date(2025, 1, 1),
            amount=Decimal("100.00"),
            tax_amount=None,
            currency="EUR",
            debit_credit="K",
        )

        mock_session.get.side_effect = [sample_broker_account]
        mock_session.execute.return_value.scalar.return_value = 0

        entry = record_transaction_as_journal_entry(mock_session, transaction, sample_accounts)

        assert entry.type == JournalEntryType.TRANSACTION
        # Should have 2 lines: DR Cash, CR Dividend Income
        assert mock_session.add.call_count >= 3

    def test_record_dividend_transaction_with_tax(
        self, mock_session, sample_broker_account, sample_accounts
    ):
        """Test recording dividend with withholding tax."""
        transaction = Transaction(
            id=str(uuid4()),
            account_id=sample_broker_account.id,
            type=TransactionType.DIVIDEND,
            date=date(2025, 1, 1),
            amount=Decimal("100.00"),
            tax_amount=Decimal("15.00"),
            currency="EUR",
            debit_credit="K",
        )

        mock_session.get.side_effect = [sample_broker_account]
        mock_session.execute.return_value.scalar.return_value = 0

        entry = record_transaction_as_journal_entry(mock_session, transaction, sample_accounts)

        assert entry.type == JournalEntryType.TRANSACTION
        # Should have 3 lines: DR Cash (net), DR Tax Expense, CR Dividend Income
        assert mock_session.add.call_count >= 4


class TestRecordTransactionInterest:
    """Tests for recording INTEREST transactions."""

    def test_record_interest_transaction(
        self, mock_session, sample_broker_account, sample_accounts
    ):
        """Test recording interest income."""
        transaction = Transaction(
            id=str(uuid4()),
            account_id=sample_broker_account.id,
            type=TransactionType.INTEREST,
            date=date(2025, 1, 1),
            amount=Decimal("50.00"),
            currency="EUR",
        )

        mock_session.get.side_effect = [sample_broker_account]
        mock_session.execute.return_value.scalar.return_value = 0

        entry = record_transaction_as_journal_entry(mock_session, transaction, sample_accounts)

        assert entry.type == JournalEntryType.TRANSACTION
        # Should have 2 lines: DR Cash, CR Interest Income
        assert mock_session.add.call_count >= 3


class TestRecordTransactionDeposit:
    """Tests for recording DEPOSIT transactions."""

    def test_record_deposit_transaction(self, mock_session, sample_broker_account, sample_accounts):
        """Test recording deposit."""
        transaction = Transaction(
            id=str(uuid4()),
            account_id=sample_broker_account.id,
            type=TransactionType.DEPOSIT,
            date=date(2025, 1, 1),
            amount=Decimal("1000.00"),
            currency="EUR",
        )

        mock_session.get.side_effect = [sample_broker_account]
        mock_session.execute.return_value.scalar.return_value = 0

        entry = record_transaction_as_journal_entry(mock_session, transaction, sample_accounts)

        assert entry.type == JournalEntryType.TRANSACTION
        # Should have 2 lines: DR Cash, CR Owner's Capital
        assert mock_session.add.call_count >= 3


class TestRecordTransactionWithdrawal:
    """Tests for recording WITHDRAWAL transactions."""

    def test_record_withdrawal_transaction(
        self, mock_session, sample_broker_account, sample_accounts
    ):
        """Test recording withdrawal."""
        transaction = Transaction(
            id=str(uuid4()),
            account_id=sample_broker_account.id,
            type=TransactionType.WITHDRAWAL,
            date=date(2025, 1, 1),
            amount=Decimal("500.00"),
            currency="EUR",
        )

        mock_session.get.side_effect = [sample_broker_account]
        mock_session.execute.return_value.scalar.return_value = 0

        entry = record_transaction_as_journal_entry(mock_session, transaction, sample_accounts)

        assert entry.type == JournalEntryType.TRANSACTION
        # Should have 2 lines: DR Owner's Capital, CR Cash
        assert mock_session.add.call_count >= 3


class TestRecordTransactionFee:
    """Tests for recording FEE transactions."""

    def test_record_fee_transaction(self, mock_session, sample_broker_account, sample_accounts):
        """Test recording fee."""
        transaction = Transaction(
            id=str(uuid4()),
            account_id=sample_broker_account.id,
            type=TransactionType.FEE,
            date=date(2025, 1, 1),
            amount=Decimal("10.00"),
            currency="EUR",
        )

        mock_session.get.side_effect = [sample_broker_account]
        mock_session.execute.return_value.scalar.return_value = 0

        entry = record_transaction_as_journal_entry(mock_session, transaction, sample_accounts)

        assert entry.type == JournalEntryType.TRANSACTION
        # Should have 2 lines: DR Fees Expense, CR Cash
        assert mock_session.add.call_count >= 3


class TestRecordTransactionTax:
    """Tests for recording TAX transactions."""

    def test_record_tax_transaction(self, mock_session, sample_broker_account, sample_accounts):
        """Test recording tax payment."""
        transaction = Transaction(
            id=str(uuid4()),
            account_id=sample_broker_account.id,
            type=TransactionType.TAX,
            date=date(2025, 1, 1),
            amount=Decimal("25.00"),
            currency="EUR",
        )

        mock_session.get.side_effect = [sample_broker_account]
        mock_session.execute.return_value.scalar.return_value = 0

        entry = record_transaction_as_journal_entry(mock_session, transaction, sample_accounts)

        assert entry.type == JournalEntryType.TRANSACTION
        # Should have 2 lines: DR Tax Expense, CR Cash
        assert mock_session.add.call_count >= 3


class TestGetAccountBalance:
    """Tests for get_account_balance function."""

    def test_get_account_balance_asset_account(self, mock_session):
        """Test calculating balance for asset account."""
        from src.models import JournalLine

        account = ChartAccount(
            id=str(uuid4()),
            portfolio_id=str(uuid4()),
            code="1000",
            name="Cash",
            type=AccountType.ASSET,
            category=AccountCategory.CASH,
            currency="EUR",
        )

        # Create sample journal lines
        lines = [
            JournalLine(
                id=str(uuid4()),
                journal_entry_id=str(uuid4()),
                account_id=account.id,
                line_number=1,
                debit_amount=Decimal("1000.00"),
                credit_amount=Decimal("0"),
                currency="EUR",
            ),
            JournalLine(
                id=str(uuid4()),
                journal_entry_id=str(uuid4()),
                account_id=account.id,
                line_number=1,
                debit_amount=Decimal("0"),
                credit_amount=Decimal("300.00"),
                currency="EUR",
            ),
        ]

        # Mock account retrieval
        mock_session.get.return_value = account

        # Mock journal lines query
        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        mock_scalars.all.return_value = lines

        balance = get_account_balance(mock_session, account.id)

        # Asset account: DR - CR = 1000 - 300 = 700
        assert balance == Decimal("700.00")

    def test_get_account_balance_revenue_account(self, mock_session):
        """Test calculating balance for revenue account."""
        from src.models import JournalLine

        account = ChartAccount(
            id=str(uuid4()),
            portfolio_id=str(uuid4()),
            code="4000",
            name="Dividend Income",
            type=AccountType.REVENUE,
            category=AccountCategory.DIVIDEND_INCOME,
            currency="EUR",
        )

        lines = [
            JournalLine(
                id=str(uuid4()),
                journal_entry_id=str(uuid4()),
                account_id=account.id,
                line_number=1,
                debit_amount=Decimal("0"),
                credit_amount=Decimal("500.00"),
                currency="EUR",
            ),
        ]

        mock_session.get.return_value = account

        mock_execute = MagicMock()
        mock_scalars = MagicMock()
        mock_session.execute.return_value = mock_execute
        mock_execute.scalars.return_value = mock_scalars
        mock_scalars.all.return_value = lines

        balance = get_account_balance(mock_session, account.id)

        # Revenue account: CR - DR = 500 - 0 = 500
        assert balance == Decimal("500.00")

    def test_get_account_balance_invalid_account(self, mock_session):
        """Test that invalid account raises error."""
        mock_session.get.return_value = None

        with pytest.raises(ValueError, match="Account .* not found"):
            get_account_balance(mock_session, "invalid-id")
