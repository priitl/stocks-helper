"""
Holding model representing a stock position in a portfolio.

A holding tracks ownership of a specific stock within a portfolio, including
quantity, purchase information, and provides computed properties for valuation
and performance metrics.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.portfolio import Portfolio
    from src.models.stock import Stock
    from src.models.transaction import Transaction


class Holding(Base):  # type: ignore[misc,valid-type]
    """
    Represents a stock holding within a portfolio.

    A holding tracks the ownership of a specific stock, including quantity,
    average purchase price, and purchase dates. Supports multi-currency
    tracking with original transaction currency.

    Attributes:
        id: Unique identifier for the holding
        portfolio_id: Reference to the parent portfolio
        ticker: Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        quantity: Number of shares held (supports fractional shares)
        avg_purchase_price: Average price paid per share in original currency
        original_currency: ISO 4217 currency code (3 chars, e.g., 'USD', 'EUR')
        first_purchase_date: Date of the initial purchase of this stock
        created_at: Timestamp when the holding was created
        updated_at: Timestamp when the holding was last modified
    """

    __tablename__ = "holdings"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign keys
    portfolio_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("stocks.ticker", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Holding details
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=False,
        doc="Number of shares held (supports fractional shares)",
    )
    avg_purchase_price: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=False,
        doc="Average purchase price per share in original currency",
    )
    original_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        doc="ISO 4217 currency code (e.g., USD, EUR, GBP)",
    )
    first_purchase_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        doc="Date of the first purchase of this stock",
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        back_populates="holdings",
        doc="The portfolio this holding belongs to",
    )
    stock: Mapped["Stock"] = relationship(
        "Stock",
        back_populates="holdings",
        doc="The stock being held",
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="holding",
        cascade="all, delete-orphan",
        doc="All transactions associated with this holding",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("quantity > 0", name="holdings_quantity_positive"),
        CheckConstraint("avg_purchase_price > 0", name="holdings_avg_price_positive"),
        CheckConstraint("LENGTH(original_currency) = 3", name="holdings_currency_iso4217"),
        UniqueConstraint("portfolio_id", "ticker", name="holdings_portfolio_ticker_unique"),
    )

    # Computed properties (stubs - will be implemented with market data service)
    @property
    def current_value(self) -> Optional[Decimal]:
        """
        Current market value of the holding (quantity * current_price).

        Returns None until market data service is implemented.
        Requires: current market price from market data service.
        """
        return None

    @property
    def gain_loss(self) -> Optional[Decimal]:
        """
        Total gain or loss in base currency (current_value - total_cost).

        Returns None until market data service is implemented.
        Requires: current_value, currency conversion to base currency.
        """
        return None

    @property
    def gain_loss_pct(self) -> Optional[Decimal]:
        """
        Percentage gain or loss ((gain_loss / total_cost) * 100).

        Returns None until market data service is implemented.
        Requires: gain_loss, total_cost.
        """
        return None

    def __repr__(self) -> str:
        """String representation of the holding."""
        return (
            f"<Holding(id={self.id}, ticker='{self.ticker}', "
            f"quantity={self.quantity}, avg_price={self.avg_purchase_price} "
            f"{self.original_currency})>"
        )
