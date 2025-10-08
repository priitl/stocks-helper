"""Accounting service for double-entry bookkeeping.

Handles recording transactions as journal entries following GAAP principles.
"""

import asyncio
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
from src.services.currency_converter import CurrencyConverter


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
        "currency_clearing": ChartAccount(
            portfolio_id=portfolio_id,
            code="1150",
            name="Currency Exchange Clearing",
            type=AccountType.ASSET,
            category=AccountCategory.CASH,
            currency=base_currency,
            is_system=True,
            description="Temporary clearing account for currency conversions",
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


def create_journal_line(
    journal_entry_id: str,
    account_id: str,
    line_number: int,
    debit_amount: Decimal,
    credit_amount: Decimal,
    currency: str,
    base_currency: str,
    exchange_rate: Decimal,
    description: str,
    currency_converter: CurrencyConverter | None = None,
    transaction_date: date | None = None,
    preserve_currency: bool = False,
) -> JournalLine:
    """Create a journal line with proper multi-currency handling.

    Converts amounts to base currency and preserves original currency information,
    unless preserve_currency=True (for multi-currency accounts like Cash).

    Args:
        journal_entry_id: Journal entry ID
        account_id: Chart account ID
        line_number: Line number within entry
        debit_amount: Debit amount in original currency
        credit_amount: Credit amount in original currency
        currency: Transaction currency
        base_currency: Portfolio base currency
        exchange_rate: Exchange rate (base_currency per unit of currency)
        description: Line description
        currency_converter: Optional currency converter for missing rates
        transaction_date: Transaction date for currency conversion
        preserve_currency: If True, keep original currency without conversion (for Cash)

    Returns:
        JournalLine with proper currency conversion (or preserved if requested)
    """
    # Store original amounts
    original_debit = debit_amount
    original_credit = credit_amount
    original_currency = currency

    # For multi-currency accounts like Cash, preserve original currency
    if preserve_currency:
        return JournalLine(
            journal_entry_id=journal_entry_id,
            account_id=account_id,
            line_number=line_number,
            debit_amount=debit_amount,
            credit_amount=credit_amount,
            currency=currency,
            exchange_rate=exchange_rate,
            description=description,
        )

    # Convert to base currency if needed
    if currency != base_currency:
        # Use provided exchange rate, or fetch if needed and rate is 1.0 (missing)
        rate = exchange_rate
        if rate == Decimal("1.0") and currency_converter and transaction_date:
            # Fetch actual rate
            fetched_rate = asyncio.run(
                currency_converter.get_rate(currency, base_currency, transaction_date)
            )
            if fetched_rate:
                rate = Decimal(str(fetched_rate))

        # Convert amounts to base currency
        if debit_amount > 0:
            debit_amount = debit_amount * rate
        if credit_amount > 0:
            credit_amount = credit_amount * rate

        # Store as base currency with foreign currency details
        return JournalLine(
            journal_entry_id=journal_entry_id,
            account_id=account_id,
            line_number=line_number,
            debit_amount=debit_amount,
            credit_amount=credit_amount,
            currency=base_currency,
            foreign_amount=original_debit if original_debit > 0 else original_credit,
            foreign_currency=original_currency,
            exchange_rate=rate,
            description=description,
        )
    else:
        # Same currency - no conversion needed, but still track foreign currency for multi-currency cash tracking
        return JournalLine(
            journal_entry_id=journal_entry_id,
            account_id=account_id,
            line_number=line_number,
            debit_amount=debit_amount,
            credit_amount=credit_amount,
            currency=base_currency,
            foreign_amount=original_debit if original_debit > 0 else original_credit,
            foreign_currency=original_currency,
            exchange_rate=Decimal("1.0"),
            description=description,
        )


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

    # Get portfolio to determine base currency
    portfolio = session.get(Portfolio, portfolio_id)
    if not portfolio:
        raise ValueError(f"Portfolio {portfolio_id} not found")

    base_currency = portfolio.base_currency

    # Initialize currency converter for exchange rates
    currency_converter = CurrencyConverter()

    # Get exchange rate from transaction, or default to 1.0
    exchange_rate = transaction.exchange_rate or Decimal("1.0")

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

        # Use transaction.amount directly - it contains the actual cash outflow
        # Fees are recorded as separate FEE transactions, so don't add them here
        purchase_amount = transaction.amount

        # DR Investments
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["investments"].id,
                line_number=line_num,
                debit_amount=purchase_amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description=f"Buy {transaction.quantity} shares",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # CR Cash
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=purchase_amount,
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Cash payment for purchase",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )

    elif transaction.type == TransactionType.SELL:
        # Validate required fields
        if transaction.quantity is None or transaction.price is None:
            raise ValueError(f"SELL transaction {transaction.id} missing quantity or price")

        # Use transaction.amount directly - it contains the actual cash inflow
        # Fees are recorded as separate FEE transactions, so don't subtract them here
        proceeds = transaction.amount

        # DR Cash (proceeds)
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=proceeds,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description=f"Proceeds from sale of {transaction.quantity} shares",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # CR Investments (at original cost - simplified)
        # Note: This would need proper cost basis tracking in production
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["investments"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=proceeds,  # Simplified
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Reduce investment balance",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )

    elif transaction.type == TransactionType.DIVIDEND:
        # DR Cash (net dividend)
        # transaction.amount is already the NET amount from CSV (Summa field)
        # tax_amount is extracted from description for informational purposes
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=transaction.amount,  # Already net amount
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Dividend received (net of tax)",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # DR Tax Expense (if withholding tax)
        if transaction.tax_amount and transaction.tax_amount > 0:
            lines.append(
                create_journal_line(
                    journal_entry_id=entry.id,
                    account_id=accounts["taxes"].id,
                    line_number=line_num,
                    debit_amount=transaction.tax_amount,
                    credit_amount=Decimal("0"),
                    currency=transaction.currency,
                    base_currency=base_currency,
                    exchange_rate=exchange_rate,
                    description="Withholding tax on dividend",
                    currency_converter=currency_converter,
                    transaction_date=transaction.date,
                )
            )
            line_num += 1

        # CR Dividend Income (gross = net + tax)
        gross_amount = transaction.amount + (transaction.tax_amount or Decimal("0"))
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["dividend_income"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=gross_amount,
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Dividend income",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )

    elif transaction.type == TransactionType.INTEREST:
        # DR Cash
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=transaction.amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Interest received",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # CR Interest Income
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["interest_income"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=transaction.amount,
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Interest income",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )

    elif transaction.type == TransactionType.DEPOSIT:
        # DR Cash
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=transaction.amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Deposit to account",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # CR Owner's Capital
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["capital"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=transaction.amount,
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Capital contribution",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )

    elif transaction.type == TransactionType.WITHDRAWAL:
        # DR Owner's Capital
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["capital"].id,
                line_number=line_num,
                debit_amount=transaction.amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Withdrawal from account",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # CR Cash
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=transaction.amount,
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Cash withdrawal",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )

    elif transaction.type == TransactionType.FEE:
        # DR Fees Expense
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["fees"].id,
                line_number=line_num,
                debit_amount=transaction.amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Fee charged",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # CR Cash
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=transaction.amount,
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Cash payment for fee",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )

    elif transaction.type == TransactionType.TAX:
        # DR Tax Expense
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["taxes"].id,
                line_number=line_num,
                debit_amount=transaction.amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Tax payment",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # CR Cash
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=transaction.amount,
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Cash payment for tax",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )

    elif transaction.type == TransactionType.CONVERSION:
        # Currency conversion: exchange between two currencies
        # Transactions come in pairs: EUR D (spent) + USD K (received)
        # Use clearing account to balance each transaction individually
        #
        # Example: Convert EUR 100 to USD 110
        #   EUR D transaction:
        #     DR Currency Clearing  100 EUR
        #     CR Cash               100 EUR
        #   USD K transaction:
        #     DR Cash               110 USD
        #     CR Currency Clearing  110 USD
        #
        # The clearing account nets to near-zero (or shows FX gain/loss)

        # IMPORTANT: For base currency transactions, use rate=1.0
        # The transaction.exchange_rate is for converting to base currency
        # but if we're already in base currency, rate must be 1.0
        conv_rate = (
            Decimal("1.0")
            if transaction.currency == base_currency
            else exchange_rate
        )

        if transaction.debit_credit == "D":
            # Money out: spent this currency
            # DR Currency Clearing
            lines.append(
                create_journal_line(
                    journal_entry_id=entry.id,
                    account_id=accounts["currency_clearing"].id,
                    line_number=line_num,
                    debit_amount=transaction.amount,
                    credit_amount=Decimal("0"),
                    currency=transaction.currency,
                    base_currency=base_currency,
                    exchange_rate=conv_rate,
                    description=f"Currency exchange - sent {transaction.currency}",
                    currency_converter=currency_converter,
                    transaction_date=transaction.date,
                )
            )
            line_num += 1

            # CR Cash (reduce this currency)
            lines.append(
                create_journal_line(
                    journal_entry_id=entry.id,
                    account_id=accounts["cash"].id,
                    line_number=line_num,
                    debit_amount=Decimal("0"),
                    credit_amount=transaction.amount,
                    currency=transaction.currency,
                    base_currency=base_currency,
                    exchange_rate=conv_rate,
                    description=f"Currency exchange - sent {transaction.currency}",
                    currency_converter=currency_converter,
                    transaction_date=transaction.date,
                )
            )
        else:  # K (credit)
            # Money in: received this currency
            # DR Cash (increase this currency)
            lines.append(
                create_journal_line(
                    journal_entry_id=entry.id,
                    account_id=accounts["cash"].id,
                    line_number=line_num,
                    debit_amount=transaction.amount,
                    credit_amount=Decimal("0"),
                    currency=transaction.currency,
                    base_currency=base_currency,
                    exchange_rate=conv_rate,
                    description=f"Currency exchange - received {transaction.currency}",
                    currency_converter=currency_converter,
                    transaction_date=transaction.date,
                )
            )
            line_num += 1

            # CR Currency Clearing
            lines.append(
                create_journal_line(
                    journal_entry_id=entry.id,
                    account_id=accounts["currency_clearing"].id,
                    line_number=line_num,
                    debit_amount=Decimal("0"),
                    credit_amount=transaction.amount,
                    currency=transaction.currency,
                    base_currency=base_currency,
                    exchange_rate=conv_rate,
                    description=f"Currency exchange - received {transaction.currency}",
                    currency_converter=currency_converter,
                    transaction_date=transaction.date,
                )
            )

    elif transaction.type == TransactionType.DISTRIBUTION:
        # Similar to dividend but for funds/ETFs
        # DR Cash (net distribution)
        net_amount = transaction.amount - (transaction.tax_amount or Decimal("0"))
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=net_amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Distribution received (net of tax)",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # DR Tax Expense (if withholding tax)
        if transaction.tax_amount and transaction.tax_amount > 0:
            lines.append(
                create_journal_line(
                    journal_entry_id=entry.id,
                    account_id=accounts["taxes"].id,
                    line_number=line_num,
                    debit_amount=transaction.tax_amount,
                    credit_amount=Decimal("0"),
                    currency=transaction.currency,
                    base_currency=base_currency,
                    exchange_rate=exchange_rate,
                    description="Withholding tax on distribution",
                    currency_converter=currency_converter,
                    transaction_date=transaction.date,
                )
            )
            line_num += 1

        # CR Dividend Income (gross) - use same account as dividends
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["dividend_income"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=transaction.amount,
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Distribution income",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )

    elif transaction.type == TransactionType.REWARD:
        # DR Cash
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=transaction.amount,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Reward received",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # CR Dividend Income (use dividend income for rewards)
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["dividend_income"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=transaction.amount,
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Reward income",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
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
