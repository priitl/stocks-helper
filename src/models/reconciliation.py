"""Reconciliation model for tracking reconciliation status.

Tracks the reconciliation status between imported transactions and journal entries.
"""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.journal import JournalEntry
    from src.models.transaction import Transaction


class ReconciliationStatus(str, enum.Enum):
    """Reconciliation status for transactions and journal entries."""

    UNRECONCILED = "UNRECONCILED"  # Not yet reconciled
    RECONCILED = "RECONCILED"  # Reconciled and verified
    PENDING = "PENDING"  # Awaiting review
    DISCREPANCY = "DISCREPANCY"  # Has discrepancies


class Reconciliation(Base):  # type: ignore[misc,valid-type]
    """Reconciliation record linking transactions to journal entries.

    Tracks the reconciliation relationship between imported transactions
    and their corresponding journal entries.

    Attributes:
        id: Unique identifier (UUID)
        transaction_id: Transaction being reconciled
        journal_entry_id: Journal entry it reconciles to
        status: Reconciliation status
        notes: Optional reconciliation notes
        reconciled_by: User who performed reconciliation
        reconciled_at: When reconciliation was performed
    """

    __tablename__ = "reconciliations"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign keys
    transaction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,  # One reconciliation per transaction
    )

    journal_entry_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Reconciliation details
    status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus),
        nullable=False,
        default=ReconciliationStatus.RECONCILED,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    reconciled_by: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="system",
    )

    reconciled_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    transaction: Mapped["Transaction"] = relationship(
        "Transaction",
        back_populates="reconciliation",
    )

    journal_entry: Mapped["JournalEntry"] = relationship(
        "JournalEntry",
        back_populates="reconciliations",
    )

    def __repr__(self) -> str:
        """String representation of Reconciliation."""
        return (
            f"<Reconciliation(transaction={self.transaction_id[:8]}, "
            f"entry={self.journal_entry_id[:8]}, "
            f"status={self.status.value})>"
        )
