"""
Transaction model for stock buy/sell operations.

Tracks individual transactions (buy/sell) for holdings with pricing,
currency conversion, and fee information.
"""

import enum
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.holding import Holding


class TransactionType(str, enum.Enum):
    """Enumeration of transaction types."""

    BUY = "BUY"
    SELL = "SELL"


class Transaction(Base):  # type: ignore[misc,valid-type]
    """
    Represents a buy or sell transaction for a holding.

    Attributes:
        id: Unique identifier for the transaction
        holding_id: Reference to the associated holding
        type: Transaction type (BUY or SELL)
        date: Date when the transaction occurred
        quantity: Number of shares/units traded (must be > 0)
        price: Price per share/unit in the transaction currency (must be > 0)
        currency: ISO 4217 currency code (3 characters)
        exchange_rate: Exchange rate to base currency (must be > 0)
        fees: Transaction fees in base currency (must be >= 0)
        notes: Optional notes about the transaction (max 500 chars)
        created_at: Timestamp when record was created
    """

    __tablename__ = "transactions"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign key to holding
    holding_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("holdings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Transaction details
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType),
        nullable=False,
    )

    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    fees: Mapped[Decimal] = mapped_column(
        Numeric(20, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    holding: Mapped["Holding"] = relationship(
        "Holding",
        back_populates="transactions",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("quantity > 0", name="check_quantity_positive"),
        CheckConstraint("price > 0", name="check_price_positive"),
        CheckConstraint("exchange_rate > 0", name="check_exchange_rate_positive"),
        CheckConstraint("fees >= 0", name="check_fees_non_negative"),
    )

    def __repr__(self) -> str:
        """Return string representation of transaction."""
        return (
            f"<Transaction(id={self.id!r}, "
            f"type={self.type.value}, "
            f"date={self.date}, "
            f"quantity={self.quantity}, "
            f"price={self.price} {self.currency})>"
        )
