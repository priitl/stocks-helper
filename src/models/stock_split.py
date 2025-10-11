"""
Stock Split model for tracking split/reverse split events.

Stock splits affect historical prices and quantities, requiring retroactive
adjustments to transaction data. This model stores split events and their ratios
to enable accurate historical position calculation.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import TIMESTAMP, CheckConstraint, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.security import Security


class StockSplit(Base):  # type: ignore[misc,valid-type]
    """
    Records stock split/reverse split events for accurate historical tracking.

    Stock splits change the number of outstanding shares and proportionally
    adjust the share price. This model tracks these events to enable proper
    historical position and cost basis calculations.

    Attributes:
        id: Unique identifier
        security_id: Reference to the security that split
        split_date: Effective date of the split
        split_ratio: Ratio of the split (e.g., 2.0 for 2:1, 0.5 for 1:2 reverse)
        split_from: Shares before split (e.g., 1 for 2-for-1)
        split_to: Shares after split (e.g., 2 for 2-for-1)
        ex_dividend_date: Ex-dividend date (if different from split date)
        notes: Optional notes about the split
        created_at: When this split record was created

    Examples:
        2-for-1 split: split_from=1, split_to=2, split_ratio=2.0
        1-for-10 reverse: split_from=10, split_to=1, split_ratio=0.1
        3-for-2 split: split_from=2, split_to=3, split_ratio=1.5
    """

    __tablename__ = "stock_splits"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign key
    security_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Split details
    split_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        doc="Effective date of the stock split",
    )

    split_ratio: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=4),
        nullable=False,
        doc="Multiplication factor (e.g., 2.0 for 2:1, 0.1 for 1:10 reverse)",
    )

    split_from: Mapped[int] = mapped_column(
        nullable=False,
        doc="Number of shares before split (e.g., 1 for 2-for-1)",
    )

    split_to: Mapped[int] = mapped_column(
        nullable=False,
        doc="Number of shares after split (e.g., 2 for 2-for-1)",
    )

    ex_dividend_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        doc="Ex-dividend date if different from split date",
    )

    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Optional notes about the split event",
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    security: Mapped["Security"] = relationship(
        "Security",
        back_populates="stock_splits",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("split_ratio > 0", name="split_ratio_positive"),
        CheckConstraint("split_from > 0", name="split_from_positive"),
        CheckConstraint("split_to > 0", name="split_to_positive"),
    )

    def __repr__(self) -> str:
        """String representation of stock split."""
        return (
            f"<StockSplit(security_id={self.security_id!r}, "
            f"date={self.split_date}, "
            f"ratio={self.split_from}:{self.split_to} ({self.split_ratio}))>"
        )
