"""
Cashflow model - future expected payments from securities.

Tracks expected dividend payments, bond coupons, and principal repayments.
Helps project future cash inflows from the portfolio.
"""

import enum
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import CheckConstraint, Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.bond import Bond
    from src.models.security import Security
    from src.models.transaction import Transaction


class CashflowType(str, enum.Enum):
    """Type of expected cashflow."""

    COUPON = "COUPON"  # Bond interest payment
    PRINCIPAL = "PRINCIPAL"  # Bond maturity/redemption
    DIVIDEND = "DIVIDEND"  # Estimated stock dividend


class CashflowStatus(str, enum.Enum):
    """Status of cashflow."""

    PENDING = "PENDING"  # Future payment
    RECEIVED = "RECEIVED"  # Payment received
    MISSED = "MISSED"  # Payment not received as expected


class Cashflow(Base):  # type: ignore[misc,valid-type]
    """
    Expected future cashflow from a security.

    For bonds: Calculates coupon payments and principal repayment based on
                coupon rate, face value, and payment frequency.
    For stocks: Estimates future dividends based on historical patterns (Phase 2).

    Attributes:
        id: Unique identifier
        security_id: Reference to the security
        bond_id: Optional direct reference to bond (for bond-specific data)
        type: Type of cashflow (COUPON, PRINCIPAL, DIVIDEND)
        expected_date: When payment is expected
        expected_amount: Amount expected to receive
        currency: Currency of payment
        actual_transaction_id: Link to actual transaction when received
        status: Current status (PENDING, RECEIVED, MISSED)
        notes: Optional notes
    """

    __tablename__ = "cashflows"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign keys
    security_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    bond_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("bonds.security_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    actual_transaction_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Cashflow details
    type: Mapped[CashflowType] = mapped_column(
        Enum(CashflowType),
        nullable=False,
        index=True,
    )

    expected_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    expected_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    status: Mapped[CashflowStatus] = mapped_column(
        Enum(CashflowStatus),
        nullable=False,
        default=CashflowStatus.PENDING,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Relationships
    security: Mapped["Security"] = relationship(
        "Security",
        back_populates="cashflows",
    )

    bond: Mapped["Bond | None"] = relationship(
        "Bond",
        back_populates="cashflows",
    )

    actual_transaction: Mapped["Transaction | None"] = relationship(
        "Transaction",
        foreign_keys=[actual_transaction_id],
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "expected_amount > 0",
            name="check_cashflow_amount_positive",
        ),
    )

    def __repr__(self) -> str:
        """Return string representation of cashflow."""
        return (
            f"<Cashflow(id={self.id!r}, "
            f"type={self.type.value}, "
            f"expected_date={self.expected_date}, "
            f"amount={self.expected_amount} {self.currency}, "
            f"status={self.status.value})>"
        )
