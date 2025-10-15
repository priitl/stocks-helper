"""
StockRecommendation model for storing AI-generated buy/sell/hold recommendations.

Tracks recommendation decisions with technical and fundamental analysis scores,
confidence levels, and detailed rationale.
"""

import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Enum,
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


class RecommendationType(str, enum.Enum):
    """Enum for recommendation types."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class ConfidenceLevel(str, enum.Enum):
    """Enum for confidence levels."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class StockRecommendation(Base):  # type: ignore[misc,valid-type]
    """
    Represents an AI-generated stock recommendation.

    Combines technical and fundamental analysis to provide buy/sell/hold
    recommendations with confidence levels and detailed supporting signals.

    Attributes:
        id: Unique identifier (UUID)
        security_id: Security identifier (foreign key to securities.id)
        portfolio_id: Portfolio UUID (foreign key to portfolios.id)
        timestamp: When recommendation was generated
        recommendation: BUY, SELL, or HOLD
        confidence: HIGH, MEDIUM, or LOW
        technical_score: Technical analysis score (0-100)
        fundamental_score: Fundamental analysis score (0-100)
        combined_score: Combined analysis score (0-100)
        technical_signals: JSON object with technical indicators
        fundamental_signals: JSON object with fundamental metrics
        rationale: Human-readable explanation (max 1000 chars)

    Relationships:
        - Stock: Many-to-one relationship with stocks
        - Portfolio: Many-to-one relationship with portfolios
    """

    __tablename__ = "stock_recommendations"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        comment="Unique recommendation identifier",
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
        comment="Portfolio identifier",
    )

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        comment="Recommendation generation timestamp",
    )

    # Recommendation and confidence
    recommendation: Mapped[RecommendationType] = mapped_column(
        Enum(RecommendationType),
        nullable=False,
        comment="Recommendation type (BUY, SELL, HOLD)",
    )

    confidence: Mapped[ConfidenceLevel] = mapped_column(
        Enum(ConfidenceLevel),
        nullable=False,
        comment="Confidence level (HIGH, MEDIUM, LOW)",
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

    combined_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Combined analysis score (0-100)",
    )

    # Signal data (JSON)
    technical_signals: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="Technical indicators and signals",
    )

    fundamental_signals: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="Fundamental metrics and signals",
    )

    # Rationale
    rationale: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="Human-readable recommendation rationale",
    )

    # Relationships
    security: Mapped["Security"] = relationship(
        "Security",
        back_populates="stock_recommendations",
        lazy="select",
    )

    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        back_populates="recommendations",
        lazy="select",
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "technical_score >= 0 AND technical_score <= 100",
            name="technical_score_range",
        ),
        CheckConstraint(
            "fundamental_score >= 0 AND fundamental_score <= 100",
            name="fundamental_score_range",
        ),
        CheckConstraint(
            "combined_score >= 0 AND combined_score <= 100",
            name="combined_score_range",
        ),
        # Index for querying latest recommendations by portfolio
        Index("ix_recommendations_portfolio_timestamp", "portfolio_id", "timestamp"),
        # Performance index for portfolio+security queries
        Index("idx_recommendations_portfolio_security", "portfolio_id", "security_id"),
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"StockRecommendation(id={self.id!r}, "
            f"security_id={self.security_id!r}, "
            f"portfolio_id={self.portfolio_id!r}, "
            f"recommendation={self.recommendation.value!r}, "
            f"confidence={self.confidence.value!r}, "
            f"combined_score={self.combined_score})"
        )
