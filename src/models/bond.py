"""
Bond model - bond-specific data.

Contains fields specific to fixed-income securities (bonds).
Joins with Security table in a one-to-one relationship.
"""

import enum
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import TIMESTAMP, Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.cashflow import Cashflow
    from src.models.security import Security


class PaymentFrequency(str, enum.Enum):
    """Bond coupon payment frequency."""

    ANNUAL = "ANNUAL"
    SEMI_ANNUAL = "SEMI_ANNUAL"
    QUARTERLY = "QUARTERLY"
    MONTHLY = "MONTHLY"


class Bond(Base):  # type: ignore[misc,valid-type]
    """
    Bond-specific data.

    Joined to Security table via security_id.
    Contains fields specific to fixed-income securities.

    Attributes:
        security_id: Foreign key to securities table (also serves as PK)
        issuer: Bond issuer name (e.g., "IUTECREDIT", "BIGBANK")
        coupon_rate: Annual coupon rate as percentage (e.g., 11.0 for 11%)
        maturity_date: Date when bond matures and principal is repaid
        face_value: Par value per bond (e.g., 1000 EUR)
        payment_frequency: How often coupons are paid
        updated_at: When bond data was last updated
    """

    __tablename__ = "bonds"

    # Primary key and foreign key to Security
    security_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("securities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Bond-specific fields
    issuer: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    coupon_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),  # e.g., 11.000000 for 11%
        nullable=False,
    )

    maturity_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    face_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 2),
        nullable=False,
        default=Decimal("1000.00"),  # Standard face value
    )

    payment_frequency: Mapped[PaymentFrequency] = mapped_column(
        Enum(PaymentFrequency),
        nullable=False,
        default=PaymentFrequency.SEMI_ANNUAL,
    )

    # Audit field
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    security: Mapped["Security"] = relationship(
        "Security",
        back_populates="bond",
    )

    cashflows: Mapped[list["Cashflow"]] = relationship(
        "Cashflow",
        back_populates="bond",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Return string representation of bond."""
        return (
            f"<Bond(security_id={self.security_id!r}, "
            f"issuer={self.issuer!r}, "
            f"coupon={self.coupon_rate}%, "
            f"maturity={self.maturity_date})>"
        )
