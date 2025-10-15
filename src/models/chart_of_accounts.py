"""Chart of Accounts model for double-entry bookkeeping.

Defines the account structure for the general ledger following standard
accounting practices with support for multi-level hierarchies.
"""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.journal import JournalLine
    from src.models.portfolio import Portfolio


class AccountType(str, enum.Enum):
    """Standard accounting account types following the accounting equation.

    Assets = Liabilities + Equity + (Revenue - Expenses)
    """

    # Balance Sheet Accounts
    ASSET = "ASSET"  # Debits increase, Credits decrease
    LIABILITY = "LIABILITY"  # Credits increase, Debits decrease
    EQUITY = "EQUITY"  # Credits increase, Debits decrease

    # Income Statement Accounts
    REVENUE = "REVENUE"  # Credits increase, Debits decrease
    EXPENSE = "EXPENSE"  # Debits increase, Credits decrease


class AccountCategory(str, enum.Enum):
    """Detailed account categories for classification."""

    # Asset categories
    CASH = "CASH"
    BANK = "BANK"
    INVESTMENTS = "INVESTMENTS"
    ACCOUNTS_RECEIVABLE = "ACCOUNTS_RECEIVABLE"
    INVENTORY = "INVENTORY"
    PREPAID_EXPENSES = "PREPAID_EXPENSES"
    FIXED_ASSETS = "FIXED_ASSETS"
    INTANGIBLE_ASSETS = "INTANGIBLE_ASSETS"

    # Liability categories
    ACCOUNTS_PAYABLE = "ACCOUNTS_PAYABLE"
    ACCRUED_EXPENSES = "ACCRUED_EXPENSES"
    SHORT_TERM_DEBT = "SHORT_TERM_DEBT"
    LONG_TERM_DEBT = "LONG_TERM_DEBT"

    # Equity categories
    CAPITAL = "CAPITAL"
    RETAINED_EARNINGS = "RETAINED_EARNINGS"
    DIVIDENDS = "DIVIDENDS"

    # Revenue categories
    SALES = "SALES"
    INTEREST_INCOME = "INTEREST_INCOME"
    DIVIDEND_INCOME = "DIVIDEND_INCOME"
    CAPITAL_GAINS = "CAPITAL_GAINS"

    # Expense categories
    COST_OF_GOODS_SOLD = "COST_OF_GOODS_SOLD"
    OPERATING_EXPENSES = "OPERATING_EXPENSES"
    INTEREST_EXPENSE = "INTEREST_EXPENSE"
    TAX_EXPENSE = "TAX_EXPENSE"
    CAPITAL_LOSSES = "CAPITAL_LOSSES"
    FEES_AND_COMMISSIONS = "FEES_AND_COMMISSIONS"


class ChartAccount(Base):  # type: ignore[misc,valid-type]
    """Chart of Accounts entry for double-entry bookkeeping.

    Implements a hierarchical account structure with support for:
    - Multi-level parent-child relationships
    - Account codes (e.g., "1000", "1100.01")
    - Active/inactive status
    - Multi-currency support

    Attributes:
        id: Unique identifier (UUID)
        portfolio_id: Portfolio this chart belongs to
        code: Account code (e.g., "1000", "2100.01")
        name: Account name (e.g., "Cash", "Accounts Payable")
        type: Account type (ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE)
        category: Detailed category for classification
        parent_id: Parent account ID for hierarchical structure
        description: Optional detailed description
        currency: Default currency for this account
        is_active: Whether account is currently in use
        is_system: Whether this is a system account (cannot be deleted)
    """

    __tablename__ = "chart_of_accounts"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Portfolio relationship
    portfolio_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Account identification
    code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Account classification
    type: Mapped[AccountType] = mapped_column(
        Enum(AccountType),
        nullable=False,
        index=True,
    )

    category: Mapped[AccountCategory] = mapped_column(
        Enum(AccountCategory),
        nullable=False,
        index=True,
    )

    # Hierarchical structure
    parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("chart_of_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Account details
    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="EUR",
    )

    # Status flags
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        index=True,
    )

    is_system: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        back_populates="chart_of_accounts",
    )

    parent: Mapped["ChartAccount | None"] = relationship(
        "ChartAccount",
        remote_side=[id],
        back_populates="children",
    )

    children: Mapped[list["ChartAccount"]] = relationship(
        "ChartAccount",
        back_populates="parent",
        cascade="all, delete-orphan",
    )

    journal_lines: Mapped[list["JournalLine"]] = relationship(
        "JournalLine",
        back_populates="account",
        cascade="all, delete-orphan",
    )

    # Table constraints
    __table_args__ = (
        # Unique account code per portfolio
        UniqueConstraint(
            "portfolio_id",
            "code",
            name="uq_account_code_per_portfolio",
        ),
        # Unique account name per portfolio
        UniqueConstraint(
            "portfolio_id",
            "name",
            name="uq_account_name_per_portfolio",
        ),
        # Index for active accounts lookup
        Index(
            "idx_active_accounts",
            "portfolio_id",
            "is_active",
        ),
        # Index for account type lookup
        Index(
            "idx_accounts_by_type",
            "portfolio_id",
            "type",
        ),
    )

    def __repr__(self) -> str:
        """String representation of ChartAccount."""
        return (
            f"<ChartAccount(code={self.code!r}, "
            f"name={self.name!r}, "
            f"type={self.type.value}, "
            f"category={self.category.value})>"
        )

    @property
    def normal_balance(self) -> str:
        """Get the normal balance side for this account type.

        Returns:
            "DEBIT" or "CREDIT"
        """
        if self.type in (AccountType.ASSET, AccountType.EXPENSE):
            return "DEBIT"
        else:  # LIABILITY, EQUITY, REVENUE
            return "CREDIT"

    @property
    def full_code(self) -> str:
        """Get the full hierarchical code including parent codes.

        Example: If parent is "1000" and code is "01", returns "1000.01"

        Returns:
            Full account code
        """
        if self.parent:
            return f"{self.parent.full_code}.{self.code}"
        return self.code

    @property
    def level(self) -> int:
        """Get the hierarchy level (0 for root accounts, 1 for children, etc.).

        Returns:
            Hierarchy level
        """
        if self.parent is None:
            return 0
        return self.parent.level + 1
