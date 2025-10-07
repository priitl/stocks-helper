"""
Account model for broker/bank accounts.

Represents a trading account (Lightyear, Swedbank, etc.) within a portfolio.
All transactions belong to an account.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import TIMESTAMP, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.portfolio import Portfolio
    from src.models.transaction import Transaction


class Account(Base):  # type: ignore[misc,valid-type]
    """
    Represents a broker or bank account within a portfolio.

    Examples: "My Lightyear Account", "Swedbank Trading", etc.

    Attributes:
        id: Unique identifier
        portfolio_id: Reference to the portfolio this account belongs to
        name: User-friendly account name (e.g., "Lightyear", "Swedbank")
        broker_source: System identifier for broker (e.g., "lightyear", "swedbank")
        account_number: Optional account number (e.g., "EE112200221075108020")
        base_currency: Base currency for the account (default: EUR)
        created_at: When the account was created
    """

    __tablename__ = "accounts"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign key to portfolio
    portfolio_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Account details
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    broker_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    account_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    base_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="EUR",
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        back_populates="accounts",
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="account",
        cascade="all, delete-orphan",
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "broker_source",
            "account_number",
            name="unique_portfolio_broker_account",
        ),
    )

    def __repr__(self) -> str:
        """Return string representation of account."""
        return (
            f"<Account(id={self.id!r}, "
            f"name={self.name!r}, "
            f"broker_source={self.broker_source!r})>"
        )
