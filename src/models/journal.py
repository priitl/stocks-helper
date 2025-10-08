"""Journal Entry models for double-entry bookkeeping.

Implements journal entries with debit/credit lines following GAAP principles.
"""

import enum
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.chart_of_accounts import ChartAccount
    from src.models.portfolio import Portfolio
    from src.models.reconciliation import Reconciliation


class JournalEntryType(str, enum.Enum):
    """Types of journal entries."""

    OPENING_BALANCE = "OPENING_BALANCE"  # Opening balances
    TRANSACTION = "TRANSACTION"  # Regular transactions
    ADJUSTMENT = "ADJUSTMENT"  # Manual adjustments
    ACCRUAL = "ACCRUAL"  # Accruals
    REVERSAL = "REVERSAL"  # Reversing entries
    CLOSING = "CLOSING"  # Closing entries


class JournalEntryStatus(str, enum.Enum):
    """Journal entry posting status."""

    DRAFT = "DRAFT"  # Not yet posted
    POSTED = "POSTED"  # Posted to ledger
    VOIDED = "VOIDED"  # Voided/cancelled


class JournalEntry(Base):  # type: ignore[misc,valid-type]
    """Journal entry header for double-entry bookkeeping.

    A journal entry consists of:
    - Header (this model): date, description, status
    - Lines (JournalLine): debits and credits that must balance

    Attributes:
        id: Unique identifier (UUID)
        portfolio_id: Portfolio this entry belongs to
        entry_number: Sequential number for tracking
        entry_date: Transaction date
        posting_date: When entry was posted
        type: Entry type (TRANSACTION, ADJUSTMENT, etc.)
        status: DRAFT, POSTED, or VOIDED
        description: Entry description
        reference: External reference (e.g., transaction ID)
        created_by: User or system that created entry
    """

    __tablename__ = "journal_entries"

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

    # Entry identification
    entry_number: Mapped[int] = mapped_column(
        nullable=False,
        index=True,
    )

    entry_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    posting_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    # Entry classification
    type: Mapped[JournalEntryType] = mapped_column(
        Enum(JournalEntryType),
        nullable=False,
        default=JournalEntryType.TRANSACTION,
    )

    status: Mapped[JournalEntryStatus] = mapped_column(
        Enum(JournalEntryStatus),
        nullable=False,
        default=JournalEntryStatus.DRAFT,
        index=True,
    )

    # Entry details
    description: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    created_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="system",
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
        back_populates="journal_entries",
    )

    lines: Mapped[list["JournalLine"]] = relationship(
        "JournalLine",
        back_populates="journal_entry",
        cascade="all, delete-orphan",
    )

    reconciliations: Mapped[list["Reconciliation"]] = relationship(
        "Reconciliation",
        back_populates="journal_entry",
        cascade="all, delete-orphan",
    )

    # Table constraints
    __table_args__ = (
        # Index for date range queries
        Index(
            "idx_journal_entries_date",
            "portfolio_id",
            "entry_date",
        ),
        # Index for posted entries
        Index(
            "idx_journal_entries_status",
            "portfolio_id",
            "status",
        ),
    )

    def __repr__(self) -> str:
        """String representation of JournalEntry."""
        return (
            f"<JournalEntry(number={self.entry_number}, "
            f"date={self.entry_date}, "
            f"status={self.status.value}, "
            f"description={self.description!r})>"
        )

    @property
    def is_balanced(self) -> bool:
        """Check if debits equal credits.

        Returns:
            True if entry is balanced
        """
        total_debits = sum(line.debit_amount for line in self.lines)
        total_credits = sum(line.credit_amount for line in self.lines)
        return total_debits == total_credits

    @property
    def total_debits(self) -> Decimal:
        """Get total debits for this entry.

        Returns:
            Total debit amount
        """
        return sum((line.debit_amount for line in self.lines), Decimal("0"))

    @property
    def total_credits(self) -> Decimal:
        """Get total credits for this entry.

        Returns:
            Total credit amount
        """
        return sum((line.credit_amount for line in self.lines), Decimal("0"))


class JournalLine(Base):  # type: ignore[misc,valid-type]
    """Journal entry line (debit or credit) for double-entry bookkeeping.

    Each line represents either a debit or credit to an account.
    A complete journal entry has multiple lines where total debits = total credits.

    Attributes:
        id: Unique identifier (UUID)
        journal_entry_id: Parent journal entry
        account_id: Chart of accounts entry
        line_number: Line sequence within entry
        description: Line description
        debit_amount: Debit amount (0 if credit)
        credit_amount: Credit amount (0 if debit)
        currency: Transaction currency
        foreign_amount: Amount in foreign currency (if applicable)
        foreign_currency: Foreign currency code
        exchange_rate: Exchange rate used
    """

    __tablename__ = "journal_lines"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign keys
    journal_entry_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chart_of_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Line details
    line_number: Mapped[int] = mapped_column(
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Amounts (one must be zero)
    # Numeric(20, 8) for exact accounting with fractional shares
    debit_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        default=Decimal("0.00"),
    )

    credit_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        default=Decimal("0.00"),
    )

    # Currency handling
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    foreign_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    foreign_currency: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
    )

    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        default=Decimal("1.0"),
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    journal_entry: Mapped["JournalEntry"] = relationship(
        "JournalEntry",
        back_populates="lines",
    )

    account: Mapped["ChartAccount"] = relationship(
        "ChartAccount",
        back_populates="journal_lines",
    )

    # Table constraints
    __table_args__ = (
        # Ensure only debit OR credit (not both)
        CheckConstraint(
            "(debit_amount > 0 AND credit_amount = 0) OR "
            "(credit_amount > 0 AND debit_amount = 0) OR "
            "(debit_amount = 0 AND credit_amount = 0)",
            name="ck_debit_or_credit",
        ),
        # Index for account balance calculations
        Index(
            "idx_journal_lines_account",
            "account_id",
            "journal_entry_id",
        ),
    )

    def __repr__(self) -> str:
        """String representation of JournalLine."""
        amount = self.debit_amount if self.debit_amount > 0 else self.credit_amount
        side = "DR" if self.debit_amount > 0 else "CR"
        return f"<JournalLine(account={self.account_id}, " f"{side} {amount} {self.currency})>"

    @property
    def amount(self) -> Decimal:
        """Get the line amount (debit or credit).

        Returns:
            Line amount (always positive)
        """
        return self.debit_amount if self.debit_amount > 0 else self.credit_amount

    @property
    def is_debit(self) -> bool:
        """Check if this is a debit line.

        Returns:
            True if debit, False if credit
        """
        return self.debit_amount > 0
