"""Contract tests for ImportService.

These tests verify that the ImportService implementation adheres to the contract
defined in specs/002-bulk-transaction-import/contracts/import_service.py

Run with: pytest -m contract tests/contract/test_import_service_contract.py
"""

from pathlib import Path

import pytest

from src.services.import_service import (
    CSVParseError,
    ImportService,
)


@pytest.mark.contract
class TestImportServiceContract:
    """Contract tests for ImportService implementation.

    These tests verify that ImportService correctly handles CSV imports,
    duplicate detection, validation errors, and ticker correction workflows.
    """

    @pytest.fixture
    def service(self):
        """Provide ImportService instance without ticker validation."""
        return ImportService()

    @pytest.fixture
    def service_with_validation(self):
        """Provide ImportService instance with ticker validation enabled."""
        # Known tickers for testing
        known_tickers = {
            "AAPL",  # For fuzzy matching APPL -> AAPL
            "GOOG",
            "MSFT",
            "V",
            "EQNR",
            "ICSUSSDP",
            "TKM1T.TL",  # Regional ticker with .TL suffix
        }
        return ImportService(known_tickers=known_tickers)

    @pytest.fixture
    def test_csv_dir(self):
        """Path to test CSV directory."""
        return Path(__file__).parent.parent / "fixtures" / "csv"

    def test_import_csv_success(self, service, test_csv_dir):
        """ImportService successfully imports valid CSV."""
        csv_path = test_csv_dir / "buy_transactions_only.csv"

        result = service.import_csv(csv_path, broker_type="lightyear")

        assert result.total_rows == 10
        assert result.successful_count == 10
        assert result.duplicate_count == 0
        assert result.error_count == 0
        assert result.unknown_ticker_count == 0
        assert result.requires_ticker_review is False
        assert len(result.errors_requiring_intervention) == 0
        assert result.batch_id > 0

    def test_import_csv_with_duplicates(self, service, test_csv_dir):
        """ImportService skips duplicate transactions on re-import."""
        csv_path = test_csv_dir / "buy_transactions_only.csv"

        # First import
        result1 = service.import_csv(csv_path, broker_type="lightyear")
        assert result1.successful_count == 10

        # Second import (all duplicates)
        result2 = service.import_csv(csv_path, broker_type="lightyear")
        assert result2.successful_count == 0
        assert result2.duplicate_count == 10
        assert result2.error_count == 0

    def test_import_csv_with_validation_errors(self, service, test_csv_dir):
        """ImportService imports valid rows and reports invalid rows."""
        csv_path = test_csv_dir / "mixed_8_valid_2_invalid.csv"

        result = service.import_csv(csv_path, broker_type="lightyear")

        assert result.total_rows == 10
        assert result.successful_count == 8
        assert result.error_count == 2
        assert len(result.errors_requiring_intervention) == 2

        # Verify errors contain original row data
        for error in result.errors_requiring_intervention:
            assert error.row_number > 0
            assert error.error_type in ("parse", "validation", "unknown_ticker")
            assert error.error_message != ""
            assert error.original_row_data is not None

    def test_import_csv_dry_run(self, service, test_csv_dir):
        """ImportService validates without committing in dry run mode."""
        csv_path = test_csv_dir / "valid_10_rows.csv"

        result = service.import_csv(csv_path, broker_type="lightyear", dry_run=True)

        assert result.total_rows == 10
        assert result.successful_count == 10
        # Dry run should not create batch record (batch_id = 0 or None)
        assert result.batch_id == 0 or result.batch_id is None

    def test_import_csv_file_not_found(self, service):
        """ImportService raises FileNotFoundError for missing file."""
        nonexistent_path = Path("/tmp/nonexistent_file_xyz.csv")

        with pytest.raises(FileNotFoundError):
            service.import_csv(nonexistent_path, broker_type="swedbank")

    def test_import_csv_invalid_broker_type(self, service, test_csv_dir):
        """ImportService raises ValueError for invalid broker type."""
        csv_path = test_csv_dir / "valid_10_rows.csv"

        with pytest.raises(ValueError, match="Invalid broker_type"):
            service.import_csv(csv_path, broker_type="invalid_broker")

    def test_import_csv_wrong_delimiter(self, service, test_csv_dir):
        """ImportService raises CSVParseError for wrong CSV format."""
        # Comma-delimited CSV but expecting semicolon (Swedbank)
        csv_path = test_csv_dir / "valid_10_rows.csv"  # Lightyear format

        with pytest.raises(CSVParseError):
            service.import_csv(csv_path, broker_type="swedbank")

    def test_get_import_history(self, service, test_csv_dir):
        """ImportService returns recent import history."""
        # Import 3 CSV files
        csv_path = test_csv_dir / "valid_10_rows.csv"
        service.import_csv(csv_path, broker_type="lightyear")
        service.import_csv(csv_path, broker_type="lightyear")
        service.import_csv(csv_path, broker_type="lightyear")

        history = service.get_import_history(limit=10)

        assert len(history) >= 3
        # Should be ordered by timestamp DESC (most recent first)
        for i in range(len(history) - 1):
            assert history[i].upload_timestamp >= history[i + 1].upload_timestamp

        # Verify structure
        batch = history[0]
        assert batch.batch_id > 0
        assert batch.filename != ""
        assert batch.broker_type in ("swedbank", "lightyear")
        assert batch.status in ("pending", "processing", "completed", "failed", "needs_review")

    def test_get_import_errors(self, service, test_csv_dir):
        """ImportService returns detailed errors for batch."""
        csv_path = test_csv_dir / "mixed_8_valid_2_invalid.csv"
        result = service.import_csv(csv_path, broker_type="lightyear")

        errors = service.get_import_errors(result.batch_id)

        assert len(errors) == 2
        # Should be ordered by row_number ASC
        assert errors[0].row_number <= errors[1].row_number

        # Each error has original data
        for error in errors:
            assert error.original_row_data is not None
            assert isinstance(error.original_row_data, dict)

    def test_get_import_errors_nonexistent_batch(self, service):
        """ImportService raises ValueError for nonexistent batch."""
        with pytest.raises(ValueError, match="Batch .* not found"):
            service.get_import_errors(999999)

    def test_import_with_unknown_tickers(self, service_with_validation, test_csv_dir):
        """ImportService detects unknown tickers and provides suggestions."""
        csv_path = test_csv_dir / "with_unknown_tickers.csv"  # 7 valid, 3 unknown

        result = service_with_validation.import_csv(csv_path, broker_type="lightyear")

        assert result.successful_count == 7
        assert result.error_count == 3
        assert result.unknown_ticker_count == 3
        assert result.requires_ticker_review is True
        assert len(result.unknown_tickers) == 3

        # Verify unknown ticker structure
        unknown = result.unknown_tickers[0]
        assert unknown.ticker != ""
        assert unknown.row_number > 0
        assert isinstance(unknown.suggestions, list)
        assert unknown.transaction_preview != ""

    def test_get_unknown_tickers(self, service_with_validation, test_csv_dir):
        """ImportService returns unknown tickers with fuzzy match suggestions."""
        csv_path = test_csv_dir / "with_unknown_tickers.csv"
        result = service_with_validation.import_csv(csv_path, broker_type="lightyear")

        unknowns = service_with_validation.get_unknown_tickers(result.batch_id)

        assert len(unknowns) == 3
        for unknown in unknowns:
            assert unknown.ticker != ""
            assert unknown.suggestions is not None  # May be empty list
            assert unknown.transaction_preview != ""

    def test_correct_ticker_single_row(self, service_with_validation, test_csv_dir):
        """ImportService corrects ticker and imports transaction."""
        csv_path = test_csv_dir / "with_typo_appl.csv"
        result = service_with_validation.import_csv(csv_path, broker_type="lightyear")

        # Find row with "APPL" typo
        unknown = result.unknown_tickers[0]
        row_num = unknown.row_number

        # Correct to "AAPL"
        imported_count = service_with_validation.correct_ticker(result.batch_id, [row_num], "AAPL")

        assert imported_count == 1
        # Verify ticker count updated
        unknowns_after = service_with_validation.get_unknown_tickers(result.batch_id)
        assert len(unknowns_after) == len(result.unknown_tickers) - 1

    def test_correct_ticker_multiple_rows(self, service_with_validation, test_csv_dir):
        """ImportService corrects multiple rows with same ticker."""
        csv_path = test_csv_dir / "with_multiple_appl.csv"  # 3 rows with APPL
        result = service_with_validation.import_csv(csv_path, broker_type="lightyear")

        # Get all APPL rows
        appl_rows = [u.row_number for u in result.unknown_tickers if u.ticker == "APPL"]
        assert len(appl_rows) == 3

        # Correct all at once
        imported_count = service_with_validation.correct_ticker(result.batch_id, appl_rows, "AAPL")

        assert imported_count == 3

    def test_correct_ticker_still_invalid(self, service_with_validation, test_csv_dir):
        """ImportService raises ValidationError if corrected ticker still invalid."""
        csv_path = test_csv_dir / "with_unknown_xyzz.csv"
        result = service_with_validation.import_csv(csv_path, broker_type="lightyear")

        unknown = result.unknown_tickers[0]

        with pytest.raises(ValueError, match="Corrected ticker .* is also invalid"):
            service_with_validation.correct_ticker(result.batch_id, [unknown.row_number], "ABCD")

    def test_ignore_unknown_tickers(self, service_with_validation, test_csv_dir):
        """ImportService imports transactions with unknown tickers."""
        csv_path = test_csv_dir / "with_regional_tkm1t.csv"
        result = service_with_validation.import_csv(csv_path, broker_type="lightyear")

        unknown = result.unknown_tickers[0]
        assert unknown.ticker == "TKM1T"

        # Import as-is without validation
        imported_count = service_with_validation.ignore_unknown_tickers(
            result.batch_id, [unknown.row_number]
        )

        assert imported_count == 1

    def test_delete_error_rows(self, service_with_validation, test_csv_dir):
        """ImportService deletes error rows."""
        csv_path = test_csv_dir / "with_unknown_tickers.csv"
        result = service_with_validation.import_csv(csv_path, broker_type="lightyear")

        # Delete 2 of 3 unknown tickers
        rows_to_delete = [
            result.unknown_tickers[0].row_number,
            result.unknown_tickers[1].row_number,
        ]
        deleted_count = service_with_validation.delete_error_rows(result.batch_id, rows_to_delete)

        assert deleted_count == 2

        # Verify only 1 unknown ticker remains
        unknowns_after = service_with_validation.get_unknown_tickers(result.batch_id)
        assert len(unknowns_after) == 1

    def test_resolve_all_unknown_tickers_updates_status(
        self, service_with_validation, test_csv_dir
    ):
        """ImportService updates batch status to completed when all tickers resolved."""
        csv_path = test_csv_dir / "with_single_unknown.csv"
        result = service_with_validation.import_csv(csv_path, broker_type="lightyear")

        assert result.requires_ticker_review is True

        # Correct the only unknown ticker
        unknown = result.unknown_tickers[0]
        service_with_validation.correct_ticker(result.batch_id, [unknown.row_number], "AAPL")

        # Check status updated
        history = service_with_validation.get_import_history(limit=1)
        batch = history[0]
        assert batch.batch_id == result.batch_id
        assert batch.status == "completed"
        assert batch.unknown_ticker_count == 0
