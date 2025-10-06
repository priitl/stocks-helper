"""
Stock model representing individual stocks and their metadata.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import TIMESTAMP, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.fundamental_data import FundamentalData
    from src.models.holding import Holding
    from src.models.market_data import MarketData
    from src.models.recommendation import StockRecommendation
    from src.models.suggestion import StockSuggestion


class Stock(Base):  # type: ignore[misc,valid-type]
    """
    Represents a stock with its core metadata and market information.

    Relationships:
        - Holdings: Many-to-one relationship with holdings
        - MarketData: Many-to-one relationship with market data points
        - StockRecommendations: Many-to-one relationship with recommendations
    """

    __tablename__ = "stocks"

    # Primary key
    ticker: Mapped[str] = mapped_column(
        String(10),
        primary_key=True,
        comment="Stock ticker symbol",
    )

    # Required fields
    exchange: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Exchange where stock is traded (e.g., NASDAQ, NYSE)",
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Full company name",
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        comment="ISO 4217 currency code (e.g., USD, EUR)",
    )

    last_updated: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.now(),
        comment="Last time stock data was updated",
    )

    # Optional fields
    sector: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Industry sector (e.g., Technology, Healthcare)",
    )

    market_cap: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=20, scale=2),
        nullable=True,
        comment="Market capitalization in the stock's currency",
    )

    country: Mapped[Optional[str]] = mapped_column(
        String(2),
        nullable=True,
        comment="ISO 3166 country code (e.g., US, DE)",
    )

    # Relationships
    holdings: Mapped[list["Holding"]] = relationship(
        "Holding",
        back_populates="stock",
        cascade="all, delete-orphan",
        lazy="select",
    )

    market_data: Mapped[list["MarketData"]] = relationship(
        "MarketData",
        back_populates="stock",
        cascade="all, delete-orphan",
        lazy="select",
    )

    stock_recommendations: Mapped[list["StockRecommendation"]] = relationship(
        "StockRecommendation",
        back_populates="stock",
        cascade="all, delete-orphan",
        lazy="select",
    )

    fundamental_data: Mapped[list["FundamentalData"]] = relationship(
        "FundamentalData",
        back_populates="stock",
        cascade="all, delete-orphan",
        lazy="select",
    )

    suggestions: Mapped[list["StockSuggestion"]] = relationship(
        "StockSuggestion",
        back_populates="stock",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"Stock(ticker={self.ticker!r}, "
            f"name={self.name!r}, "
            f"exchange={self.exchange!r}, "
            f"sector={self.sector!r}, "
            f"market_cap={self.market_cap}, "
            f"currency={self.currency!r})"
        )
