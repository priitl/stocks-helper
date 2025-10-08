"""Accounting service for double-entry bookkeeping.

Handles recording transactions as journal entries following GAAP principles.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import (
    Account,
    AccountCategory,
    AccountType,
    ChartAccount,
    JournalEntry,
    JournalEntryStatus,
    JournalEntryType,
    JournalLine,
    Portfolio,
    Reconciliation,
    ReconciliationStatus,
    Transaction,
    TransactionType,
)


def initialize_chart_of_accounts(session: Session, portfolio_id: str) -> dict[str, ChartAccount]:
    """Initialize default chart of accounts for a portfolio.

    Creates standard accounts for:
    - Assets (Cash, Bank, Investments)
    - Equity (Capital, Retained Earnings)
    - Revenue (Dividends, Interest, Capital Gains)
    - Expenses (Fees, Taxes, Capital Losses)

    Args:
        session: Database session
        portfolio_id: Portfolio ID

    Returns:
        Dictionary mapping account names to ChartAccount instances
    """
    portfolio = session.get(Portfolio, portfolio_id)
    if not portfolio:
        raise ValueError(f"Portfolio {portfolio_id} not found")

    base_currency = portfolio.base_currency

    # Asset accounts
    accounts = {
        "cash": ChartAccount(
            portfolio_id=portfolio_id,
            code="1000",
            name="Cash",
            type=AccountType.ASSET,
            category=AccountCategory.CASH,
            currency=base_currency,
            is_system=True,
            description="Cash and cash equivalents",
        ),
        "bank": ChartAccount(
            portfolio_id=portfolio_id,
            code="1100",
            name="Bank Accounts",
            type=AccountType.ASSET,
            category=AccountCategory.BANK,
            currency=base_currency,
            is_system=True,
            description="Bank account balances",
        ),
        "investments": ChartAccount(
            portfolio_id=portfolio_id,
            code="1200",
            name="Investments - Securities",
            type=AccountType.ASSET,
            category=AccountCategory.INVESTMENTS,
            currency=base_currency,
            is_system=True,
            description="Stock and bond investments at cost",
        ),
        # Equity accounts
        "capital": ChartAccount(
            portfolio_id=portfolio_id,
            code="3000",
            name="Owner's Capital",
            type=AccountType.EQUITY,
            category=AccountCategory.CAPITAL,
            currency=base_currency,
            is_system=True,
            description="Initial capital contributions",
        ),
        "retained_earnings": ChartAccount(
            portfolio_id=portfolio_id,
            code="3100",
            name="Retained Earnings",
            type=AccountType.EQUITY,
            category=AccountCategory.RETAINED_EARNINGS,
            currency=base_currency,
            is_system=True,
            description="Accumulated earnings",
        ),
        # Revenue accounts
        "dividend_income": ChartAccount(
            portfolio_id=portfolio_id,
            code="4000",
            name="Dividend Income",
            type=AccountType.REVENUE,
            category=AccountCategory.DIVIDEND_INCOME,
            currency=base_currency,
            is_system=True,
            description="Dividend income from stocks",
        ),
        "interest_income": ChartAccount(
            portfolio_id=portfolio_id,
            code="4100",
            name="Interest Income",
            type=AccountType.REVENUE,
            category=AccountCategory.INTEREST_INCOME,
            currency=base_currency,
            is_system=True,
            description="Interest income from bonds and bank accounts",
        ),
        "capital_gains": ChartAccount(
            portfolio_id=portfolio_id,
            code="4200",
            name="Capital Gains",
            type=AccountType.REVENUE,
            category=AccountCategory.CAPITAL_GAINS,
            currency=base_currency,
            is_system=True,
            description="Realized capital gains from sales",
        ),
        # Expense accounts
        "fees": ChartAccount(
            portfolio_id=portfolio_id,
            code="5000",
            name="Fees and Commissions",
            type=AccountType.EXPENSE,
            category=AccountCategory.FEES_AND_COMMISSIONS,
            currency=base_currency,
            is_system=True,
            description="Trading fees and commissions",
        ),
        "taxes": ChartAccount(
            portfolio_id=portfolio_id,
            code="5100",
            name="Tax Expense",
            type=AccountType.EXPENSE,
            category=AccountCategory.TAX_EXPENSE,
            currency=base_currency,
            is_system=True,
            description="Withholding taxes and other taxes",
        ),
        "capital_losses": ChartAccount(
            portfolio_id=portfolio_id,
            code="5200",
            name="Capital Losses",
            type=AccountType.EXPENSE,
            category=AccountCategory.CAPITAL_LOSSES,
            currency=base_currency,
            is_system=True,
            description="Realized capital losses from sales",
        ),
    }

    for account in accounts.values():
        session.add(account)

    session.flush()
    return accounts


def get_next_entry_number(session: Session, portfolio_id: str) -> int:
    """Get the next sequential entry number for a portfolio.

    Args:
        session: Database session
        portfolio_id: Portfolio ID

    Returns:
        Next entry number (starting from 1)
    """
    stmt = (
        select(JournalEntry.entry_number)
        .where(JournalEntry.portfolio_id == portfolio_id)
        .order_by(JournalEntry.entry_number.desc())
        .limit(1)
    )

    result = session.execute(stmt).scalar()
    return (result or 0) + 1


def record_transaction_as_journal_entry(
    session: Session,
    transaction: Transaction,
    accounts: dict[str, ChartAccount],
) -> JournalEntry:
    """Record a transaction as a journal entry with proper debits and credits.

    Applies double-entry bookkeeping rules for each transaction type:
    - BUY: DR Investments, CR Cash (+ fees)
    - SELL: DR Cash, CR Investments (+ capital gain/loss, fees)
    - DIVIDEND: DR Cash, CR Dividend Income (- taxes)
    - INTEREST: DR Cash, CR Interest Income
    - DEPOSIT: DR Cash, CR Owner's Capital
    - WITHDRAWAL: DR Owner's Capital, CR Cash
    - FEE: DR Fees Expense, CR Cash
    - TAX: DR Tax Expense, CR Cash

    Args:
        session: Database session
        transaction: Transaction to record
        accounts: Dictionary of ChartAccount instances by name

    Returns:
        Created JournalEntry with lines
    """
    # Get the broker account to find portfolio_id
    account = session.get(Account, transaction.account_id)
    if not account:
        raise ValueError(f"Account {transaction.account_id} not found")

    portfolio_id = account.portfolio_id

    # Create journal entry header
    entry = JournalEntry(
        portfolio_id=portfolio_id,
        entry_number=get_next_entry_number(session, portfolio_id),
        entry_date=transaction.date,
        type=JournalEntryType.TRANSACTION,
        status=JournalEntryStatus.POSTED,
        description=f"{transaction.type.value}: {transaction.notes or ''}",
        reference=transaction.id,
        created_by="system",
    )
    session.add(entry)
    session.flush()

    # Create journal lines based on transaction type
    lines = []
    line_num = 1

    if transaction.type == TransactionType.BUY:
        # Validate required fields
        if transaction.quantity is None or transaction.price is None:
            raise ValueError(f"BUY transaction {transaction.id} missing quantity or price")

        # Validate fees field
        fees = transaction.fees if transaction.fees is not None else Decimal("0")

        # DR Investments (cost + fees)
        total_cost = (transaction.quantity * transaction.price) + fees
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["investments"].id,
                line_number=line_num,
                debit_amount=total_cost,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                description=f"Buy {transaction.quantity} shares",
            )
        )
        line_num += 1

        # CR Cash
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=total_cost,
                currency=transaction.currency,
                description="Cash payment for purchase",
            )
        )

    elif transaction.type == TransactionType.SELL:
        # Validate required fields
        if transaction.quantity is None or transaction.price is None:
            raise ValueError(f"SELL transaction {transaction.id} missing quantity or price")

        # Validate fees field
        fees = transaction.fees if transaction.fees is not None else Decimal("0")

        # Calculate capital gain/loss (simplified - would need cost basis tracking)
        proceeds = (transaction.quantity * transaction.price) - fees

        # DR Cash (proceeds)
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=proceeds,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                description=f"Proceeds from sale of {transaction.quantity} shares",
            )
        )
        line_num += 1

        # CR Investments (at original cost - simplified)
        # Note: This would need proper cost basis tracking in production
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["investments"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=proceeds,  # Simplified
                currency=transaction.currency,
                description="Reduce investment balance",
            )
        )

    elif transaction.type == TransactionType.DIVIDEND:
        # DR Cash (net dividend)
        net_amount = transaction.amount - (transaction.tax_amount or Decimal("0"))
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=net_amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                description="Dividend received (net of tax)",
            )
        )
        line_num += 1

        # DR Tax Expense (if withholding tax)
        if transaction.tax_amount and transaction.tax_amount > 0:
            lines.append(
                JournalLine(
                    journal_entry_id=entry.id,
                    account_id=accounts["taxes"].id,
                    line_number=line_num,
                    debit_amount=transaction.tax_amount,
                    credit_amount=Decimal("0"),
                    currency=transaction.currency,
                    description="Withholding tax on dividend",
                )
            )
            line_num += 1

        # CR Dividend Income (gross)
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["dividend_income"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=transaction.amount,
                currency=transaction.currency,
                description="Dividend income",
            )
        )

    elif transaction.type == TransactionType.INTEREST:
        # DR Cash
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=transaction.amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                description="Interest received",
            )
        )
        line_num += 1

        # CR Interest Income
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["interest_income"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=transaction.amount,
                currency=transaction.currency,
                description="Interest income",
            )
        )

    elif transaction.type == TransactionType.DEPOSIT:
        # DR Cash
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=transaction.amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                description="Deposit to account",
            )
        )
        line_num += 1

        # CR Owner's Capital
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["capital"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=transaction.amount,
                currency=transaction.currency,
                description="Capital contribution",
            )
        )

    elif transaction.type == TransactionType.WITHDRAWAL:
        # DR Owner's Capital
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["capital"].id,
                line_number=line_num,
                debit_amount=transaction.amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                description="Withdrawal from account",
            )
        )
        line_num += 1

        # CR Cash
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=transaction.amount,
                currency=transaction.currency,
                description="Cash withdrawal",
            )
        )

    elif transaction.type == TransactionType.FEE:
        # DR Fees Expense
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["fees"].id,
                line_number=line_num,
                debit_amount=transaction.amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                description="Fee charged",
            )
        )
        line_num += 1

        # CR Cash
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=transaction.amount,
                currency=transaction.currency,
                description="Cash payment for fee",
            )
        )

    elif transaction.type == TransactionType.TAX:
        # DR Tax Expense
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["taxes"].id,
                line_number=line_num,
                debit_amount=transaction.amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                description="Tax payment",
            )
        )
        line_num += 1

        # CR Cash
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=transaction.amount,
                currency=transaction.currency,
                description="Cash payment for tax",
            )
        )

    # Add all lines to session
    for line in lines:
        session.add(line)

    session.flush()

    # Verify entry is balanced
    if not entry.is_balanced:
        raise ValueError(
            f"Journal entry {entry.entry_number} is not balanced: "
            f"DR={entry.total_debits}, CR={entry.total_credits}"
        )

    # Create reconciliation record
    reconciliation = Reconciliation(
        transaction_id=transaction.id,
        journal_entry_id=entry.id,
        status=ReconciliationStatus.RECONCILED,
        reconciled_by="system",
    )
    session.add(reconciliation)
    session.flush()

    return entry


def get_account_balance(
    session: Session,
    account_id: str,
    as_of_date: date | None = None,
) -> Decimal:
    """Calculate account balance as of a specific date.

    Args:
        session: Database session
        account_id: ChartAccount ID
        as_of_date: Date to calculate balance (defaults to today)

    Returns:
        Account balance (positive for normal balance side)
    """
    if as_of_date is None:
        as_of_date = date.today()

    # Get account to determine normal balance
    account = session.get(ChartAccount, account_id)
    if not account:
        raise ValueError(f"Account {account_id} not found")

    # Query all journal lines for this account up to date
    stmt = (
        select(JournalLine)
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalLine.account_id == account_id,
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date <= as_of_date,
        )
    )

    lines = session.execute(stmt).scalars().all()

    # Calculate balance
    total_debits = sum((line.debit_amount for line in lines), Decimal("0"))
    total_credits = sum((line.credit_amount for line in lines), Decimal("0"))

    # Return based on normal balance side
    if account.normal_balance == "DEBIT":
        return total_debits - total_credits
    else:
        return total_credits - total_debits
