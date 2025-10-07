"""Cashflow projection service for bonds and dividend-paying securities.

Generates future expected cashflows for portfolio planning and analysis.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.bond import Bond, PaymentFrequency
from src.models.cashflow import Cashflow, CashflowStatus, CashflowType
from src.models.holding import Holding
from src.models.security import Security, SecurityType


@dataclass
class CashflowProjection:
    """Projected cashflow with security details.

    Attributes:
        security_id: Security identifier
        security_name: Security name
        security_type: BOND or STOCK
        cashflow_type: COUPON, PRINCIPAL, or DIVIDEND
        expected_date: Expected payment date
        expected_amount: Expected payment amount
        currency: Payment currency
        status: PENDING, RECEIVED, or MISSED
    """

    security_id: str
    security_name: str
    security_type: SecurityType
    cashflow_type: CashflowType
    expected_date: date
    expected_amount: Decimal
    currency: str
    status: CashflowStatus


def get_payment_frequency_months(frequency: PaymentFrequency) -> int:
    """Convert PaymentFrequency to months between payments.

    Args:
        frequency: Payment frequency enum

    Returns:
        Number of months between payments
    """
    frequency_map = {
        PaymentFrequency.ANNUAL: 12,
        PaymentFrequency.SEMI_ANNUAL: 6,
        PaymentFrequency.QUARTERLY: 3,
        PaymentFrequency.MONTHLY: 1,
    }
    return frequency_map[frequency]


def generate_bond_cashflows(
    session: Session,
    bond: Bond,
    holding: Holding,
    start_date: date,
    end_date: date | None = None,
) -> list[Cashflow]:
    """Generate expected cashflows for a bond holding.

    Creates Cashflow records for:
    - Coupon payments based on payment frequency
    - Principal repayment at maturity

    Args:
        session: Database session
        bond: Bond model instance
        holding: Holding for this bond
        start_date: Start date for projections (typically today)
        end_date: Optional end date (defaults to maturity date)

    Returns:
        List of Cashflow records (not yet added to session)
    """
    if end_date is None:
        end_date = bond.maturity_date

    # Ensure end_date doesn't exceed maturity
    if end_date > bond.maturity_date:
        end_date = bond.maturity_date

    cashflows = []

    # Calculate coupon payment amount
    annual_coupon = bond.face_value * (bond.coupon_rate / Decimal("100"))
    payments_per_year = 12 / get_payment_frequency_months(bond.payment_frequency)
    coupon_payment = annual_coupon / Decimal(str(payments_per_year))

    # Adjust for holding quantity
    coupon_payment = coupon_payment * holding.quantity

    # Generate coupon payments
    months_between = get_payment_frequency_months(bond.payment_frequency)
    current_date = start_date

    while current_date <= end_date:
        # Move to next payment date
        current_date = current_date + relativedelta(months=months_between)

        if current_date <= end_date:
            cashflow = Cashflow(
                security_id=bond.security_id,
                bond_id=bond.security_id,
                type=CashflowType.COUPON,
                expected_date=current_date,
                expected_amount=coupon_payment,
                currency=bond.security.currency,
                status=CashflowStatus.PENDING,
            )
            cashflows.append(cashflow)

    # Add principal repayment at maturity
    if bond.maturity_date >= start_date and bond.maturity_date <= end_date:
        principal_payment = bond.face_value * holding.quantity

        cashflow = Cashflow(
            security_id=bond.security_id,
            bond_id=bond.security_id,
            type=CashflowType.PRINCIPAL,
            expected_date=bond.maturity_date,
            expected_amount=principal_payment,
            currency=bond.security.currency,
            status=CashflowStatus.PENDING,
        )
        cashflows.append(cashflow)

    return cashflows


def get_portfolio_cashflows(
    session: Session,
    portfolio_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    security_types: list[SecurityType] | None = None,
) -> list[CashflowProjection]:
    """Get all projected cashflows for a portfolio.

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        start_date: Start date for projections (defaults to today)
        end_date: End date for projections (defaults to 1 year from start)
        security_types: Optional filter by security types (defaults to all)

    Returns:
        List of CashflowProjection sorted by expected_date
    """
    if start_date is None:
        start_date = date.today()

    if end_date is None:
        end_date = start_date + timedelta(days=365)

    # Query existing cashflows
    stmt = (
        select(Cashflow, Security)
        .join(Security, Cashflow.security_id == Security.id)
        .join(Holding, Security.id == Holding.security_id)
        .where(
            Holding.portfolio_id == portfolio_id,
            Cashflow.expected_date >= start_date,
            Cashflow.expected_date <= end_date,
        )
    )

    if security_types:
        stmt = stmt.where(Security.security_type.in_(security_types))

    stmt = stmt.order_by(Cashflow.expected_date)

    results = session.execute(stmt).all()

    projections = []
    for cashflow, security in results:
        projection = CashflowProjection(
            security_id=security.id,
            security_name=security.name,
            security_type=security.security_type,
            cashflow_type=cashflow.type,
            expected_date=cashflow.expected_date,
            expected_amount=cashflow.expected_amount,
            currency=cashflow.currency,
            status=cashflow.status,
        )
        projections.append(projection)

    return projections


def regenerate_bond_cashflows(
    session: Session,
    portfolio_id: str,
    projection_years: int = 10,
) -> int:
    """Regenerate all cashflow projections for bonds in portfolio.

    Deletes existing PENDING cashflows and regenerates them.

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        projection_years: Years to project into future

    Returns:
        Number of cashflows generated
    """
    start_date = date.today()
    end_date = start_date + timedelta(days=365 * projection_years)

    # Get all bond holdings
    stmt = (
        select(Holding, Security, Bond)
        .join(Security, Holding.security_id == Security.id)
        .join(Bond, Security.id == Bond.security_id)
        .where(
            Holding.portfolio_id == portfolio_id,
            Security.security_type == SecurityType.BOND,
            Holding.quantity > 0,
        )
    )

    holdings = session.execute(stmt).all()

    # Delete existing PENDING cashflows for these securities
    security_ids = [h.Holding.security_id for h in holdings]
    if security_ids:
        delete_stmt = select(Cashflow).where(
            Cashflow.security_id.in_(security_ids),
            Cashflow.status == CashflowStatus.PENDING,
        )
        existing_cashflows = session.execute(delete_stmt).scalars().all()
        for cf in existing_cashflows:
            session.delete(cf)

    # Generate new cashflows
    total_generated = 0
    for holding, security, bond in holdings:
        cashflows = generate_bond_cashflows(
            session,
            bond,
            holding,
            start_date,
            end_date,
        )

        for cf in cashflows:
            session.add(cf)

        total_generated += len(cashflows)

    session.flush()
    return total_generated


def get_cashflow_summary(
    session: Session,
    portfolio_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Decimal]:
    """Get cashflow summary by currency.

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        start_date: Start date (defaults to today)
        end_date: End date (defaults to 1 year from start)

    Returns:
        Dictionary mapping currency to total expected amount
    """
    if start_date is None:
        start_date = date.today()

    if end_date is None:
        end_date = start_date + timedelta(days=365)

    projections = get_portfolio_cashflows(
        session,
        portfolio_id,
        start_date,
        end_date,
    )

    # Sum by currency
    summary: dict[str, Decimal] = {}
    for proj in projections:
        if proj.status == CashflowStatus.PENDING:
            if proj.currency not in summary:
                summary[proj.currency] = Decimal("0")
            summary[proj.currency] += proj.expected_amount

    return summary
