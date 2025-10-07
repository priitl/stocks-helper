"""
Import batch model for tracking CSV import operations.

Tracks metadata for each CSV import including counts, status, and errors.
"""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import TIMESTAMP, Enum, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.import_error import ImportError
    from src.models.transaction import Transaction


class ImportStatus(str, enum.Enum):
    """Enumeration of import batch statuses."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class ImportBatch(Base):  # type: ignore[misc,valid-type]
    """
    Represents a CSV import batch operation.

    Attributes:
        id: Unique identifier for the batch
        broker_source: Broker name (e.g., 'swedbank', 'lightyear')
        filename: Original CSV filename
        status: Import status (in_progress, completed, needs_review, failed)
        total_rows: Total number of rows in CSV
        successful_count: Number of successfully imported transactions
        duplicate_count: Number of duplicate transactions skipped
        error_count: Number of rows with validation errors
        unknown_ticker_count: Number of rows with unknown tickers
        duration_seconds: Time taken for import operation
        started_at: Timestamp when import started
        completed_at: Timestamp when import finished
        error_message: Error message if import failed
        created_at: Timestamp when record was created
    """

    __tablename__ = "import_batches"

    # Primary key
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # Import metadata
    broker_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus),
        nullable=False,
        default=ImportStatus.IN_PROGRESS,
        index=True,
    )

    # Statistics
    total_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    successful_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    duplicate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    unknown_ticker_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    duration_seconds: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    # Timing
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP,
        nullable=True,
    )

    # Error details
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    errors: Mapped[list["ImportError"]] = relationship(
        "ImportError",
        back_populates="batch",
        cascade="all, delete-orphan",
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="import_batch",
    )

    def __repr__(self) -> str:
        """Return string representation of import batch."""
        return (
            f"<ImportBatch(id={self.id}, "
            f"broker={self.broker_source!r}, "
            f"status={self.status.value}, "
            f"successful={self.successful_count}, "
            f"errors={self.error_count})>"
        )
