"""
Security model - base class for all tradeable securities (stocks, bonds, ETFs, etc.).

Provides common fields and relationships for all security types.
Specific data is stored in joined tables (Stock, Bond, etc.).
"""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import TIMESTAMP, Boolean, CheckConstraint, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.bond import Bond
    from src.models.cashflow import Cashflow
    from src.models.fundamental_data import FundamentalData
    from src.models.holding import Holding
    from src.models.market_data import MarketData
    from src.models.recommendation import StockRecommendation
    from src.models.stock_details import Stock
    from src.models.stock_split import StockSplit
    from src.models.suggestion import StockSuggestion


class SecurityType(str, enum.Enum):
    """Types of securities that can be tracked."""

    STOCK = "STOCK"
    BOND = "BOND"
    ETF = "ETF"
    FUND = "FUND"


class Security(Base):  # type: ignore[misc,valid-type]
    """
    Base model for all tradeable securities.

    This is the parent table in a joined-table inheritance pattern.
    Specific security types (Stock, Bond) store additional data in their own tables.

    Attributes:
        id: Unique identifier
        security_type: Type of security (STOCK, BOND, ETF, FUND)
        ticker: Trading ticker symbol (e.g., "AAPL", "TSLA") - primarily for stocks
        isin: International Securities Identification Number (e.g., "US0378331005")
        name: Full security name
        currency: Trading currency (ISO 4217 code)
        created_at: Timestamp when record was created
        updated_at: Timestamp when record was last updated
    """

    __tablename__ = "securities"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Security type
    security_type: Mapped[SecurityType] = mapped_column(
        Enum(SecurityType),
        nullable=False,
        index=True,
    )

    # Identifiers (at least one required)
    ticker: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        unique=True,
        index=True,
    )

    isin: Mapped[str | None] = mapped_column(
        String(12),
        nullable=True,
        unique=True,
        index=True,
    )

    # Common fields
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    # Status fields
    archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        doc="True if security is no longer trading (delisted, matured, etc.)",
    )

    # Audit fields
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

    # Relationships - one-to-one with specific security type tables
    stock: Mapped["Stock | None"] = relationship(
        "Stock",
        back_populates="security",
        uselist=False,
        cascade="all, delete-orphan",
    )

    bond: Mapped["Bond | None"] = relationship(
        "Bond",
        back_populates="security",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # One-to-many relationships
    holdings: Mapped[list["Holding"]] = relationship(
        "Holding",
        back_populates="security",
        cascade="all, delete-orphan",
    )

    cashflows: Mapped[list["Cashflow"]] = relationship(
        "Cashflow",
        back_populates="security",
        cascade="all, delete-orphan",
    )

    market_data: Mapped[list["MarketData"]] = relationship(
        "MarketData",
        back_populates="security",
        cascade="all, delete-orphan",
    )

    fundamental_data: Mapped[list["FundamentalData"]] = relationship(
        "FundamentalData",
        back_populates="security",
        cascade="all, delete-orphan",
    )

    stock_recommendations: Mapped[list["StockRecommendation"]] = relationship(
        "StockRecommendation",
        back_populates="security",
        cascade="all, delete-orphan",
    )

    stock_suggestions: Mapped[list["StockSuggestion"]] = relationship(
        "StockSuggestion",
        back_populates="security",
        cascade="all, delete-orphan",
    )

    stock_splits: Mapped[list["StockSplit"]] = relationship(
        "StockSplit",
        back_populates="security",
        cascade="all, delete-orphan",
        order_by="StockSplit.split_date.desc()",
        doc="Stock split events for this security",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "ticker IS NOT NULL OR isin IS NOT NULL",
            name="check_ticker_or_isin_required",
        ),
    )

    def __repr__(self) -> str:
        """Return string representation of security."""
        identifier = self.ticker or self.isin
        return (
            f"<Security(id={self.id!r}, "
            f"type={self.security_type.value}, "
            f"identifier={identifier!r}, "
            f"name={self.name!r})>"
        )
