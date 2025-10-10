"""Security lot tracking models for GAAP/IFRS cost basis accounting.

Tracks individual security purchase lots and their allocations to sales
for proper FIFO cost basis calculation and realized gain/loss reporting.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base


class SecurityLot(Base):  # type: ignore[misc,valid-type]
    """Track individual security purchase lots for FIFO cost basis.

    GAAP/IFRS requires tracking cost basis of individual lots
    to calculate realized gains/losses on sales per IFRS 9.

    Each BUY transaction creates a SecurityLot that tracks:
    - Original purchase quantity and cost
    - Remaining quantity (after partial sales)
    - Cost basis in both transaction and base currency

    Attributes:
        id: Unique identifier
        holding_id: Foreign key to holding
        transaction_id: BUY transaction that created this lot
        security_ticker: Security identifier (ticker or ISIN)
        purchase_date: Date of purchase
        quantity: Original quantity purchased
        remaining_quantity: Quantity remaining after sales
        cost_per_share: Cost per share in transaction currency
        cost_per_share_base: Cost per share in base currency (EUR)
        total_cost: Total cost (quantity * cost_per_share)
        total_cost_base: Total cost in base currency
        currency: Transaction currency
        exchange_rate: Exchange rate used (base per transaction currency)
        is_closed: True when remaining_quantity = 0
        created_at: Record creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "security_lots"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign keys
    holding_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("holdings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # Each BUY transaction creates exactly one lot
        index=True,
    )

    # Security identification
    security_ticker: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    # Purchase details
    purchase_date: Mapped[date] = mapped_column(
        nullable=False,
        index=True,
    )

    # Quantity tracking (Numeric(20, 8) for fractional shares)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    remaining_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    # Cost basis (transaction currency) - Numeric(20, 8) for exact accounting
    cost_per_share: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    # Cost basis (base currency) - Numeric(20, 8) for exact accounting
    cost_per_share_base: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    total_cost_base: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    # Currency information
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    # Status
    is_closed: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(),
        onupdate=lambda: datetime.now(),
        nullable=False,
    )

    # Relationships
    holding: Mapped["Holding"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Holding",
        back_populates="lots",
    )

    transaction: Mapped["Transaction"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Transaction",
        foreign_keys=[transaction_id],
    )

    allocations: Mapped[list["SecurityAllocation"]] = relationship(
        "SecurityAllocation",
        back_populates="lot",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"SecurityLot(ticker={self.security_ticker}, "
            f"purchase_date={self.purchase_date}, "
            f"quantity={self.quantity}, "
            f"remaining={self.remaining_quantity}, "
            f"cost_base={self.cost_per_share_base} {self.currency})"
        )


class SecurityAllocation(Base):  # type: ignore[misc,valid-type]
    """Track which lots were used for each SELL transaction (FIFO matching).

    When securities are sold, this tracks which specific lots were used
    to fulfill the sale (using FIFO method) and the resulting realized
    gain or loss.

    Attributes:
        id: Unique identifier
        lot_id: Foreign key to SecurityLot
        sell_transaction_id: SELL transaction that used this lot
        quantity_allocated: Quantity from this lot used for the sale
        cost_basis: Cost basis for allocated quantity (base currency)
        proceeds: Sale proceeds for allocated quantity (base currency)
        realized_gain_loss: Realized gain/loss (proceeds - cost_basis)
        created_at: Record creation timestamp
    """

    __tablename__ = "security_allocations"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign keys
    lot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("security_lots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sell_transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Allocation details (all in base currency) - Numeric(20, 8) for exact accounting
    quantity_allocated: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    cost_basis: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    proceeds: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    realized_gain_loss: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(),
        nullable=False,
    )

    # Relationships
    lot: Mapped["SecurityLot"] = relationship(
        "SecurityLot",
        back_populates="allocations",
    )

    transaction: Mapped["Transaction"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Transaction",
        foreign_keys=[sell_transaction_id],
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"SecurityAllocation(lot_id={self.lot_id[:8]}, "
            f"quantity={self.quantity_allocated}, "
            f"realized_g_l={self.realized_gain_loss})"
        )
