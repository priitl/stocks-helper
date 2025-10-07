"""Tax reporting service for compliance and tax calculations.

Handles capital gains/losses, dividend income, and tax summaries.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import Holding, Security, Transaction, TransactionType


class CostBasisMethod(str, Enum):
    """Cost basis calculation methods."""

    FIFO = "FIFO"  # First In, First Out
    LIFO = "LIFO"  # Last In, First Out
    AVERAGE = "AVERAGE"  # Average cost


@dataclass
class TaxLot:
    """Represents a tax lot (purchase) for cost basis tracking.

    Attributes:
        transaction_id: Purchase transaction ID
        purchase_date: Date of purchase
        quantity: Quantity purchased
        price_per_share: Purchase price per share
        remaining_quantity: Remaining quantity not yet sold
        cost_basis: Total cost (quantity * price + allocated fees)
    """

    transaction_id: str
    purchase_date: date
    quantity: Decimal
    price_per_share: Decimal
    remaining_quantity: Decimal
    cost_basis: Decimal


@dataclass
class CapitalGain:
    """Represents a capital gain/loss from a sale.

    Attributes:
        security_id: Security sold
        security_name: Security name
        sell_transaction_id: Sale transaction ID
        sell_date: Date of sale
        quantity_sold: Quantity sold
        proceeds: Sale proceeds (quantity * price - fees)
        cost_basis: Cost basis of sold shares
        gain_loss: Capital gain (positive) or loss (negative)
        holding_period_days: Days held
        is_long_term: True if held > 1 year
        tax_lots_used: List of tax lots used for this sale
    """

    security_id: str
    security_name: str
    sell_transaction_id: str
    sell_date: date
    quantity_sold: Decimal
    proceeds: Decimal
    cost_basis: Decimal
    gain_loss: Decimal
    holding_period_days: int
    is_long_term: bool
    tax_lots_used: list[TaxLot]


@dataclass
class DividendIncome:
    """Represents dividend income for tax reporting.

    Attributes:
        security_id: Security ID
        security_name: Security name
        transaction_id: Dividend transaction ID
        payment_date: Dividend payment date
        gross_amount: Gross dividend amount
        withholding_tax: Withholding tax amount
        net_amount: Net dividend received
        currency: Currency
    """

    security_id: str
    security_name: str
    transaction_id: str
    payment_date: date
    gross_amount: Decimal
    withholding_tax: Decimal
    net_amount: Decimal
    currency: str


@dataclass
class AnnualTaxSummary:
    """Annual tax summary report.

    Attributes:
        year: Tax year
        total_dividends: Total dividend income
        total_withholding_tax: Total withholding tax paid
        short_term_gains: Short-term capital gains (≤1 year)
        long_term_gains: Long-term capital gains (>1 year)
        total_capital_gains: Total capital gains/losses
        interest_income: Interest income
        fees_paid: Trading fees paid
        tax_paid: Other taxes paid
    """

    year: int
    total_dividends: Decimal
    total_withholding_tax: Decimal
    short_term_gains: Decimal
    long_term_gains: Decimal
    total_capital_gains: Decimal
    interest_income: Decimal
    fees_paid: Decimal
    tax_paid: Decimal


def get_tax_lots(
    session: Session,
    security_id: str,
    as_of_date: date | None = None,
) -> list[TaxLot]:
    """Get all tax lots (purchases) for a security.

    Retrieves all BUY transactions and calculates remaining quantity
    after accounting for SELL transactions.

    Args:
        session: Database session
        security_id: Security ID
        as_of_date: Calculate lots as of this date (optional)

    Returns:
        List of TaxLot sorted by purchase date (FIFO order)
    """
    # Get all BUY transactions
    buy_stmt = (
        select(Transaction)
        .join(Holding, Transaction.holding_id == Holding.id)
        .where(
            Holding.security_id == security_id,
            Transaction.type == TransactionType.BUY,
        )
    )

    if as_of_date:
        buy_stmt = buy_stmt.where(Transaction.date <= as_of_date)

    buy_stmt = buy_stmt.order_by(Transaction.date)  # FIFO order

    buy_txns = session.execute(buy_stmt).scalars().all()

    # Get all SELL transactions
    sell_stmt = (
        select(Transaction)
        .join(Holding, Transaction.holding_id == Holding.id)
        .where(
            Holding.security_id == security_id,
            Transaction.type == TransactionType.SELL,
        )
    )

    if as_of_date:
        sell_stmt = sell_stmt.where(Transaction.date <= as_of_date)

    sell_stmt = sell_stmt.order_by(Transaction.date)

    sell_txns = session.execute(sell_stmt).scalars().all()

    # Build tax lots
    tax_lots = []
    for buy_txn in buy_txns:
        # Skip if missing required data
        if buy_txn.quantity is None or buy_txn.price is None:
            continue

        # Calculate cost basis (purchase price + allocated fees)
        total_cost = (buy_txn.quantity * buy_txn.price) + buy_txn.fees

        tax_lot = TaxLot(
            transaction_id=buy_txn.id,
            purchase_date=buy_txn.date,
            quantity=buy_txn.quantity,
            price_per_share=buy_txn.price,
            remaining_quantity=buy_txn.quantity,
            cost_basis=total_cost,
        )
        tax_lots.append(tax_lot)

    # Reduce tax lots by SELL transactions (FIFO)
    for sell_txn in sell_txns:
        if sell_txn.quantity is None:
            continue

        quantity_to_sell = sell_txn.quantity

        for lot in tax_lots:
            if quantity_to_sell <= 0:
                break

            if lot.remaining_quantity > 0:
                quantity_from_lot = min(lot.remaining_quantity, quantity_to_sell)
                lot.remaining_quantity -= quantity_from_lot
                quantity_to_sell -= quantity_from_lot

    # Filter to lots with remaining quantity
    return [lot for lot in tax_lots if lot.remaining_quantity > 0]


def calculate_capital_gains(
    session: Session,
    holding_id: str,
    sell_transaction: Transaction,
    method: CostBasisMethod = CostBasisMethod.FIFO,
) -> CapitalGain:
    """Calculate capital gain/loss for a SELL transaction.

    Uses specified cost basis method (FIFO, LIFO, or AVERAGE) to determine
    which tax lots are sold and calculate the gain/loss.

    Args:
        session: Database session
        holding_id: Holding ID
        sell_transaction: SELL transaction
        method: Cost basis method (default: FIFO)

    Returns:
        CapitalGain with detailed calculation
    """
    holding = session.get(Holding, holding_id)
    if not holding:
        raise ValueError(f"Holding {holding_id} not found")

    security = session.get(Security, holding.security_id)
    if not security:
        raise ValueError(f"Security {holding.security_id} not found")

    # Get tax lots as of sell date
    all_lots = get_tax_lots(session, holding.security_id, sell_transaction.date)

    # Apply cost basis method
    if method == CostBasisMethod.FIFO:
        # Already in FIFO order
        lots_to_use = all_lots
    elif method == CostBasisMethod.LIFO:
        # Reverse for LIFO
        lots_to_use = list(reversed(all_lots))
    else:  # AVERAGE
        # For average cost, create a single "virtual" lot
        total_quantity = sum((lot.remaining_quantity for lot in all_lots), Decimal("0"))
        total_cost = sum(
            (lot.cost_basis * (lot.remaining_quantity / lot.quantity) for lot in all_lots),
            Decimal("0"),
        )
        avg_price: Decimal = total_cost / total_quantity if total_quantity > 0 else Decimal("0")

        lots_to_use = [
            TaxLot(
                transaction_id="AVERAGE",
                purchase_date=all_lots[0].purchase_date if all_lots else sell_transaction.date,
                quantity=total_quantity,
                price_per_share=avg_price,
                remaining_quantity=total_quantity,
                cost_basis=total_cost,
            )
        ]

    # Validate sell transaction has required data
    if sell_transaction.quantity is None or sell_transaction.price is None:
        raise ValueError(f"Sell transaction {sell_transaction.id} missing quantity or price")

    # Match sold quantity to tax lots
    quantity_to_sell: Decimal = sell_transaction.quantity
    cost_basis_total = Decimal("0")
    lots_used = []

    for lot in lots_to_use:
        if quantity_to_sell <= 0:
            break

        # Skip if lot has no remaining quantity
        if lot.remaining_quantity <= 0:
            continue

        quantity_from_lot: Decimal = min(lot.remaining_quantity, quantity_to_sell)

        # Calculate proportional cost basis
        if lot.quantity > 0:
            cost_basis_from_lot = lot.cost_basis * (quantity_from_lot / lot.quantity)
        else:
            cost_basis_from_lot = Decimal("0")

        cost_basis_total += cost_basis_from_lot
        quantity_to_sell -= quantity_from_lot

        # Record lot used
        lot_used = TaxLot(
            transaction_id=lot.transaction_id,
            purchase_date=lot.purchase_date,
            quantity=quantity_from_lot,
            price_per_share=lot.price_per_share,
            remaining_quantity=Decimal("0"),  # Fully used for this sale
            cost_basis=cost_basis_from_lot,
        )
        lots_used.append(lot_used)

    # Calculate proceeds (sale price - fees)
    proceeds = (sell_transaction.quantity * sell_transaction.price) - sell_transaction.fees

    # Calculate gain/loss
    gain_loss = proceeds - cost_basis_total

    # Determine holding period (use earliest lot for simplicity)
    if lots_used:
        earliest_purchase = min(lot.purchase_date for lot in lots_used)
        holding_period_days = (sell_transaction.date - earliest_purchase).days
        is_long_term = holding_period_days > 365
    else:
        holding_period_days = 0
        is_long_term = False

    return CapitalGain(
        security_id=holding.security_id,
        security_name=security.name,
        sell_transaction_id=sell_transaction.id,
        sell_date=sell_transaction.date,
        quantity_sold=sell_transaction.quantity,
        proceeds=proceeds,
        cost_basis=cost_basis_total,
        gain_loss=gain_loss,
        holding_period_days=holding_period_days,
        is_long_term=is_long_term,
        tax_lots_used=lots_used,
    )


def get_dividend_income(
    session: Session,
    portfolio_id: str,
    start_date: date,
    end_date: date,
) -> list[DividendIncome]:
    """Get all dividend income for a period.

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        start_date: Period start date
        end_date: Period end date

    Returns:
        List of DividendIncome
    """
    from src.models import Account

    stmt = (
        select(Transaction, Security)
        .join(Account, Transaction.account_id == Account.id)
        .join(Holding, Transaction.holding_id == Holding.id)
        .join(Security, Holding.security_id == Security.id)
        .where(
            Account.portfolio_id == portfolio_id,
            Transaction.type == TransactionType.DIVIDEND,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )
        .order_by(Transaction.date)
    )

    results = session.execute(stmt).all()

    dividends = []
    for txn, security in results:
        dividends.append(
            DividendIncome(
                security_id=security.id,
                security_name=security.name,
                transaction_id=txn.id,
                payment_date=txn.date,
                gross_amount=txn.amount,
                withholding_tax=txn.tax_amount or Decimal("0"),
                net_amount=txn.amount - (txn.tax_amount or Decimal("0")),
                currency=txn.currency,
            )
        )

    return dividends


def get_annual_tax_summary(
    session: Session,
    portfolio_id: str,
    year: int,
) -> AnnualTaxSummary:
    """Generate annual tax summary for a portfolio.

    Calculates all taxable events for the year including:
    - Dividend income
    - Capital gains/losses (short-term and long-term)
    - Interest income
    - Fees paid
    - Taxes paid

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        year: Tax year

    Returns:
        AnnualTaxSummary
    """
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)

    from src.models import Account

    # Get dividend income
    dividends = get_dividend_income(session, portfolio_id, start_date, end_date)
    total_dividends = sum((d.gross_amount for d in dividends), Decimal("0"))
    total_withholding_tax = sum((d.withholding_tax for d in dividends), Decimal("0"))

    # Get capital gains from SELL transactions
    sell_stmt = (
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.portfolio_id == portfolio_id,
            Transaction.type == TransactionType.SELL,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )
    )

    sell_txns = session.execute(sell_stmt).scalars().all()

    short_term_gains = Decimal("0")
    long_term_gains = Decimal("0")

    for sell_txn in sell_txns:
        if sell_txn.holding_id:
            capital_gain = calculate_capital_gains(session, sell_txn.holding_id, sell_txn)

            if capital_gain.is_long_term:
                long_term_gains += capital_gain.gain_loss
            else:
                short_term_gains += capital_gain.gain_loss

    total_capital_gains = short_term_gains + long_term_gains

    # Get interest income
    interest_stmt = (
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.portfolio_id == portfolio_id,
            Transaction.type == TransactionType.INTEREST,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )
    )

    interest_txns = session.execute(interest_stmt).scalars().all()
    interest_income = sum((txn.amount for txn in interest_txns), Decimal("0"))

    # Get fees paid
    fee_stmt = (
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.portfolio_id == portfolio_id,
            Transaction.type == TransactionType.FEE,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )
    )

    fee_txns = session.execute(fee_stmt).scalars().all()
    fees_paid = sum((txn.amount for txn in fee_txns), Decimal("0"))

    # Get taxes paid (besides withholding)
    tax_stmt = (
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.portfolio_id == portfolio_id,
            Transaction.type == TransactionType.TAX,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )
    )

    tax_txns = session.execute(tax_stmt).scalars().all()
    tax_paid = sum((txn.amount for txn in tax_txns), Decimal("0"))

    return AnnualTaxSummary(
        year=year,
        total_dividends=total_dividends,
        total_withholding_tax=total_withholding_tax,
        short_term_gains=short_term_gains,
        long_term_gains=long_term_gains,
        total_capital_gains=total_capital_gains,
        interest_income=interest_income,
        fees_paid=fees_paid,
        tax_paid=tax_paid,
    )
