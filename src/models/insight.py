"""
Insight model for storing portfolio analysis insights.

Each insight represents a specific analytical finding about a portfolio,
with structured data and a human-readable summary.
"""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import JSON, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.portfolio import Portfolio


class InsightType(enum.Enum):
    """Types of portfolio insights that can be generated."""

    SECTOR_ALLOCATION = "SECTOR_ALLOCATION"
    GEO_ALLOCATION = "GEO_ALLOCATION"
    DIVERSIFICATION_GAP = "DIVERSIFICATION_GAP"
    HIGH_PERFORMERS = "HIGH_PERFORMERS"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    PERFORMANCE_TREND = "PERFORMANCE_TREND"


class Insight(Base):  # type: ignore[misc,valid-type]
    """
    Insight model representing analytical findings about a portfolio.

    Attributes:
        id: Unique identifier (UUID)
        portfolio_id: Foreign key to Portfolio
        timestamp: When the insight was generated
        insight_type: Type of insight (enum)
        data: Structured JSON data containing the insight details
        summary: Human-readable summary (max 500 chars)
        portfolio: Related portfolio
    """

    __tablename__ = "insights"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    portfolio_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("portfolios.id"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    insight_type: Mapped[InsightType] = mapped_column(Enum(InsightType), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="insights")

    # Indexes
    __table_args__ = (Index("ix_insights_portfolio_timestamp", "portfolio_id", "timestamp"),)

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<Insight(id={self.id!r}, portfolio_id={self.portfolio_id!r}, "
            f"type={self.insight_type.value!r}, timestamp={self.timestamp.isoformat()!r})>"
        )
