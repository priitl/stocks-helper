"""
Import error model for tracking validation failures during CSV import.

Stores detailed error information for manual intervention and correction.
"""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import TIMESTAMP, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.import_batch import ImportBatch


class ImportErrorType(str, enum.Enum):
    """Enumeration of import error types."""

    VALIDATION = "validation"
    PARSE = "parse"
    UNKNOWN_TICKER = "unknown_ticker"
    DATABASE = "database"
    OTHER = "other"


class ImportError(Base):  # type: ignore[misc,valid-type]
    """
    Represents a validation error during CSV import.

    Attributes:
        id: Unique identifier for the error
        batch_id: Reference to the import batch
        row_number: Row number in the CSV file (1-indexed)
        error_type: Type of error (validation, parse, unknown_ticker, etc.)
        error_message: Human-readable error message
        original_data: Original CSV row data as JSON
        suggested_fix: Suggested correction (e.g., fuzzy match results for ticker)
        resolved: Whether the error has been resolved
        created_at: Timestamp when error was recorded
    """

    __tablename__ = "import_errors"

    # Primary key
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # Foreign key to import batch
    batch_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("import_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Error details
    row_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    error_type: Mapped[ImportErrorType] = mapped_column(
        Enum(ImportErrorType),
        nullable=False,
        index=True,
    )

    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Original row data
    original_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    # Suggested fixes (e.g., fuzzy match results)
    suggested_fix: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Resolution status
    resolved: Mapped[bool] = mapped_column(
        Integer,  # SQLite doesn't have native boolean
        nullable=False,
        default=0,
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    batch: Mapped["ImportBatch"] = relationship(
        "ImportBatch",
        back_populates="errors",
    )

    def __repr__(self) -> str:
        """Return string representation of import error."""
        return (
            f"<ImportError(id={self.id}, "
            f"batch_id={self.batch_id}, "
            f"row={self.row_number}, "
            f"type={self.error_type.value}, "
            f"resolved={bool(self.resolved)})>"
        )
