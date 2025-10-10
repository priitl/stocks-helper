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
    Holding,
    JournalEntry,
    JournalEntryStatus,
    JournalEntryType,
    JournalLine,
    Portfolio,
    Reconciliation,
    ReconciliationStatus,
    Security,
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
        "fair_value_adjustment": ChartAccount(
            portfolio_id=portfolio_id,
            code="1210",
            name="Fair Value Adjustment - Investments",
            type=AccountType.ASSET,
            category=AccountCategory.INVESTMENTS,
            currency=base_currency,
            is_system=True,
            description="Mark-to-market adjustment (Investments at Cost + FV Adj = Market Value)",
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
            name="Realized Capital Gains",
            type=AccountType.REVENUE,
            category=AccountCategory.CAPITAL_GAINS,
            currency=base_currency,
            is_system=True,
            description="Realized capital gains from sales (GAAP/IFRS)",
        ),
        "unrealized_investment_gl": ChartAccount(
            portfolio_id=portfolio_id,
            code="4210",
            name="Unrealized Gain/Loss on Investments",
            type=AccountType.REVENUE,
            category=AccountCategory.CAPITAL_GAINS,
            currency=base_currency,
            is_system=True,
            description=(
                "Unrealized gains/losses from mark-to-market (IFRS 9) - "
                "can be credit (gain) or debit (loss)"
            ),
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
            name="Realized Capital Losses",
            type=AccountType.EXPENSE,
            category=AccountCategory.CAPITAL_LOSSES,
            currency=base_currency,
            is_system=True,
            description="Realized capital losses from sales (GAAP/IFRS)",
        ),
        # Currency gain/loss accounts (IAS 21 / ASC 830)
        "currency_gains": ChartAccount(
            portfolio_id=portfolio_id,
            code="4300",
            name="Realized Currency Gains",
            type=AccountType.REVENUE,
            category=AccountCategory.CAPITAL_GAINS,
            currency=base_currency,
            is_system=True,
            description="Realized foreign exchange gains (IAS 21)",
        ),
        "unrealized_currency_gl": ChartAccount(
            portfolio_id=portfolio_id,
            code="4310",
            name="Unrealized Currency Gain/Loss",
            type=AccountType.REVENUE,
            category=AccountCategory.CAPITAL_GAINS,
            currency=base_currency,
            is_system=True,
            description=(
                "Unrealized FX gains/losses on monetary items (IAS 21) - "
                "can be credit (gain) or debit (loss)"
            ),
        ),
        "currency_losses": ChartAccount(
            portfolio_id=portfolio_id,
            code="5300",
            name="Realized Currency Losses",
            type=AccountType.EXPENSE,
            category=AccountCategory.CAPITAL_LOSSES,
            currency=base_currency,
            is_system=True,
            description="Realized foreign exchange losses (IAS 21)",
        ),
    }

    for account in accounts.values():
        session.add(account)

    session.flush()
    return accounts


def get_next_entry_number(session: Session, portfolio_id: str) -> int:
    """Get the next sequential entry number for a portfolio.

    Uses SELECT FOR UPDATE to prevent race conditions in concurrent transactions.

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
        .with_for_update()  # Lock row to prevent concurrent number conflicts
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

    Converts amounts to base currency and stores original currency in
    foreign_amount/foreign_currency fields. Journal entries must balance in base
    currency (GAAP/IFRS requirement).

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
        # Same currency - no conversion needed, but still track foreign currency
        # for multi-currency cash tracking
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

        # GAAP/IFRS: Create security lot for cost basis tracking
        if transaction.holding_id:
            # Get holding and security info for lot creation
            holding = session.get(Holding, transaction.holding_id)
            if holding:
                # Get security for ticker
                security = session.get(Security, holding.security_id)
                if security and security.ticker:
                    from src.services.lot_tracking_service import create_security_lot

                    try:
                        create_security_lot(
                            session,
                            transaction,
                            transaction.holding_id,
                            exchange_rate,
                            security.ticker,
                        )
                    except Exception as e:
                        # Log error but don't fail the whole transaction
                        # This allows gradual adoption of lot tracking
                        logger = __import__("logging").getLogger(__name__)
                        logger.warning(
                            f"Failed to create security lot for BUY {transaction.id}: {e}"
                        )

    elif transaction.type == TransactionType.SELL:
        # Validate required fields
        if transaction.quantity is None or transaction.price is None:
            raise ValueError(f"SELL transaction {transaction.id} missing quantity or price")

        # Use transaction.amount directly - it contains the actual cash inflow
        # Fees are recorded as separate FEE transactions, so don't subtract them here
        proceeds = transaction.amount

        # Convert proceeds to base currency
        proceeds_base = proceeds * exchange_rate

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

        # GAAP/IFRS: Use FIFO lot matching for cost basis
        # Split into capital gain/loss (price change) and realized FX gain/loss (rate change)
        cost_basis_base = proceeds_base  # Fallback if no lots
        total_capital_gain_base = Decimal("0")
        total_fx_gain_base = Decimal("0")

        if transaction.holding_id:
            try:
                from src.models import StockSplit
                from src.services.lot_tracking_service import (
                    allocate_lots_fifo,
                    create_security_allocation,
                )

                # Adjust SELL quantity for splits
                # Different brokers handle split recording differently:
                # - Swedbank: ALL transactions are in pre-split terms → apply ALL splits
                # - Lightyear: Transactions are in actual traded terms → apply only future splits
                adjusted_quantity = transaction.quantity

                # Get holding to find security
                holding = session.get(Holding, transaction.holding_id)
                if holding:
                    security = session.get(Security, holding.security_id)
                    if security:
                        # For Swedbank: apply ALL splits (all quantities are pre-split)
                        # For other brokers: apply only splits after the sale date
                        if transaction.broker_source == "swedbank":
                            # Get ALL splits for this security
                            splits_stmt = (
                                select(StockSplit)
                                .where(StockSplit.security_id == security.id)
                                .order_by(StockSplit.split_date)
                            )
                        else:
                            # Get splits that occurred after this sale
                            splits_stmt = (
                                select(StockSplit)
                                .where(
                                    StockSplit.security_id == security.id,
                                    StockSplit.split_date > transaction.date,
                                )
                                .order_by(StockSplit.split_date)
                            )

                        splits_to_apply = session.execute(splits_stmt).scalars().all()

                        # Apply each split to the sell quantity
                        for split in splits_to_apply:
                            adjusted_quantity *= split.split_ratio

                # Use FIFO to get cost basis with adjusted quantity
                # Lots already store split-adjusted quantities (Option B architecture)
                # Use a savepoint to rollback lot modifications if FIFO fails
                savepoint = session.begin_nested()
                try:
                    allocations = allocate_lots_fifo(
                        session,
                        transaction.holding_id,
                        adjusted_quantity,  # Use split-adjusted quantity to match lot quantities
                        transaction.date,
                        transaction.broker_source,  # Kept for API compatibility
                    )
                    savepoint.commit()  # FIFO succeeded, commit lot modifications
                except Exception as fifo_error:
                    # FIFO failed - rollback lot modifications
                    savepoint.rollback()
                    raise fifo_error  # Re-raise to trigger simplified accounting fallback

                # Calculate cost basis and split capital vs FX gains/losses
                cost_basis_base = Decimal("0")

                for lot, qty_allocated, alloc_cost_basis in allocations:
                    # Cost in original currency (for this allocation)
                    cost_in_original = qty_allocated * lot.cost_per_share

                    # Proceeds in original currency (for this allocation)
                    proceeds_in_original = (qty_allocated / adjusted_quantity) * proceeds

                    # 1. Capital gain/loss in original currency
                    capital_gain_original = proceeds_in_original - cost_in_original

                    # 2. Capital gain/loss in EUR (converted at SALE rate)
                    capital_gain_eur = capital_gain_original * exchange_rate

                    # 3. Realized FX gain/loss on the cost basis (IAS 21)
                    #    = cost × (sale rate - purchase rate)
                    fx_gain_eur = cost_in_original * (exchange_rate - lot.exchange_rate)

                    # Accumulate totals
                    cost_basis_base += alloc_cost_basis
                    total_capital_gain_base += capital_gain_eur
                    total_fx_gain_base += fx_gain_eur

                    # Create allocation record
                    alloc_proceeds = (qty_allocated / adjusted_quantity) * proceeds_base
                    create_security_allocation(
                        session,
                        lot,
                        transaction.id,
                        qty_allocated,
                        alloc_cost_basis,
                        alloc_proceeds,
                    )

            except Exception as e:
                # If lot tracking fails, fall back to simplified method
                logger = __import__("logging").getLogger(__name__)
                logger.warning(
                    f"Failed to use FIFO for SELL {transaction.id}: {e}. "
                    f"Using simplified accounting (proceeds = cost basis)"
                )
                cost_basis_base = proceeds_base
                total_capital_gain_base = Decimal("0")
                total_fx_gain_base = Decimal("0")

        # CR Investments at Cost
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["investments"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=(
                    cost_basis_base / exchange_rate if exchange_rate > 0 else cost_basis_base
                ),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Reduce investment at cost basis",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # Record realized capital gain or loss (price change only)
        if abs(total_capital_gain_base) >= Decimal("0.01"):  # Ignore rounding
            if total_capital_gain_base > 0:
                # CR Realized Capital Gain
                lines.append(
                    create_journal_line(
                        journal_entry_id=entry.id,
                        account_id=accounts["capital_gains"].id,
                        line_number=line_num,
                        debit_amount=Decimal("0"),
                        credit_amount=(
                            total_capital_gain_base / exchange_rate
                            if exchange_rate > 0
                            else total_capital_gain_base
                        ),
                        currency=transaction.currency,
                        base_currency=base_currency,
                        exchange_rate=exchange_rate,
                        description="Realized capital gain on sale",
                        currency_converter=currency_converter,
                        transaction_date=transaction.date,
                    )
                )
                line_num += 1
            else:
                # DR Realized Capital Loss
                lines.append(
                    create_journal_line(
                        journal_entry_id=entry.id,
                        account_id=accounts["capital_losses"].id,
                        line_number=line_num,
                        debit_amount=(
                            abs(total_capital_gain_base) / exchange_rate
                            if exchange_rate > 0
                            else abs(total_capital_gain_base)
                        ),
                        credit_amount=Decimal("0"),
                        currency=transaction.currency,
                        base_currency=base_currency,
                        exchange_rate=exchange_rate,
                        description="Realized capital loss on sale",
                        currency_converter=currency_converter,
                        transaction_date=transaction.date,
                    )
                )
                line_num += 1

        # Record realized FX gain or loss (IAS 21 - exchange rate change on investment)
        # This is a EUR-only line that measures the impact of exchange rate changes
        # NO foreign_currency set (this is not a foreign currency position)
        if abs(total_fx_gain_base) >= Decimal("0.01"):  # Ignore rounding
            if total_fx_gain_base > 0:
                # CR Realized Currency Gain
                lines.append(
                    JournalLine(
                        journal_entry_id=entry.id,
                        account_id=accounts["currency_gains"].id,
                        line_number=line_num,
                        debit_amount=Decimal("0"),
                        credit_amount=total_fx_gain_base,  # EUR amount, no conversion
                        currency=base_currency,  # EUR, not foreign currency
                        exchange_rate=Decimal("1.0"),
                        description="Realized FX gain on investment (IAS 21)",
                    )
                )
                line_num += 1
            else:
                # DR Realized Currency Loss
                lines.append(
                    JournalLine(
                        journal_entry_id=entry.id,
                        account_id=accounts["currency_losses"].id,
                        line_number=line_num,
                        debit_amount=abs(total_fx_gain_base),  # EUR amount, no conversion
                        credit_amount=Decimal("0"),
                        currency=base_currency,  # EUR, not foreign currency
                        exchange_rate=Decimal("1.0"),
                        description="Realized FX loss on investment (IAS 21)",
                    )
                )
                line_num += 1

    elif transaction.type == TransactionType.DIVIDEND:
        # DR Cash (net dividend after tax and fees)
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
                description="Dividend received (net of tax and fees)",
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

        # DR Fees Expense (if dividend fee charged)
        if transaction.fees and transaction.fees > 0:
            lines.append(
                create_journal_line(
                    journal_entry_id=entry.id,
                    account_id=accounts["fees"].id,
                    line_number=line_num,
                    debit_amount=transaction.fees,
                    credit_amount=Decimal("0"),
                    currency=transaction.currency,
                    base_currency=base_currency,
                    exchange_rate=exchange_rate,
                    description="Fee on dividend",
                    currency_converter=currency_converter,
                    transaction_date=transaction.date,
                )
            )
            line_num += 1

        # CR Dividend Income (gross = net + tax + fees)
        gross_amount = (
            transaction.amount
            + (transaction.tax_amount or Decimal("0"))
            + (transaction.fees or Decimal("0"))
        )
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
        # transaction.amount is the NET cash received (after fees already deducted)
        # Fees field is informational - fee was already deducted from broker

        # DR Cash (transaction.amount is already net)
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=transaction.amount,  # NET cash received
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Interest received (net of fees)",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # DR Fees Expense (if interest fee charged)
        # Fee was already deducted from cash, this is just expense recognition
        if transaction.fees and transaction.fees > 0:
            lines.append(
                create_journal_line(
                    journal_entry_id=entry.id,
                    account_id=accounts["fees"].id,
                    line_number=line_num,
                    debit_amount=transaction.fees,
                    credit_amount=Decimal("0"),
                    currency=transaction.currency,
                    base_currency=base_currency,
                    exchange_rate=exchange_rate,
                    description="Fee on interest",
                    currency_converter=currency_converter,
                    transaction_date=transaction.date,
                )
            )
            line_num += 1

        # CR Interest Income (gross = net + fees)
        gross_amount = transaction.amount + (transaction.fees or Decimal("0"))
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["interest_income"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=gross_amount,
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Interest income",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )

    elif transaction.type == TransactionType.DEPOSIT:
        # transaction.amount is the NET cash deposited (after fees already deducted)
        # Fees field is informational - fee was already deducted from broker

        # DR Cash (transaction.amount is already net)
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=transaction.amount,  # NET cash deposited
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Deposit to account (net of fees)",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # DR Fees Expense (if deposit fee charged)
        # Fee was already deducted from cash, this is just expense recognition
        if transaction.fees and transaction.fees > 0:
            lines.append(
                create_journal_line(
                    journal_entry_id=entry.id,
                    account_id=accounts["fees"].id,
                    line_number=line_num,
                    debit_amount=transaction.fees,
                    credit_amount=Decimal("0"),
                    currency=transaction.currency,
                    base_currency=base_currency,
                    exchange_rate=exchange_rate,
                    description="Fee on deposit",
                    currency_converter=currency_converter,
                    transaction_date=transaction.date,
                )
            )
            line_num += 1

        # CR Owner's Capital (gross = net + fees)
        gross_amount = transaction.amount + (transaction.fees or Decimal("0"))
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["capital"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=gross_amount,
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Capital contribution",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )

    elif transaction.type == TransactionType.WITHDRAWAL:
        # DR Owner's Capital (withdrawal + fees)
        withdrawal_total = transaction.amount + (transaction.fees or Decimal("0"))
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["capital"].id,
                line_number=line_num,
                debit_amount=withdrawal_total,
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Withdrawal from account (including fees)",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # DR Fees Expense (if withdrawal fee charged)
        # Note: Debit capital for the total, but expense the fee separately
        if transaction.fees and transaction.fees > 0:
            lines.append(
                create_journal_line(
                    journal_entry_id=entry.id,
                    account_id=accounts["fees"].id,
                    line_number=line_num,
                    debit_amount=transaction.fees,
                    credit_amount=Decimal("0"),
                    currency=transaction.currency,
                    base_currency=base_currency,
                    exchange_rate=exchange_rate,
                    description="Fee on withdrawal",
                    currency_converter=currency_converter,
                    transaction_date=transaction.date,
                )
            )
            line_num += 1

        # CR Cash (withdrawal amount + fees)
        cash_outflow = transaction.amount + (transaction.fees or Decimal("0"))
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=cash_outflow,
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
        # Transactions come in pairs: EUR D (spent) + NOK K (received)
        # Each transaction creates its own journal entry that balances in its own currency
        #
        # Example: Convert EUR 1,458.67 to NOK 16,965.84 (with EUR 3.50 fee)
        #   EUR D transaction (Entry #275):
        #     DR Currency Clearing  EUR 1,458.67
        #     DR Fees Expense       EUR 3.50
        #     CR Cash               EUR 1,462.17  ✓ Balances in EUR
        #   NOK K transaction (Entry #276):
        #     DR Cash               NOK 16,965.84
        #     CR Currency Clearing  NOK 16,965.84  ✓ Balances in NOK
        #
        # Currency Clearing account shows both EUR and NOK positions
        # Net clearing ≈ 0 (difference is FX gain/loss from spread)

        # IMPORTANT: For base currency transactions, use rate=1.0
        # The transaction.exchange_rate is for converting to base currency
        # but if we're already in base currency, rate must be 1.0
        conv_rate = Decimal("1.0") if transaction.currency == base_currency else exchange_rate

        if transaction.debit_credit == "D":
            # Money out: spent this currency
            # Convert to EUR for proper journal entry balancing
            # Original currency tracked in foreign_amount/foreign_currency
            #
            # NOTE: CONVERSION fees are imported as separate FEE transactions (Lightyear broker)
            # So transaction.fees field is informational only - do NOT journal it here
            # The separate FEE transaction will journal: DR Fees Expense / CR Cash

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

            # CR Cash (transaction.amount only - fees handled by separate FEE transaction)
            # Fees NOT included - separate FEE transaction
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
            # Convert to EUR for proper journal entry balancing
            # Original currency tracked in foreign_amount/foreign_currency

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

            # GAAP/IFRS (IAS 21): Create currency lot for foreign currency received
            # Only create lot for non-base currency receipts with conversion details
            if (
                transaction.currency != base_currency
                and transaction.conversion_from_currency
                and transaction.conversion_from_amount
            ):
                from src.services.currency_lot_service import CurrencyLotService

                try:
                    lot_service = CurrencyLotService(session)
                    lot_service.create_lot_from_conversion(transaction)
                except Exception as e:
                    # Log error but don't fail the whole transaction
                    logger = __import__("logging").getLogger(__name__)
                    logger.warning(
                        f"Failed to create currency lot for CONVERSION {transaction.id}: {e}"
                    )

    elif transaction.type == TransactionType.DISTRIBUTION:
        # transaction.amount is the NET cash received (after tax and fees deducted)
        # Fees/tax fields are informational - already deducted from broker

        # DR Cash (transaction.amount is already net)
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=transaction.amount,  # NET cash received
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Distribution received (net of tax and fees)",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # DR Tax Expense (if withholding tax)
        # Tax was already deducted from cash, this is just expense recognition
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

        # DR Fees Expense (if distribution fee charged)
        # Fee was already deducted from cash, this is just expense recognition
        if transaction.fees and transaction.fees > 0:
            lines.append(
                create_journal_line(
                    journal_entry_id=entry.id,
                    account_id=accounts["fees"].id,
                    line_number=line_num,
                    debit_amount=transaction.fees,
                    credit_amount=Decimal("0"),
                    currency=transaction.currency,
                    base_currency=base_currency,
                    exchange_rate=exchange_rate,
                    description="Fee on distribution",
                    currency_converter=currency_converter,
                    transaction_date=transaction.date,
                )
            )
            line_num += 1

        # CR Dividend Income (gross = net + tax + fees)
        gross_amount = (
            transaction.amount
            + (transaction.tax_amount or Decimal("0"))
            + (transaction.fees or Decimal("0"))
        )
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
                description="Distribution income",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )

    elif transaction.type == TransactionType.REWARD:
        # transaction.amount is the NET cash received (after fees deducted)
        # Fees field is informational - fee was already deducted from broker

        # DR Cash (transaction.amount is already net)
        lines.append(
            create_journal_line(
                journal_entry_id=entry.id,
                account_id=accounts["cash"].id,
                line_number=line_num,
                debit_amount=transaction.amount,  # NET cash received
                credit_amount=Decimal("0"),
                currency=transaction.currency,
                base_currency=base_currency,
                exchange_rate=exchange_rate,
                description="Reward received (net of fees)",
                currency_converter=currency_converter,
                transaction_date=transaction.date,
            )
        )
        line_num += 1

        # DR Fees Expense (if reward fee charged)
        # Fee was already deducted from cash, this is just expense recognition
        if transaction.fees and transaction.fees > 0:
            lines.append(
                create_journal_line(
                    journal_entry_id=entry.id,
                    account_id=accounts["fees"].id,
                    line_number=line_num,
                    debit_amount=transaction.fees,
                    credit_amount=Decimal("0"),
                    currency=transaction.currency,
                    base_currency=base_currency,
                    exchange_rate=exchange_rate,
                    description="Fee on reward",
                    currency_converter=currency_converter,
                    transaction_date=transaction.date,
                )
            )
            line_num += 1

        # CR Dividend Income (gross = net + fees)
        gross_amount = transaction.amount + (transaction.fees or Decimal("0"))
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


def get_cash_balances_by_currency(
    session: Session,
    account_id: str,
    as_of_date: date | None = None,
) -> dict[str, Decimal]:
    """Calculate cash balances by currency (for multi-currency accounts).

    For multi-currency accounts like Cash, sums the foreign_amount field
    grouped by foreign_currency to get actual currency positions.

    Args:
        session: Database session
        account_id: ChartAccount ID (should be Cash account)
        as_of_date: Date to calculate balance (defaults to today)

    Returns:
        Dictionary mapping currency code to balance amount
        e.g., {"EUR": Decimal("384.03"), "NOK": Decimal("12.00")}
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
            JournalLine.foreign_currency.isnot(None),
            JournalLine.foreign_amount.isnot(None),
        )
    )

    lines = session.execute(stmt).scalars().all()

    # Group by currency and sum foreign_amount
    balances: dict[str, Decimal] = {}
    for line in lines:
        currency = line.foreign_currency
        if currency is None:
            continue  # Skip lines without foreign currency

        if currency not in balances:
            balances[currency] = Decimal("0")

        # Add/subtract based on debit/credit
        foreign_amount = line.foreign_amount or Decimal("0")
        if line.debit_amount > 0:
            balances[currency] += foreign_amount
        else:
            balances[currency] -= foreign_amount

    # Filter out currencies with zero balance
    return {curr: bal for curr, bal in balances.items() if abs(bal) >= Decimal("0.01")}
