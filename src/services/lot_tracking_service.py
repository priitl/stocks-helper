"""Lot tracking service for GAAP/IFRS cost basis accounting.

Implements:
- SecurityLot creation for BUY transactions
- FIFO lot matching for SELL transactions
- Mark-to-market adjustments for securities and foreign currency
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import (
    ChartAccount,
    Holding,
    JournalEntry,
    JournalEntryStatus,
    JournalEntryType,
    JournalLine,
    Portfolio,
    Security,
    SecurityAllocation,
    SecurityLot,
    StockSplit,
    Transaction,
)
from src.services.currency_converter import CurrencyConverter
from src.services.market_data_fetcher import MarketDataFetcher


def create_security_lot(
    session: Session,
    transaction: Transaction,
    holding_id: str,
    exchange_rate: Decimal,
    ticker: str,
) -> SecurityLot:
    """Create a new security lot from a BUY transaction.

    Stores lots with as-traded quantities initially. When stock splits are discovered
    (via yfinance sync), the split is immediately applied to all existing lots using
    apply_split_to_existing_lots(). This ensures lots always have current split-adjusted
    quantities without needing to query splits during calculations (Option B architecture).

    This approach:
    - Stores split-adjusted quantities in lots
    - Splits applied once when discovered, not on-the-fly
    - All calculations use lot quantities directly
    - Performance: no split queries during FIFO or mark-to-market

    Args:
        session: Database session
        transaction: BUY transaction
        holding_id: Holding ID
        exchange_rate: Exchange rate (base currency per transaction currency)
        ticker: Security ticker symbol

    Returns:
        Created SecurityLot with as-traded quantities (will be adjusted when splits are synced)

    Raises:
        ValueError: If transaction is not a BUY or missing required fields
    """
    if transaction.quantity is None or transaction.price is None:
        raise ValueError(f"BUY transaction {transaction.id} missing quantity or price")

    # Calculate cost basis
    # transaction.amount already includes the total cost (quantity * price)
    total_cost = transaction.amount
    cost_per_share = transaction.price

    # Convert to base currency
    total_cost_base = total_cost * exchange_rate
    cost_per_share_base = cost_per_share * exchange_rate

    # Store as-traded quantities initially
    # When splits are discovered, they'll be applied immediately to all lots
    quantity = transaction.quantity
    remaining_quantity = transaction.quantity

    # Create lot with as-traded values (will be adjusted when splits sync)
    lot = SecurityLot(
        holding_id=holding_id,
        transaction_id=transaction.id,
        security_ticker=ticker,
        purchase_date=transaction.date,
        quantity=quantity,
        remaining_quantity=remaining_quantity,
        cost_per_share=cost_per_share,
        total_cost=total_cost,
        cost_per_share_base=cost_per_share_base,
        total_cost_base=total_cost_base,
        currency=transaction.currency,
        exchange_rate=exchange_rate,
        is_closed=False,
    )

    session.add(lot)
    session.flush()
    return lot


def allocate_lots_fifo(
    session: Session,
    holding_id: str,
    quantity_to_sell: Decimal,
    sell_date: date,
    broker_source: str | None = None,
) -> list[tuple[SecurityLot, Decimal, Decimal]]:
    """Allocate lots using FIFO for a SELL transaction.

    Finds the oldest open lots and allocates them to fulfill the sale quantity.
    Lots store split-adjusted quantities (Option B architecture).
    Updates lot remaining_quantity and is_closed status.

    Args:
        session: Database session
        holding_id: Holding ID
        quantity_to_sell: Quantity being sold (split-adjusted)
        sell_date: Sale date
        broker_source: Broker source (unused, kept for API compatibility)

    Returns:
        List of (lot, quantity_allocated, cost_basis_base)
        where cost_basis_base is the total cost basis for the allocated quantity

    Raises:
        ValueError: If insufficient lots to fulfill sale
    """
    # Get holding to find security
    holding = session.get(Holding, holding_id)
    if not holding:
        raise ValueError(f"Holding {holding_id} not found")

    security = session.get(Security, holding.security_id)
    if not security:
        raise ValueError(f"Security {holding.security_id} not found")

    # Get all open lots for this holding, ordered by purchase date (FIFO)
    stmt = (
        select(SecurityLot)
        .where(
            SecurityLot.holding_id == holding_id,
            SecurityLot.is_closed == False,  # noqa: E712
            SecurityLot.remaining_quantity > 0,
        )
        .order_by(SecurityLot.purchase_date, SecurityLot.created_at)
    )

    lots = session.execute(stmt).scalars().all()

    # Allocate lots
    allocations: list[tuple[SecurityLot, Decimal, Decimal]] = []
    remaining_to_sell = quantity_to_sell

    for lot in lots:
        if remaining_to_sell <= 0:
            break

        # Lots already store split-adjusted quantities (Option B)
        # No need to apply splits on-the-fly
        available_quantity = lot.remaining_quantity

        # Determine how much to allocate from this lot
        qty_to_allocate = min(available_quantity, remaining_to_sell)

        # Calculate cost basis for this allocation (in base currency)
        # Use the fraction of the lot we're allocating
        fraction_allocated = qty_to_allocate / available_quantity if available_quantity > 0 else Decimal("0")
        cost_basis = fraction_allocated * (lot.remaining_quantity * lot.cost_per_share_base)

        # Update lot remaining quantity (split-adjusted)
        lot_qty_to_remove = qty_to_allocate
        lot.remaining_quantity -= lot_qty_to_remove

        if lot.remaining_quantity <= Decimal("0.00000001"):  # Threshold for floating point
            lot.remaining_quantity = Decimal("0")
            lot.is_closed = True

        # Record allocation
        allocations.append((lot, qty_to_allocate, cost_basis))
        remaining_to_sell -= qty_to_allocate

    # Verify we allocated enough
    if remaining_to_sell > Decimal("0.00000001"):  # Small threshold for rounding
        raise ValueError(
            f"Insufficient lots to sell {quantity_to_sell} shares. "
            f"Only {quantity_to_sell - remaining_to_sell} available."
        )

    session.flush()
    return allocations


def create_security_allocation(
    session: Session,
    lot: SecurityLot,
    sell_transaction_id: str,
    quantity_allocated: Decimal,
    cost_basis: Decimal,
    proceeds: Decimal,
) -> SecurityAllocation:
    """Create a security allocation record linking a lot to a sale.

    Args:
        session: Database session
        lot: SecurityLot being allocated
        sell_transaction_id: SELL transaction ID
        quantity_allocated: Quantity from this lot used for the sale
        cost_basis: Cost basis for allocated quantity (base currency)
        proceeds: Sale proceeds for allocated quantity (base currency)

    Returns:
        Created SecurityAllocation
    """
    realized_gain_loss = proceeds - cost_basis

    allocation = SecurityAllocation(
        lot_id=lot.id,
        sell_transaction_id=sell_transaction_id,
        quantity_allocated=quantity_allocated,
        cost_basis=cost_basis,
        proceeds=proceeds,
        realized_gain_loss=realized_gain_loss,
    )

    session.add(allocation)
    session.flush()
    return allocation


def apply_split_to_existing_lots(
    session: Session,
    security_id: str,
    split: StockSplit,
) -> int:
    """Apply a stock split to all existing lots for a security.

    Updates lot quantities and cost basis for lots purchased before the split date.
    This is called when a new split is recorded to update existing lots in the database.

    Args:
        session: Database session
        security_id: Security ID
        split: StockSplit object to apply

    Returns:
        Number of lots updated

    Example:
        For a 2:1 split (split_ratio=2.0):
        - 100 shares @ $10/share → 200 shares @ $5/share
        - Total cost remains $1,000
    """
    # Find all lots for this security purchased before the split date
    stmt = (
        select(SecurityLot)
        .join(Holding, SecurityLot.holding_id == Holding.id)
        .join(Security, Holding.security_id == Security.id)
        .where(
            Security.id == security_id,
            SecurityLot.purchase_date < split.split_date,
        )
    )
    lots = session.execute(stmt).scalars().all()

    if not lots:
        return 0

    split_ratio = split.split_ratio  # e.g., 2.0 for 2:1 split, 0.5 for 1:2 reverse split

    updated_count = 0
    for lot in lots:
        # Adjust quantities (multiply by ratio)
        lot.quantity *= split_ratio
        lot.remaining_quantity *= split_ratio

        # Adjust cost per share (divide by ratio to maintain total cost)
        lot.cost_per_share /= split_ratio
        lot.cost_per_share_base /= split_ratio

        # Note: total_cost and total_cost_base remain unchanged
        # This is correct - a split changes quantity and price, not total value

        updated_count += 1

    session.flush()
    return updated_count


def _get_chart_accounts(session: Session, portfolio_id: str) -> dict[str, ChartAccount]:
    """Get existing chart of accounts for a portfolio.

    Args:
        session: Database session
        portfolio_id: Portfolio ID

    Returns:
        Dictionary mapping account keys to ChartAccount instances

    Raises:
        ValueError: If required accounts are not found
    """
    # Get all accounts for portfolio
    stmt = select(ChartAccount).where(ChartAccount.portfolio_id == portfolio_id)
    all_accounts = session.execute(stmt).scalars().all()

    # Map by name to key
    name_to_key = {
        "Cash": "cash",
        "Bank Accounts": "bank",
        "Currency Exchange Clearing": "currency_clearing",
        "Investments - Securities": "investments",
        "Fair Value Adjustment - Investments": "fair_value_adjustment",
        "Owner's Capital": "capital",
        "Retained Earnings": "retained_earnings",
        "Dividend Income": "dividend_income",
        "Interest Income": "interest_income",
        "Realized Capital Gains": "realized_gains",
        "Unrealized Gains on Investments": "unrealized_gains",
        "Fees and Commissions": "fees",
        "Tax Expense": "taxes",
        "Realized Capital Losses": "realized_losses",
        "Unrealized Losses on Investments": "unrealized_losses",
        "Realized Currency Gains": "currency_gains",
        "Unrealized Currency Gains": "unrealized_currency_gains",
        "Realized Currency Losses": "currency_losses",
        "Unrealized Currency Losses": "unrealized_currency_losses",
    }

    accounts = {}
    for account in all_accounts:
        key = name_to_key.get(account.name)
        if key:
            accounts[key] = account

    # Verify required accounts exist
    required = ["fair_value_adjustment", "unrealized_gains", "unrealized_losses"]
    for req in required:
        if req not in accounts:
            raise ValueError(f"Required account not found: {req}")

    return accounts


def mark_securities_to_market(
    session: Session,
    portfolio_id: str,
    as_of_date: date,
) -> JournalEntry | None:
    """Mark all securities to current market value.

    Creates adjustment entry for unrealized gains/losses following IFRS 9 and IAS 21.
    Separates price effects (IFRS 9) from FX effects (IAS 21) for proper compliance.

    This function compares the current market value of all securities with their
    cost basis plus any existing fair value adjustments, and creates a journal
    entry to adjust the Fair Value Adjustment account. For foreign currency
    securities, it separates:
    - Price unrealized G/L: Price changes measured at purchase exchange rates
    - FX unrealized G/L: Exchange rate changes measured at current prices

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        as_of_date: Date for market prices

    Returns:
        Created JournalEntry if adjustment needed, None if no adjustment
    """
    from src.services.accounting_service import (
        get_account_balance,
        get_next_entry_number,
    )

    # Get portfolio
    portfolio = session.get(Portfolio, portfolio_id)
    if not portfolio:
        raise ValueError(f"Portfolio {portfolio_id} not found")

    # Get chart of accounts (use existing, don't create)
    accounts = _get_chart_accounts(session, portfolio_id)

    # Get all open lots (securities still held)
    stmt = (
        select(SecurityLot)
        .join(Holding, SecurityLot.holding_id == Holding.id)
        .where(
            Holding.portfolio_id == portfolio_id,
            SecurityLot.is_closed == False,  # noqa: E712
            SecurityLot.remaining_quantity > 0,
        )
    )
    open_lots = session.execute(stmt).scalars().all()

    if not open_lots:
        return None  # No securities to mark

    # Group lots by ticker and calculate cost basis
    lots_by_ticker: dict[str, list[SecurityLot]] = {}
    cost_basis_by_ticker: dict[str, Decimal] = {}

    for lot in open_lots:
        ticker = lot.security_ticker
        if ticker not in lots_by_ticker:
            lots_by_ticker[ticker] = []
            cost_basis_by_ticker[ticker] = Decimal("0")

        lots_by_ticker[ticker].append(lot)
        cost_basis_by_ticker[ticker] += lot.remaining_quantity * lot.cost_per_share_base

    # Fetch current market prices
    market_data_fetcher = MarketDataFetcher()
    tickers = list(lots_by_ticker.keys())
    prices = market_data_fetcher.get_current_prices(tickers)

    # Calculate market values and unrealized G/L
    # Per IAS 21, separate price effects (IFRS 9) from FX effects (IAS 21)
    currency_converter = CurrencyConverter()
    total_market_value = Decimal("0")
    total_cost_basis = Decimal("0")
    total_price_unrealized_gl = Decimal("0")  # Price changes only
    total_fx_unrealized_gl = Decimal("0")  # FX rate changes only

    for ticker, lots in lots_by_ticker.items():
        # Get security info for currency (needed for both Yahoo Finance and manual prices)
        security_stmt = select(Security).where(Security.ticker == ticker)
        security = session.execute(security_stmt).scalar_one_or_none()
        if not security:
            continue

        # Get current price - try Yahoo Finance first
        price = prices.get(ticker)

        # Fallback: Check for manual price in MarketData table
        # This handles bonds, funds, and other securities not on Yahoo Finance
        if price is None:
            from src.models import MarketData

            manual_price_stmt = (
                select(MarketData)
                .where(
                    MarketData.security_id == security.id,
                    MarketData.is_latest == True,  # noqa: E712
                )
                .order_by(MarketData.timestamp.desc())
                .limit(1)
            )
            manual_price_record = session.execute(manual_price_stmt).scalar_one_or_none()

            if manual_price_record:
                price = float(manual_price_record.price)
            else:
                # Skip securities without any price data
                continue

        # Calculate total quantity for this ticker
        # Lots already store split-adjusted quantities (Option B architecture)
        total_quantity = Decimal("0")
        for lot in lots:
            total_quantity += lot.remaining_quantity

        # Get cost basis for this ticker
        cost_basis = cost_basis_by_ticker[ticker]
        total_cost_basis += cost_basis

        # For foreign currency securities, separate price and FX effects per IAS 21
        if security.currency != portfolio.base_currency:
            import asyncio

            # Get current exchange rate
            current_rate_float = asyncio.run(
                currency_converter.get_rate(
                    from_currency=security.currency,
                    to_currency=portfolio.base_currency,
                    rate_date=as_of_date,
                )
            )
            current_rate = Decimal(str(current_rate_float)) if current_rate_float else Decimal("1.0")

            # Calculate weighted average purchase rate from lots
            total_cost_local = Decimal("0")
            total_cost_base_from_lots = Decimal("0")
            for lot in lots:
                lot_cost_local = lot.remaining_quantity * lot.cost_per_share
                lot_cost_base = lot.remaining_quantity * lot.cost_per_share_base
                total_cost_local += lot_cost_local
                total_cost_base_from_lots += lot_cost_base

            # Weighted average purchase rate
            weighted_avg_rate = (
                total_cost_base_from_lots / total_cost_local
                if total_cost_local > 0
                else current_rate
            )

            # Price in security currency
            price_local = Decimal(str(price))

            # Market value at purchase rate (price effect only)
            market_value_at_purchase_rate = total_quantity * price_local * weighted_avg_rate

            # Market value at current rate (price + FX effect)
            market_value_at_current_rate = total_quantity * price_local * current_rate

            # Unrealized G/L breakdown:
            # 1. Price effect: change in price, measured at purchase rate
            price_unrealized_gl = market_value_at_purchase_rate - cost_basis

            # 2. FX effect (IAS 21): change in exchange rate, measured on COST BASIS
            #    FX gain/loss = cost_basis_local × (current_rate - purchase_rate)
            #    This measures FX impact on what we PAID, not current market value
            cost_basis_local = total_cost_local  # Already calculated above
            fx_unrealized_gl = cost_basis_local * (current_rate - weighted_avg_rate)

            total_price_unrealized_gl += price_unrealized_gl
            total_fx_unrealized_gl += fx_unrealized_gl
            total_market_value += market_value_at_current_rate
        else:
            # Base currency security - no FX effect, only price effect
            price_base = Decimal(str(price))
            market_value = total_quantity * price_base
            price_unrealized_gl = market_value - cost_basis

            total_price_unrealized_gl += price_unrealized_gl
            total_market_value += market_value

    # Calculate total unrealized G/L (for Fair Value Adjustment account)
    total_unrealized_gl = total_price_unrealized_gl + total_fx_unrealized_gl

    # Get existing fair value adjustment balance
    existing_adjustment = get_account_balance(
        session, accounts["fair_value_adjustment"].id, as_of_date
    )

    # Calculate incremental adjustment needed
    incremental_adjustment = total_unrealized_gl - existing_adjustment

    # Check if adjustment is needed (use small threshold for rounding)
    if abs(incremental_adjustment) < Decimal("0.01"):
        return None

    # Create journal entry for incremental adjustment
    # Per IAS 21, separate price effects (IFRS 9) from FX effects (IAS 21)
    entry = JournalEntry(
        portfolio_id=portfolio_id,
        entry_number=get_next_entry_number(session, portfolio_id),
        entry_date=as_of_date,
        posting_date=as_of_date,
        type=JournalEntryType.ADJUSTMENT,
        status=JournalEntryStatus.POSTED,
        description="Mark securities to market (unrealized G/L - price & FX)",
        created_by="system",
    )
    session.add(entry)
    session.flush()

    lines = []
    line_num = 1

    # Calculate incremental price and FX adjustments needed
    # Get existing balances for price and FX unrealized accounts
    existing_price_gains = get_account_balance(
        session, accounts["unrealized_gains"].id, as_of_date
    )
    existing_price_losses = get_account_balance(
        session, accounts["unrealized_losses"].id, as_of_date
    )
    existing_price_unrealized = existing_price_gains - existing_price_losses

    existing_fx_gains = get_account_balance(
        session, accounts["unrealized_currency_gains"].id, as_of_date
    )
    existing_fx_losses = get_account_balance(
        session, accounts["unrealized_currency_losses"].id, as_of_date
    )
    existing_fx_unrealized = existing_fx_gains - existing_fx_losses

    # Calculate incremental adjustments
    incremental_price_adjustment = total_price_unrealized_gl - existing_price_unrealized
    incremental_fx_adjustment = total_fx_unrealized_gl - existing_fx_unrealized

    # Fair Value Adjustment account gets the total adjustment
    if incremental_adjustment > 0:
        # Net gain: DR Fair Value Adjustment
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["fair_value_adjustment"].id,
                line_number=line_num,
                debit_amount=incremental_adjustment,
                credit_amount=Decimal("0"),
                currency=portfolio.base_currency,
                description="Fair value increase",
            )
        )
        line_num += 1
    else:
        # Net loss: CR Fair Value Adjustment
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["fair_value_adjustment"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=abs(incremental_adjustment),
                currency=portfolio.base_currency,
                description="Fair value decrease",
            )
        )
        line_num += 1

    # Price effect - Unrealized Gains/Losses on Investments (IFRS 9)
    if abs(incremental_price_adjustment) >= Decimal("0.01"):
        if incremental_price_adjustment > 0:
            # Price gain: CR Unrealized Gains
            lines.append(
                JournalLine(
                    journal_entry_id=entry.id,
                    account_id=accounts["unrealized_gains"].id,
                    line_number=line_num,
                    debit_amount=Decimal("0"),
                    credit_amount=incremental_price_adjustment,
                    currency=portfolio.base_currency,
                    description="Unrealized gain on investments (price)",
                )
            )
            line_num += 1
        else:
            # Price loss: DR Unrealized Losses
            lines.append(
                JournalLine(
                    journal_entry_id=entry.id,
                    account_id=accounts["unrealized_losses"].id,
                    line_number=line_num,
                    debit_amount=abs(incremental_price_adjustment),
                    credit_amount=Decimal("0"),
                    currency=portfolio.base_currency,
                    description="Unrealized loss on investments (price)",
                )
            )
            line_num += 1

    # FX effect - Unrealized Currency Gains/Losses (IAS 21)
    if abs(incremental_fx_adjustment) >= Decimal("0.01"):
        if incremental_fx_adjustment > 0:
            # FX gain: CR Unrealized Currency Gains
            lines.append(
                JournalLine(
                    journal_entry_id=entry.id,
                    account_id=accounts["unrealized_currency_gains"].id,
                    line_number=line_num,
                    debit_amount=Decimal("0"),
                    credit_amount=incremental_fx_adjustment,
                    currency=portfolio.base_currency,
                    description="Unrealized FX gain on investments (IAS 21)",
                )
            )
            line_num += 1
        else:
            # FX loss: DR Unrealized Currency Losses
            lines.append(
                JournalLine(
                    journal_entry_id=entry.id,
                    account_id=accounts["unrealized_currency_losses"].id,
                    line_number=line_num,
                    debit_amount=abs(incremental_fx_adjustment),
                    credit_amount=Decimal("0"),
                    currency=portfolio.base_currency,
                    description="Unrealized FX loss on investments (IAS 21)",
                )
            )
            line_num += 1

    # Add lines to entry
    for line in lines:
        session.add(line)

    session.flush()

    # Check if entry is balanced (with small tolerance for rounding)
    if not entry.is_balanced:
        # Calculate imbalance
        imbalance = entry.total_debits - entry.total_credits

        # If imbalance is small (<10 cents), add balancing adjustment
        if abs(imbalance) < Decimal("0.10"):
            # Find the Fair Value Adjustment line to adjust
            for line in lines:
                if line.account_id == accounts["fair_value_adjustment"].id:
                    # Adjust to force balance
                    if imbalance > 0:
                        # Too many debits, increase credit or decrease debit
                        if line.credit_amount > 0:
                            line.credit_amount += imbalance
                        else:
                            line.debit_amount -= imbalance
                    else:
                        # Too many credits, increase debit or decrease credit
                        if line.debit_amount > 0:
                            line.debit_amount -= imbalance
                        else:
                            line.credit_amount += imbalance
                    session.flush()
                    break

        # Verify balance after adjustment
        if not entry.is_balanced:
            raise ValueError(
                f"Mark-to-market entry not balanced: "
                f"DR={entry.total_debits}, CR={entry.total_credits}"
            )

    return entry


def mark_currency_to_market(
    session: Session,
    portfolio_id: str,
    cash_account_id: str,
    base_currency: str,
    as_of_date: date,
) -> JournalEntry | None:
    """Mark all foreign currency cash to current exchange rates (IAS 21).

    Creates adjustment entry for unrealized FX gains/losses on foreign currency
    cash positions using currency lot tracking for GAAP/IFRS compliance.

    IAS 21 requires monetary items (cash) in foreign currency to be remeasured
    at current exchange rates at each reporting date, with gains/losses recognized
    in profit or loss.

    This function uses OPEN currency lots (remaining_amount > 0) to calculate
    unrealized FX, similar to how mark_securities_to_market uses open security lots.
    Spent currency creates REALIZED FX gains/losses when allocated.

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        cash_account_id: Cash account ID (unused, kept for API compatibility)
        base_currency: Portfolio base currency
        as_of_date: Date for exchange rates

    Returns:
        Created JournalEntry if adjustment needed, None if no adjustment
    """
    from src.models.currency_lot import CurrencyLot
    from src.services.accounting_service import get_next_entry_number

    # Get chart of accounts (use existing, don't create)
    accounts = _get_chart_accounts(session, portfolio_id)

    # Get portfolio
    portfolio = session.get(Portfolio, portfolio_id)
    if not portfolio:
        raise ValueError(f"Portfolio {portfolio_id} not found")

    # Get actual cash balances (from journal entries)
    # This is the ground truth - what's actually in the bank
    from src.services.accounting_service import get_cash_balances_by_currency

    cash_balances = get_cash_balances_by_currency(session, cash_account_id, as_of_date)

    if not cash_balances:
        return None  # No cash to mark

    # Only process foreign currencies with positive balances
    foreign_currencies_with_cash = {
        curr: amt
        for curr, amt in cash_balances.items()
        if curr != base_currency and amt > Decimal("0.01")  # Exclude base currency and zero balances
    }

    if not foreign_currencies_with_cash:
        return None  # No foreign currency cash to mark

    # Get OPEN currency lots (remaining_amount > 0)
    # With proper lot allocation, remaining amounts should match actual cash balances
    stmt = (
        select(CurrencyLot)
        .where(
            CurrencyLot.remaining_amount > 0,
            CurrencyLot.from_currency == base_currency,
            CurrencyLot.to_currency.in_(list(foreign_currencies_with_cash.keys())),
            CurrencyLot.conversion_date <= as_of_date,
        )
    )
    open_lots = session.execute(stmt).scalars().all()

    if not open_lots:
        return None  # No open lots to mark

    # Calculate book value and current value for each currency
    currency_converter = CurrencyConverter()
    total_book_value = Decimal("0")
    total_current_value = Decimal("0")

    # Group by currency for exchange rate lookups
    currencies_to_mark = set(lot.to_currency for lot in open_lots)

    import asyncio

    for currency in currencies_to_mark:
        # Get current exchange rate
        current_rate_float = asyncio.run(
            currency_converter.get_rate(
                from_currency=currency,
                to_currency=base_currency,
                rate_date=as_of_date,
            )
        )
        current_rate = Decimal(str(current_rate_float)) if current_rate_float else Decimal("1.0")

        # Calculate book value and current value for all lots in this currency
        for lot in open_lots:
            if lot.to_currency != currency:
                continue

            # Book value = proportional cost basis for remaining amount
            # lot.from_amount is EUR paid, lot.to_amount is USD received
            # lot.remaining_amount is USD still held
            lot_book_value = lot.from_amount * (lot.remaining_amount / lot.to_amount)
            total_book_value += lot_book_value

            # Current value at current exchange rate
            lot_current_value = lot.remaining_amount * current_rate
            total_current_value += lot_current_value

    # Calculate unrealized FX gain/loss (IAS 21)
    total_unrealized_fx_gl = total_current_value - total_book_value

    # Get existing cash FX adjustment from previous mark_currency_to_market entries
    existing_cash_fx = Decimal("0")

    prev_entries_stmt = (
        select(JournalEntry)
        .where(
            JournalEntry.portfolio_id == portfolio_id,
            JournalEntry.description == "Mark foreign currency cash to market (IAS 21)",
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date <= as_of_date,
        )
    )
    prev_cash_fx_entries = session.execute(prev_entries_stmt).scalars().all()

    for prev_entry in prev_cash_fx_entries:
        for line in prev_entry.lines:
            if line.account_id == accounts["unrealized_currency_gains"].id:
                existing_cash_fx += line.credit_amount
            elif line.account_id == accounts["unrealized_currency_losses"].id:
                existing_cash_fx -= line.debit_amount

    # Calculate incremental adjustment needed
    unrealized_fx_gl = total_unrealized_fx_gl - existing_cash_fx

    # Check if adjustment is needed (use small threshold for rounding)
    if abs(unrealized_fx_gl) < Decimal("0.01"):
        return None

    # Create journal entry for unrealized FX adjustment
    entry = JournalEntry(
        portfolio_id=portfolio_id,
        entry_number=get_next_entry_number(session, portfolio_id),
        entry_date=as_of_date,
        posting_date=as_of_date,
        type=JournalEntryType.ADJUSTMENT,
        status=JournalEntryStatus.POSTED,
        description="Mark foreign currency cash to market (IAS 21)",
        created_by="system",
    )
    session.add(entry)
    session.flush()

    lines = []
    line_num = 1

    if unrealized_fx_gl > 0:
        # Unrealized gain: DR Cash, CR Unrealized Currency Gains
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=cash_account_id,
                line_number=line_num,
                debit_amount=unrealized_fx_gl,
                credit_amount=Decimal("0"),
                currency=base_currency,
                description="Foreign currency revaluation gain",
            )
        )
        line_num += 1

        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["unrealized_currency_gains"].id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=unrealized_fx_gl,
                currency=base_currency,
                description="Unrealized FX gain (IAS 21)",
            )
        )
    else:
        # Unrealized loss: DR Unrealized Currency Losses, CR Cash
        loss_amount = abs(unrealized_fx_gl)

        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=accounts["unrealized_currency_losses"].id,
                line_number=line_num,
                debit_amount=loss_amount,
                credit_amount=Decimal("0"),
                currency=base_currency,
                description="Unrealized FX loss (IAS 21)",
            )
        )
        line_num += 1

        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=cash_account_id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=loss_amount,
                currency=base_currency,
                description="Foreign currency revaluation loss",
            )
        )

    # Add lines to entry
    for line in lines:
        session.add(line)

    session.flush()

    # Verify entry is balanced
    if not entry.is_balanced:
        raise ValueError(
            f"Currency mark-to-market entry not balanced: "
            f"DR={entry.total_debits}, CR={entry.total_credits}"
        )

    return entry
