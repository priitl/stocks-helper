"""MarketData model for storing historical and current stock price data."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base


class MarketData(Base):
    """
    Historical and current market data for stocks.

    Stores price, volume, and OHLC data with composite primary key (ticker, timestamp).
    Supports tracking latest prices via is_latest flag.
    """

    __tablename__ = "market_data"

    # Composite Primary Key
    ticker: Mapped[str] = mapped_column(
        String,
        ForeignKey("stocks.ticker"),
        primary_key=True,
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        primary_key=True,
        nullable=False,
    )

    # Price and Volume Data
    price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )
    volume: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    # OHLC Data (nullable for non-intraday data)
    open: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )
    high: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )
    low: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )
    close: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    # Metadata
    data_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    is_latest: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Relationships
    stock = relationship("Stock", back_populates="market_data")

    # Table Arguments (Constraints and Indexes)
    __table_args__ = (
        # Price Constraints
        CheckConstraint("price > 0", name="ck_market_data_price_positive"),
        CheckConstraint("volume >= 0 OR volume IS NULL", name="ck_market_data_volume_non_negative"),
        CheckConstraint("open > 0 OR open IS NULL", name="ck_market_data_open_positive"),
        CheckConstraint("high > 0 OR high IS NULL", name="ck_market_data_high_positive"),
        CheckConstraint("low > 0 OR low IS NULL", name="ck_market_data_low_positive"),
        CheckConstraint("close > 0 OR close IS NULL", name="ck_market_data_close_positive"),
        # OHLC Validation Constraints
        CheckConstraint(
            "high >= low OR high IS NULL OR low IS NULL",
            name="ck_market_data_high_gte_low",
        ),
        CheckConstraint(
            "high >= open OR high IS NULL OR open IS NULL",
            name="ck_market_data_high_gte_open",
        ),
        CheckConstraint(
            "high >= close OR high IS NULL OR close IS NULL",
            name="ck_market_data_high_gte_close",
        ),
        CheckConstraint(
            "low <= open OR low IS NULL OR open IS NULL",
            name="ck_market_data_low_lte_open",
        ),
        CheckConstraint(
            "low <= close OR low IS NULL OR close IS NULL",
            name="ck_market_data_low_lte_close",
        ),
        # Index for fast current price lookups
        Index("ix_market_data_ticker_is_latest", "ticker", "is_latest"),
        # Unique partial index to prevent race conditions
        # Ensures only ONE row per ticker can have is_latest=True
        # This database-level constraint prevents multiple concurrent transactions
        # from creating duplicate latest prices
        Index(
            "ix_market_data_latest_per_ticker",
            "ticker",
            unique=True,
            sqlite_where="is_latest = 1",  # SQLite: Only index rows where is_latest=1
            # Note: For PostgreSQL, would use: postgresql_where=text('is_latest = true')
        ),
        # Performance index for historical data queries (timestamp DESC for newest first)
        Index("idx_market_data_ticker_timestamp", "ticker", "timestamp"),
    )

    def __repr__(self) -> str:
        """String representation of MarketData."""
        return (
            f"MarketData(ticker={self.ticker!r}, "
            f"timestamp={self.timestamp.isoformat()!r}, "
            f"price={self.price}, "
            f"volume={self.volume}, "
            f"is_latest={self.is_latest})"
        )
