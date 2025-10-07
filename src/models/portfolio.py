"""
Portfolio model for managing investment portfolios.

Each portfolio contains holdings and insights, tracked in a specific base currency.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.account import Account
    from src.models.chart_of_accounts import ChartAccount
    from src.models.holding import Holding
    from src.models.insight import Insight
    from src.models.journal import JournalEntry
    from src.models.recommendation import StockRecommendation
    from src.models.suggestion import StockSuggestion


class Portfolio(Base):  # type: ignore[misc,valid-type]
    """
    Portfolio model representing an investment portfolio.

    Attributes:
        id: Unique identifier (UUID)
        name: Portfolio name
        base_currency: ISO 4217 currency code (e.g., 'USD', 'EUR')
        created_at: Timestamp when portfolio was created
        updated_at: Timestamp when portfolio was last updated
        holdings: Related holdings in this portfolio
        insights: Related insights for this portfolio
    """

    __tablename__ = "portfolios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    accounts: Mapped[list["Account"]] = relationship(
        "Account", back_populates="portfolio", cascade="all, delete-orphan"
    )
    holdings: Mapped[list["Holding"]] = relationship(
        "Holding", back_populates="portfolio", cascade="all, delete-orphan"
    )
    insights: Mapped[list["Insight"]] = relationship(
        "Insight", back_populates="portfolio", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["StockRecommendation"]] = relationship(
        "StockRecommendation", back_populates="portfolio", cascade="all, delete-orphan"
    )
    suggestions: Mapped[list["StockSuggestion"]] = relationship(
        "StockSuggestion", back_populates="portfolio", cascade="all, delete-orphan"
    )
    chart_of_accounts: Mapped[list["ChartAccount"]] = relationship(
        "ChartAccount", back_populates="portfolio", cascade="all, delete-orphan"
    )
    journal_entries: Mapped[list["JournalEntry"]] = relationship(
        "JournalEntry", back_populates="portfolio", cascade="all, delete-orphan"
    )

    @validates("base_currency")
    def validate_base_currency(self, key: str, value: str) -> str:
        """
        Validate base_currency is a 3-character ISO 4217 code.

        Args:
            key: Field name being validated
            value: Currency code to validate

        Returns:
            Uppercase currency code

        Raises:
            ValueError: If currency code is not 3 characters
        """
        if not value or len(value) != 3:
            raise ValueError(f"base_currency must be a 3-character ISO 4217 code, got: {value!r}")
        return value.upper()

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<Portfolio(id={self.id!r}, name={self.name!r}, "
            f"base_currency={self.base_currency!r})>"
        )
