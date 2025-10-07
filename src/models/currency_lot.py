"""
Currency lot tracking model for precise currency gain calculations.

Tracks each currency conversion as a "lot" (similar to stock lots) to enable
accurate FIFO-based allocation of purchases to specific conversion rates.
"""

from datetime import date as date_type
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.account import Account
    from src.models.transaction import Transaction


class CurrencyLot(Base):  # type: ignore[misc,valid-type]
    """
    Represents a currency conversion lot for tracking currency purchases.

    Each conversion transaction creates a currency lot that can be allocated
    to subsequent purchases in that currency. Uses FIFO to track which
    conversion rates apply to which purchases.

    Attributes:
        id: Unique identifier
        account_id: Account that made the conversion
        conversion_transaction_id: The CONVERSION transaction that created this lot
        from_currency: Currency converted from (e.g., EUR)
        to_currency: Currency converted to (e.g., USD)
        from_amount: Amount in source currency
        to_amount: Amount received in target currency
        remaining_amount: Unallocated amount in target currency
        exchange_rate: Exchange rate (to_currency/from_currency)
        conversion_date: Date of conversion
        created_at: Record creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "currency_lots"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign keys
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    conversion_transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # Each conversion transaction creates exactly one lot
        index=True,
    )

    # Currencies
    from_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        comment="Source currency code (ISO 4217)",
    )

    to_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        comment="Target currency code (ISO 4217)",
    )

    # Amounts
    from_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=False,
        comment="Amount in source currency",
    )

    to_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=False,
        comment="Amount received in target currency",
    )

    remaining_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=False,
        comment="Unallocated amount available for purchases",
    )

    # Exchange rate (for reference, can be calculated from amounts)
    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=False,
        comment="Exchange rate: to_currency per unit of from_currency",
    )

    # Date
    conversion_date: Mapped[date_type] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Date of the conversion",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="currency_lots")
    conversion_transaction: Mapped["Transaction"] = relationship(
        "Transaction",
        foreign_keys=[conversion_transaction_id],
    )
    allocations: Mapped[list["CurrencyAllocation"]] = relationship(
        "CurrencyAllocation",
        back_populates="currency_lot",
        cascade="all, delete-orphan",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("from_amount > 0", name="currency_lot_from_amount_positive"),
        CheckConstraint("to_amount > 0", name="currency_lot_to_amount_positive"),
        CheckConstraint(
            "remaining_amount >= 0", name="currency_lot_remaining_amount_non_negative"
        ),
        CheckConstraint(
            "remaining_amount <= to_amount", name="currency_lot_remaining_lte_total"
        ),
        CheckConstraint("exchange_rate > 0", name="currency_lot_exchange_rate_positive"),
        CheckConstraint("LENGTH(from_currency) = 3", name="currency_lot_from_currency_iso4217"),
        CheckConstraint("LENGTH(to_currency) = 3", name="currency_lot_to_currency_iso4217"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<CurrencyLot(id={self.id}, "
            f"{self.from_currency}->{self.to_currency}, "
            f"rate={self.exchange_rate}, "
            f"remaining={self.remaining_amount}/{self.to_amount})>"
        )


class CurrencyAllocation(Base):  # type: ignore[misc,valid-type]
    """
    Tracks allocation of currency lots to purchases.

    Records which currency lot(s) funded which purchase transaction,
    enabling accurate currency gain calculations based on specific
    conversion rates.

    Attributes:
        id: Unique identifier
        currency_lot_id: The lot from which currency was allocated
        purchase_transaction_id: The BUY transaction that used the currency
        allocated_amount: Amount allocated from this lot (in target currency)
        created_at: Record creation timestamp
    """

    __tablename__ = "currency_allocations"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign keys
    currency_lot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("currency_lots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    purchase_transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Allocation amount
    allocated_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=False,
        comment="Amount allocated from lot to purchase (in target currency)",
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    currency_lot: Mapped["CurrencyLot"] = relationship(
        "CurrencyLot", back_populates="allocations"
    )
    purchase_transaction: Mapped["Transaction"] = relationship(
        "Transaction",
        foreign_keys=[purchase_transaction_id],
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("allocated_amount > 0", name="currency_allocation_amount_positive"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<CurrencyAllocation(lot={self.currency_lot_id[:8]}, "
            f"purchase={self.purchase_transaction_id[:8]}, "
            f"amount={self.allocated_amount})>"
        )
