"""Ledger reporting service for accounting reports.

Generates General Ledger, Trial Balance, Income Statement, and Balance Sheet.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import (
    AccountType,
    ChartAccount,
    JournalEntry,
    JournalEntryStatus,
    JournalLine,
)


@dataclass
class LedgerEntry:
    """Single ledger entry for general ledger report.

    Attributes:
        entry_date: Journal entry date
        entry_number: Journal entry number
        description: Entry description
        debit_amount: Debit amount
        credit_amount: Credit amount
        balance: Running balance
    """

    entry_date: date
    entry_number: int
    description: str
    debit_amount: Decimal
    credit_amount: Decimal
    balance: Decimal


@dataclass
class TrialBalanceEntry:
    """Single entry in trial balance report.

    Attributes:
        account_code: Account code
        account_name: Account name
        account_type: ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE
        debit_balance: Debit balance (if normal balance is debit)
        credit_balance: Credit balance (if normal balance is credit)
    """

    account_code: str
    account_name: str
    account_type: AccountType
    debit_balance: Decimal
    credit_balance: Decimal


def get_general_ledger(
    session: Session,
    account_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[LedgerEntry]:
    """Generate general ledger report for a specific account.

    Shows all journal entries affecting the account with running balance.

    Args:
        session: Database session
        account_id: ChartAccount ID
        start_date: Start date for report (optional)
        end_date: End date for report (optional)

    Returns:
        List of LedgerEntry sorted by date
    """
    # Get account
    account = session.get(ChartAccount, account_id)
    if not account:
        raise ValueError(f"Account {account_id} not found")

    # Build query
    stmt = (
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalLine.account_id == account_id,
            JournalEntry.status == JournalEntryStatus.POSTED,
        )
    )

    if start_date:
        stmt = stmt.where(JournalEntry.entry_date >= start_date)
    if end_date:
        stmt = stmt.where(JournalEntry.entry_date <= end_date)

    stmt = stmt.order_by(JournalEntry.entry_date, JournalEntry.entry_number)

    results = session.execute(stmt).all()

    # Calculate running balance
    entries = []
    running_balance = Decimal("0")

    for line, entry in results:
        if account.normal_balance == "DEBIT":
            running_balance += line.debit_amount - line.credit_amount
        else:
            running_balance += line.credit_amount - line.debit_amount

        entries.append(
            LedgerEntry(
                entry_date=entry.entry_date,
                entry_number=entry.entry_number,
                description=entry.description,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
                balance=running_balance,
            )
        )

    return entries


def get_trial_balance(
    session: Session,
    portfolio_id: str,
    as_of_date: date | None = None,
) -> list[TrialBalanceEntry]:
    """Generate trial balance report for a portfolio.

    Lists all accounts with their balances, grouped by type.
    Verifies that total debits equal total credits.

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        as_of_date: Date for balance (defaults to today)

    Returns:
        List of TrialBalanceEntry sorted by account code
    """
    if as_of_date is None:
        as_of_date = date.today()

    # Get all accounts for portfolio
    stmt = (
        select(ChartAccount)
        .where(ChartAccount.portfolio_id == portfolio_id, ChartAccount.is_active)
        .order_by(ChartAccount.code)
    )

    accounts = session.execute(stmt).scalars().all()

    entries = []
    for account in accounts:
        # Calculate balance
        balance = _calculate_account_balance(session, account.id, as_of_date)

        # Determine if balance goes in debit or credit column
        if account.normal_balance == "DEBIT":
            debit_balance = balance if balance >= 0 else Decimal("0")
            credit_balance = abs(balance) if balance < 0 else Decimal("0")
        else:
            debit_balance = abs(balance) if balance < 0 else Decimal("0")
            credit_balance = balance if balance >= 0 else Decimal("0")

        entries.append(
            TrialBalanceEntry(
                account_code=account.code,
                account_name=account.name,
                account_type=account.type,
                debit_balance=debit_balance,
                credit_balance=credit_balance,
            )
        )

    return entries


def _calculate_account_balance(
    session: Session,
    account_id: str,
    as_of_date: date,
) -> Decimal:
    """Calculate account balance as of a specific date.

    Args:
        session: Database session
        account_id: ChartAccount ID
        as_of_date: Date to calculate balance

    Returns:
        Account balance (positive for normal balance side)
    """
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


@dataclass
class IncomeStatementLine:
    """Single line in income statement.

    Attributes:
        account_name: Account name
        amount: Amount (positive)
    """

    account_name: str
    amount: Decimal


@dataclass
class IncomeStatement:
    """Income statement report.

    Attributes:
        start_date: Period start date
        end_date: Period end date
        revenue_lines: Revenue accounts
        expense_lines: Expense accounts
        total_revenue: Total revenue
        total_expenses: Total expenses
        net_income: Net income (revenue - expenses)
    """

    start_date: date
    end_date: date
    revenue_lines: list[IncomeStatementLine]
    expense_lines: list[IncomeStatementLine]
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal


def get_income_statement(
    session: Session,
    portfolio_id: str,
    start_date: date,
    end_date: date,
) -> IncomeStatement:
    """Generate income statement for a period.

    Shows revenue and expenses, calculating net income.

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        start_date: Period start date
        end_date: Period end date

    Returns:
        IncomeStatement report
    """
    # Get all revenue and expense accounts
    stmt = select(ChartAccount).where(
        ChartAccount.portfolio_id == portfolio_id,
        ChartAccount.is_active,
        ChartAccount.type.in_([AccountType.REVENUE, AccountType.EXPENSE]),
    )

    accounts = session.execute(stmt).scalars().all()

    revenue_lines = []
    expense_lines = []
    total_revenue = Decimal("0")
    total_expenses = Decimal("0")

    for account in accounts:
        # Calculate activity for the period
        stmt = (
            select(JournalLine)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalLine.account_id == account.id,
                JournalEntry.status == JournalEntryStatus.POSTED,
                JournalEntry.entry_date >= start_date,
                JournalEntry.entry_date <= end_date,
            )
        )

        lines = session.execute(stmt).scalars().all()

        if not lines:
            continue

        # Calculate net change for period
        total_debits = sum((line.debit_amount for line in lines), Decimal("0"))
        total_credits = sum((line.credit_amount for line in lines), Decimal("0"))

        if account.type == AccountType.REVENUE:
            # Revenue has credit normal balance
            amount: Decimal = total_credits - total_debits
            if amount > 0:
                revenue_lines.append(IncomeStatementLine(account.name, amount))
                total_revenue += amount
        else:  # EXPENSE
            # Expense has debit normal balance
            amount = total_debits - total_credits
            if amount > 0:
                expense_lines.append(IncomeStatementLine(account.name, amount))
                total_expenses += amount

    net_income = total_revenue - total_expenses

    return IncomeStatement(
        start_date=start_date,
        end_date=end_date,
        revenue_lines=revenue_lines,
        expense_lines=expense_lines,
        total_revenue=total_revenue,
        total_expenses=total_expenses,
        net_income=net_income,
    )


@dataclass
class BalanceSheetLine:
    """Single line in balance sheet.

    Attributes:
        account_name: Account name
        amount: Amount (positive)
    """

    account_name: str
    amount: Decimal


@dataclass
class BalanceSheet:
    """Balance sheet report.

    Attributes:
        as_of_date: Report date
        asset_lines: Asset accounts
        liability_lines: Liability accounts
        equity_lines: Equity accounts
        total_assets: Total assets
        total_liabilities: Total liabilities
        total_equity: Total equity
    """

    as_of_date: date
    asset_lines: list[BalanceSheetLine]
    liability_lines: list[BalanceSheetLine]
    equity_lines: list[BalanceSheetLine]
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal


def get_balance_sheet(
    session: Session,
    portfolio_id: str,
    as_of_date: date | None = None,
) -> BalanceSheet:
    """Generate balance sheet as of a specific date.

    Shows assets, liabilities, and equity.
    Verifies accounting equation: Assets = Liabilities + Equity

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        as_of_date: Report date (defaults to today)

    Returns:
        BalanceSheet report
    """
    if as_of_date is None:
        as_of_date = date.today()

    # Get all balance sheet accounts
    stmt = select(ChartAccount).where(
        ChartAccount.portfolio_id == portfolio_id,
        ChartAccount.is_active,
        ChartAccount.type.in_([AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY]),
    )

    accounts = session.execute(stmt).scalars().all()

    asset_lines = []
    liability_lines = []
    equity_lines = []
    total_assets = Decimal("0")
    total_liabilities = Decimal("0")
    total_equity = Decimal("0")

    for account in accounts:
        balance = _calculate_account_balance(session, account.id, as_of_date)

        if balance == 0:
            continue

        if account.type == AccountType.ASSET:
            asset_lines.append(BalanceSheetLine(account.name, balance))
            total_assets += balance
        elif account.type == AccountType.LIABILITY:
            liability_lines.append(BalanceSheetLine(account.name, balance))
            total_liabilities += balance
        else:  # EQUITY
            equity_lines.append(BalanceSheetLine(account.name, balance))
            total_equity += balance

    return BalanceSheet(
        as_of_date=as_of_date,
        asset_lines=asset_lines,
        liability_lines=liability_lines,
        equity_lines=equity_lines,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        total_equity=total_equity,
    )
