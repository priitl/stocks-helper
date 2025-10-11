"""
Stock model - stock-specific data.

Contains additional fields specific to stocks (exchange, sector, etc.).
Joins with Security table in a one-to-one relationship.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import TIMESTAMP, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.security import Security


class Stock(Base):  # type: ignore[misc,valid-type]
    """
    Stock-specific data.

    Joined to Security table via security_id.
    Contains fields specific to equity securities.

    Attributes:
        security_id: Foreign key to securities table (also serves as PK)
        exchange: Exchange where stock trades (e.g., "NASDAQ", "NYSE", "TSE")
        sector: Business sector (e.g., "Technology", "Healthcare")
        industry: Specific industry within sector
        country: Country of incorporation (e.g., "United States", "Estonia")
        region: Geographic region (e.g., "North America", "Europe")
        market_cap: Market capitalization in billions (optional)
        updated_at: When stock data was last updated
    """

    __tablename__ = "stocks"

    # Primary key and foreign key to Security
    security_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("securities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Stock-specific fields
    exchange: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    sector: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    industry: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    country: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    region: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    market_cap: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    # Audit field
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship back to Security
    security: Mapped["Security"] = relationship(
        "Security",
        back_populates="stock",
    )

    def __repr__(self) -> str:
        """Return string representation of stock."""
        return (
            f"<Stock(security_id={self.security_id!r}, "
            f"exchange={self.exchange!r}, "
            f"sector={self.sector!r})>"
        )
