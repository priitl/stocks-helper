"""
Import Service Contract

Defines the interface for the CSV import service.
This contract specifies expected behavior, not implementation.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Protocol


@dataclass
class ImportSummary:
    """Summary of import operation results."""

    batch_id: int
    total_rows: int
    successful_count: int
    duplicate_count: int
    error_count: int
    unknown_ticker_count: int
    processing_duration: float  # seconds
    requires_ticker_review: bool  # True if unknown_ticker_count > 0
    errors_requiring_intervention: List["ImportErrorDetail"]
    unknown_tickers: List["UnknownTickerDetail"]


@dataclass
class ImportErrorDetail:
    """Details of a single import error for manual review."""

    row_number: int
    error_type: (
        str  # 'parse', 'validation', 'unknown_ticker', 'missing_required_field', 'invalid_format'
    )
    error_message: str
    original_row_data: dict  # Original CSV row as dict


@dataclass
class UnknownTickerDetail:
    """Details of an unknown ticker requiring manual review."""

    row_number: int
    ticker: str
    suggestions: List[str]  # Fuzzy match suggestions (e.g., ["AAPL", "APL"])
    confidence: List[str]  # Confidence per suggestion (e.g., ["high", "low"])
    transaction_preview: str  # E.g., "Buy 10 shares @ $150.00"
    original_row_data: dict  # Original CSV row for reference


class ImportService(Protocol):
    """
    Service for importing transactions from broker CSV files.

    Contract Guarantees:
    - Duplicate transactions (by broker_reference_id) are skipped, not imported
    - Invalid rows are collected and returned for manual intervention
    - Valid rows are imported even when invalid rows exist (no rollback on partial failure)
    - All imports are tracked in import_batch table with metadata
    - Original CSV data preserved in import_errors for failed rows
    """

    def import_csv(self, filepath: Path, broker_type: str, dry_run: bool = False) -> ImportSummary:
        """
        Import transactions from CSV file.

        Args:
            filepath: Path to CSV file
            broker_type: 'swedbank' or 'lightyear'
            dry_run: If True, validate but don't commit to database

        Returns:
            ImportSummary with counts and errors requiring manual intervention

        Raises:
            FileNotFoundError: CSV file doesn't exist
            ValueError: broker_type not in ['swedbank', 'lightyear']
            CSVParseError: File format invalid (wrong delimiter, encoding)
            DatabaseError: Database connection or transaction failure

        Behavior:
        - Creates ImportBatch record with status 'pending'
        - Updates status to 'processing' during import
        - Updates status to 'completed' on success, 'failed' on unrecoverable error
        - Skips duplicate transactions (matches broker_source + broker_reference_id)
        - Collects validation errors, continues importing valid rows
        - Records processing_duration in ImportBatch
        - Commits transaction only if not dry_run

        Performance:
        - Must handle CSV files up to 50,000 rows
        - Target: < 30 seconds for 10,000 transactions
        - Memory: < 200MB during import
        """
        ...

    def get_import_history(self, limit: int = 10) -> List["ImportBatchInfo"]:
        """
        Get recent import history.

        Args:
            limit: Maximum number of batches to return

        Returns:
            List of ImportBatchInfo ordered by upload_timestamp DESC

        Contract:
        - Returns most recent imports first
        - Includes summary counts (successful, duplicate, error)
        - Does not include detailed error messages (use get_import_errors for details)
        """
        ...

    def get_import_errors(self, batch_id: int) -> List[ImportErrorDetail]:
        """
        Get detailed errors for a specific import batch.

        Args:
            batch_id: ImportBatch ID

        Returns:
            List of ImportErrorDetail with original CSV data

        Raises:
            ValueError: batch_id doesn't exist

        Contract:
        - Returns all errors for batch, ordered by row_number
        - Includes original CSV row data for manual correction
        - Empty list if batch had no errors
        """
        ...

    def get_unknown_tickers(self, batch_id: int) -> List[UnknownTickerDetail]:
        """
        Get unknown tickers from import batch for manual review.

        Args:
            batch_id: ImportBatch ID

        Returns:
            List of UnknownTickerDetail with fuzzy match suggestions

        Raises:
            ValueError: batch_id doesn't exist

        Contract:
        - Returns only errors with error_type='unknown_ticker'
        - Ordered by row_number
        - Includes fuzzy match suggestions when available
        - Empty list if no unknown tickers
        """
        ...

    def correct_ticker(self, batch_id: int, row_numbers: List[int], corrected_ticker: str) -> int:
        """
        Correct ticker for specific rows and re-import transactions.

        Args:
            batch_id: ImportBatch ID
            row_numbers: List of row numbers to correct
            corrected_ticker: New ticker to use

        Returns:
            Number of transactions successfully imported after correction

        Raises:
            ValueError: batch_id doesn't exist or row_numbers invalid
            ValidationError: corrected_ticker still invalid

        Contract:
        - Updates original_row_data with corrected ticker
        - Re-validates corrected ticker (must be valid in market data APIs)
        - Imports corrected transactions
        - Removes corrected rows from import_errors table
        - Decrements unknown_ticker_count in ImportBatch
        - Updates batch status to 'completed' if all tickers resolved
        """
        ...

    def ignore_unknown_tickers(self, batch_id: int, row_numbers: List[int]) -> int:
        """
        Mark unknown tickers as "keep as-is" and import them anyway.

        Args:
            batch_id: ImportBatch ID
            row_numbers: List of row numbers to import with unknown tickers

        Returns:
            Number of transactions imported

        Raises:
            ValueError: batch_id doesn't exist or row_numbers invalid

        Contract:
        - Imports transactions with unknown tickers (no market data validation)
        - Removes rows from import_errors table
        - Decrements unknown_ticker_count in ImportBatch
        - Updates batch status to 'completed' if all tickers resolved
        - Transactions importable even if API lookups fail later
        """
        ...

    def delete_error_rows(self, batch_id: int, row_numbers: List[int]) -> int:
        """
        Delete error rows (don't import these transactions).

        Args:
            batch_id: ImportBatch ID
            row_numbers: List of row numbers to delete

        Returns:
            Number of rows deleted

        Raises:
            ValueError: batch_id doesn't exist or row_numbers invalid

        Contract:
        - Removes rows from import_errors table
        - Decrements error_count and total_rows in ImportBatch
        - Decrements unknown_ticker_count if any deleted rows were unknown tickers
        - Updates batch status to 'completed' if no errors remain
        """
        ...


@dataclass
class ImportBatchInfo:
    """Summary information about an import batch."""

    batch_id: int
    filename: str
    broker_type: str
    upload_timestamp: datetime
    total_rows: int
    successful_count: int
    duplicate_count: int
    error_count: int
    unknown_ticker_count: int
    status: str  # 'pending', 'processing', 'completed', 'failed', 'needs_review'
    processing_duration: float


# Exception Types


class CSVParseError(Exception):
    """Raised when CSV file cannot be parsed."""

    def __init__(self, message: str, row_number: int | None = None):
        self.row_number = row_number
        super().__init__(message)


class DatabaseError(Exception):
    """Raised when database operation fails."""

    pass


# Contract Test Cases


class TestImportServiceContract:
    """
    Contract tests to verify ImportService implementation.

    These tests must pass for any implementation of ImportService.
    """

    def test_import_csv_success(self, service: ImportService, valid_csv_path: Path):
        """
        Given: Valid CSV file with 10 transactions
        When: import_csv called
        Then: ImportSummary shows 10 successful, 0 errors
        And: 10 transactions exist in database
        And: ImportBatch record created with status 'completed'
        """
        pass

    def test_import_csv_with_duplicates(self, service: ImportService, csv_path: Path):
        """
        Given: CSV file with 10 transactions
        And: Same 10 transactions already imported
        When: import_csv called again
        Then: ImportSummary shows 0 successful, 10 duplicates, 0 errors
        And: No new transactions created in database
        """
        pass

    def test_import_csv_with_validation_errors(
        self, service: ImportService, invalid_csv_path: Path
    ):
        """
        Given: CSV with 8 valid rows, 2 invalid rows (missing ticker, negative price)
        When: import_csv called
        Then: ImportSummary shows 8 successful, 2 errors
        And: 8 transactions exist in database
        And: 2 ImportError records created with original row data
        And: errors_requiring_intervention contains 2 errors with details
        """
        pass

    def test_import_csv_dry_run(self, service: ImportService, valid_csv_path: Path):
        """
        Given: Valid CSV file with 10 transactions
        When: import_csv called with dry_run=True
        Then: ImportSummary returned with counts
        And: 0 transactions in database (nothing committed)
        And: No ImportBatch record created
        """
        pass

    def test_import_csv_file_not_found(self, service: ImportService):
        """
        Given: Nonexistent CSV file path
        When: import_csv called
        Then: FileNotFoundError raised
        And: No database changes
        """
        pass

    def test_import_csv_invalid_broker_type(self, service: ImportService, csv_path: Path):
        """
        Given: Valid CSV file
        When: import_csv called with broker_type='invalid'
        Then: ValueError raised with message "Invalid broker_type: must be 'swedbank' or 'lightyear'"
        """
        pass

    def test_import_csv_wrong_delimiter(self, service: ImportService):
        """
        Given: CSV file with wrong delimiter (expected ';', got ',')
        When: import_csv called with broker_type='swedbank'
        Then: CSVParseError raised
        And: ImportBatch status set to 'failed'
        """
        pass

    def test_get_import_history(self, service: ImportService):
        """
        Given: 15 import batches in database
        When: get_import_history(limit=10) called
        Then: Returns 10 most recent batches ordered by timestamp DESC
        And: Each batch includes summary counts
        """
        pass

    def test_get_import_errors(self, service: ImportService, batch_with_errors: int):
        """
        Given: ImportBatch with 3 errors
        When: get_import_errors(batch_id) called
        Then: Returns 3 ImportErrorDetail records
        And: Each error includes original_row_data
        And: Ordered by row_number ASC
        """
        pass

    def test_get_import_errors_nonexistent_batch(self, service: ImportService):
        """
        Given: Nonexistent batch_id
        When: get_import_errors(999999) called
        Then: ValueError raised
        """
        pass

    def test_import_with_unknown_tickers(
        self, service: ImportService, csv_with_unknown_tickers: Path
    ):
        """
        Given: CSV with 10 rows: 7 valid tickers, 3 unknown (APPL, XYZZ, TKM1T)
        When: import_csv called
        Then: ImportSummary shows:
            - successful_count = 7
            - error_count = 3
            - unknown_ticker_count = 3
            - requires_ticker_review = True
            - status = 'needs_review'
        And: unknown_tickers list has 3 items with suggestions
        """
        pass

    def test_get_unknown_tickers(self, service: ImportService, batch_with_unknown: int):
        """
        Given: Import batch with 3 unknown tickers
        When: get_unknown_tickers(batch_id) called
        Then: Returns 3 UnknownTickerDetail records
        And: Each has suggestions (fuzzy matches)
        And: transaction_preview shows "Buy X @ $Y"
        """
        pass

    def test_correct_ticker_single_row(self, service: ImportService, batch_id: int):
        """
        Given: Import batch with unknown ticker "APPL" at row 23
        When: correct_ticker(batch_id, [23], "AAPL") called
        Then: Returns 1 (1 transaction imported)
        And: Row 23 removed from import_errors
        And: unknown_ticker_count decremented
        And: Transaction with "AAPL" exists in database
        """
        pass

    def test_correct_ticker_multiple_rows(self, service: ImportService, batch_id: int):
        """
        Given: Import batch with "APPL" at rows 23, 45, 67
        When: correct_ticker(batch_id, [23, 45, 67], "AAPL") called
        Then: Returns 3 (3 transactions imported)
        And: All 3 rows removed from import_errors
        And: unknown_ticker_count decremented by 3
        """
        pass

    def test_correct_ticker_still_invalid(self, service: ImportService, batch_id: int):
        """
        Given: Import batch with unknown ticker "XYZZ"
        When: correct_ticker(batch_id, [23], "ABCD") called (still unknown)
        Then: ValidationError raised with message "Ticker ABCD not found"
        And: No changes to database
        """
        pass

    def test_ignore_unknown_tickers(self, service: ImportService, batch_id: int):
        """
        Given: Import batch with unknown ticker "TKM1T" (valid Tallinn exchange)
        When: ignore_unknown_tickers(batch_id, [89]) called
        Then: Returns 1 (1 transaction imported with unknown ticker)
        And: Row 89 removed from import_errors
        And: Transaction with "TKM1T" exists in database
        And: unknown_ticker_count decremented
        """
        pass

    def test_delete_error_rows(self, service: ImportService, batch_id: int):
        """
        Given: Import batch with 3 unknown tickers
        When: delete_error_rows(batch_id, [23, 45]) called
        Then: Returns 2 (2 rows deleted)
        And: 2 rows removed from import_errors
        And: error_count decremented by 2
        And: unknown_ticker_count decremented by 2
        And: total_rows decremented by 2
        """
        pass

    def test_resolve_all_unknown_tickers_updates_status(
        self, service: ImportService, batch_id: int
    ):
        """
        Given: Import batch status='needs_review' with 1 unknown ticker
        When: correct_ticker(batch_id, [23], "AAPL") called
        Then: Batch status updated to 'completed'
        And: unknown_ticker_count = 0
        """
        pass
