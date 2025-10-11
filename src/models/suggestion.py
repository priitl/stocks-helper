"""
Stock suggestion model for AI-generated investment suggestions.

Tracks stock suggestions with scoring and analysis for portfolio optimization.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.portfolio import Portfolio
    from src.models.security import Security


class SuggestionType(str, Enum):
    """Type of stock suggestion based on analysis strategy."""

    DIVERSIFICATION = "DIVERSIFICATION"
    SIMILAR_TO_WINNERS = "SIMILAR_TO_WINNERS"
    MARKET_OPPORTUNITY = "MARKET_OPPORTUNITY"


class StockSuggestion(Base):  # type: ignore[misc,valid-type]
    """
    AI-generated stock suggestion with scoring and analysis.

    Attributes:
        id: Unique identifier (UUID)
        security_id: Security identifier
        portfolio_id: Portfolio this suggestion is for
        timestamp: When suggestion was generated
        suggestion_type: Strategy type for this suggestion
        technical_score: Technical analysis score (0-100)
        fundamental_score: Fundamental analysis score (0-100)
        overall_score: Combined overall score (0-100)
        technical_summary: Brief technical analysis (max 500 chars)
        fundamental_summary: Brief fundamental analysis (max 500 chars)
        portfolio_fit: How this fits the portfolio (max 500 chars)
        related_holding_ticker: Optional ticker of related existing holding

    Relationships:
        - stock: The Stock being suggested
        - portfolio: The Portfolio receiving this suggestion
    """

    __tablename__ = "stock_suggestions"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        comment="Unique suggestion identifier",
    )

    # Foreign keys
    security_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
        comment="Security identifier",
    )

    portfolio_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        comment="Portfolio receiving this suggestion",
    )

    # Metadata
    timestamp: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        comment="When suggestion was generated",
    )

    suggestion_type: Mapped[SuggestionType] = mapped_column(
        String(30),
        nullable=False,
        comment="Strategy type for this suggestion",
    )

    # Scores (0-100)
    technical_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Technical analysis score (0-100)",
    )

    fundamental_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Fundamental analysis score (0-100)",
    )

    overall_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Combined overall score (0-100)",
    )

    # Analysis summaries
    technical_summary: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Brief technical analysis summary",
    )

    fundamental_summary: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Brief fundamental analysis summary",
    )

    portfolio_fit: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="How this stock fits the portfolio",
    )

    # Optional related holding
    related_holding_ticker: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="Ticker of related existing holding",
    )

    # Relationships
    security: Mapped["Security"] = relationship(
        "Security",
        back_populates="stock_suggestions",
        lazy="select",
    )

    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        back_populates="suggestions",
        lazy="select",
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "technical_score >= 0 AND technical_score <= 100",
            name="ck_technical_score_range",
        ),
        CheckConstraint(
            "fundamental_score >= 0 AND fundamental_score <= 100",
            name="ck_fundamental_score_range",
        ),
        CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_overall_score_range",
        ),
        Index(
            "ix_suggestions_portfolio_timestamp",
            "portfolio_id",
            "timestamp",
            unique=False,
        ),
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<StockSuggestion(id={self.id!r}, "
            f"security_id={self.security_id!r}, "
            f"portfolio_id={self.portfolio_id!r}, "
            f"type={self.suggestion_type.value}, "
            f"overall_score={self.overall_score})>"
        )
