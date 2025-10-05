"""FundamentalData model for storing fundamental analysis metrics."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
    TIMESTAMP,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base


class FundamentalData(Base):
    """
    Fundamental analysis data for stocks including ratios and growth metrics.

    Stores key financial metrics with composite primary key (ticker, timestamp).
    All ratio and percentage fields are nullable to handle missing data.
    """

    __tablename__ = "fundamental_data"

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

    # Valuation Ratios
    pe_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Price-to-Earnings ratio",
    )
    pb_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Price-to-Book ratio",
    )
    peg_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Price/Earnings to Growth ratio",
    )

    # Profitability Metrics (Percentages)
    roe: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Return on Equity (percentage)",
    )
    roa: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Return on Assets (percentage)",
    )
    profit_margin: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Profit margin (percentage)",
    )

    # Growth Metrics (Percentages)
    revenue_growth_yoy: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Year-over-year revenue growth (percentage)",
    )
    earnings_growth_yoy: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Year-over-year earnings growth (percentage)",
    )

    # Financial Health Ratios
    debt_to_equity: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Debt-to-Equity ratio",
    )
    current_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Current ratio (current assets / current liabilities)",
    )

    # Dividend Metrics
    dividend_yield: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Dividend yield (percentage)",
    )

    # Metadata
    data_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Source of the fundamental data (e.g., 'yahoo_finance', 'alpha_vantage')",
    )

    # Relationships
    stock = relationship("Stock", back_populates="fundamental_data")

    # Table Arguments (Constraints)
    __table_args__ = (
        # Dividend yield must be non-negative
        CheckConstraint(
            "dividend_yield >= 0 OR dividend_yield IS NULL",
            name="ck_fundamental_data_dividend_yield_non_negative",
        ),
        # PE ratio should be within reasonable range (negative possible, but < 1000)
        CheckConstraint(
            "pe_ratio < 1000 OR pe_ratio IS NULL",
            name="ck_fundamental_data_pe_ratio_reasonable",
        ),
    )

    def __repr__(self) -> str:
        """String representation of FundamentalData."""
        return (
            f"FundamentalData(ticker={self.ticker!r}, "
            f"timestamp={self.timestamp.isoformat()!r}, "
            f"pe_ratio={self.pe_ratio}, "
            f"pb_ratio={self.pb_ratio}, "
            f"roe={self.roe}, "
            f"data_source={self.data_source!r})"
        )
