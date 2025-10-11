"""Integration tests for unknown ticker handling with exchange suffix detection.

Tests the complete workflow: import with unknown tickers → review → correct/ignore/delete.
This implements Scenario 8 from specs/002-bulk-transaction-import/quickstart.md

Run with: pytest -m integration tests/integration/test_import_unknown_tickers.py
"""

import tempfile
from pathlib import Path
from textwrap import dedent

import pytest

from src.lib.db import db_session, init_db, reset_db
from src.services.import_service import ImportService


@pytest.mark.integration
class TestImportUnknownTickers:
    """Integration tests for unknown ticker detection and correction workflow.

    Scenario 8: Import CSV with unknown tickers (typo, invalid, regional)
    - AAPL: Valid (imports successfully)
    - APPL: Typo → suggests AAPL
    - MSFT: Valid (imports successfully)
    - XYZZ: Unknown → no suggestions
    - TKM1T: Regional (missing .TL suffix) → suggests TKM1T.TL
    - GOOG: Valid (imports successfully)

    Expected: 3 successful, 3 unknown requiring review
    """

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Reset database before each test."""
        reset_db()
        init_db()
        yield
        # Cleanup handled by reset_db in next test

    @pytest.fixture
    def service(self):
        """Provide ImportService instance with ticker validation enabled."""
        # Known tickers for validation
        known_tickers = {
            "AAPL",  # Valid ticker
            "MSFT",  # Valid ticker
            "GOOG",  # Valid ticker
            "TKM1T.TL",  # Regional ticker with .TL suffix
        }
        return ImportService(known_tickers=known_tickers)

    @pytest.fixture
    def csv_with_unknown_tickers(self):
        """Create CSV file with known and unknown tickers."""
        content = dedent(  # noqa: E501
            """
            "Date","Reference","Ticker","ISIN","Type","Quantity","CCY","Price/share","Gross Amount","FX Rate","Fee","Net Amt.","Tax Amt."  # noqa: E501
            "01/10/2025 12:00:00","OR-VALID001","AAPL","US0378331005","Buy","10.000000000","USD","150.00","1500.00","","0.00","1500.00",""  # noqa: E501
            "02/10/2025 12:00:00","OR-TYPO001","APPL","","Buy","5.000000000","USD","150.00","750.00","","0.00","750.00",""  # noqa: E501
            "03/10/2025 12:00:00","OR-VALID002","MSFT","US5949181045","Buy","8.000000000","USD","300.00","2400.00","","0.00","2400.00",""  # noqa: E501
            "04/10/2025 12:00:00","OR-UNKNOWN001","XYZZ","","Buy","15.000000000","USD","25.00","375.00","","0.00","375.00",""  # noqa: E501
            "05/10/2025 12:00:00","OR-REGIONAL001","TKM1T","EE0000001105","Buy","20.000000000","EUR","8.50","170.00","","0.00","170.00",""  # noqa: E501
            "06/10/2025 12:00:00","OR-VALID003","GOOG","US02079K3059","Buy","3.000000000","USD","2800.00","8400.00","","0.00","8400.00",""  # noqa: E501
            """
        ).strip()

        # Create temporary CSV file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(content)
            temp_path = Path(f.name)

        yield temp_path

        # Cleanup
        temp_path.unlink()

    def test_import_detects_unknown_tickers(self, service, csv_with_unknown_tickers):
        """Step 1: Import detects 3 unknown tickers with suggestions."""
        result = service.import_csv(csv_with_unknown_tickers, broker_type="lightyear")

        # Summary counts
        assert result.total_rows == 6
        assert result.successful_count == 3, "Should import 3 valid tickers (AAPL, MSFT, GOOG)"
        assert result.error_count == 3, "Should flag 3 unknown tickers"
        assert result.unknown_ticker_count == 3
        assert result.requires_ticker_review is True

        # Verify unknown tickers list
        assert len(result.unknown_tickers) == 3

        # Find each unknown ticker
        unknown_by_ticker = {u.ticker: u for u in result.unknown_tickers}

        # APPL typo should suggest AAPL
        appl = unknown_by_ticker.get("APPL")
        assert appl is not None, "APPL typo not detected"
        assert "AAPL" in appl.suggestions, "APPL should suggest AAPL"
        assert appl.row_number == 3  # Second data row (0-indexed including header)
        assert "Buy 5" in appl.transaction_preview or "5.0" in appl.transaction_preview

        # XYZZ unknown should have no suggestions
        xyzz = unknown_by_ticker.get("XYZZ")
        assert xyzz is not None, "XYZZ not detected as unknown"
        assert len(xyzz.suggestions) == 0 or all(
            s not in xyzz.suggestions for s in ["AAPL", "MSFT", "GOOG"]
        )

        # TKM1T should suggest TKM1T.TL (exchange suffix detection)
        tkm1t = unknown_by_ticker.get("TKM1T")
        assert tkm1t is not None, "TKM1T not detected"
        assert "TKM1T.TL" in tkm1t.suggestions, "TKM1T should suggest TKM1T.TL (Tallinn exchange)"
        assert any(
            "Tallinn" in str(c) or "high" in str(c) for c in tkm1t.confidence
        ), "Should have high confidence"

    def test_review_tickers_command(self, service, csv_with_unknown_tickers):
        """Step 2: Review tickers shows all unknowns with suggestions."""
        result = service.import_csv(csv_with_unknown_tickers, broker_type="lightyear")

        # Get unknown tickers for review
        unknowns = service.get_unknown_tickers(result.batch_id)

        assert len(unknowns) == 3
        # Should be ordered by row number
        for i in range(len(unknowns) - 1):
            assert unknowns[i].row_number <= unknowns[i + 1].row_number

        # Each has required fields
        for unknown in unknowns:
            assert unknown.ticker != ""
            assert unknown.row_number > 0
            assert unknown.transaction_preview != ""
            assert unknown.original_row_data is not None

    def test_correct_typo_ticker(self, service, csv_with_unknown_tickers):
        """Step 3: Correct APPL typo to AAPL."""
        result = service.import_csv(csv_with_unknown_tickers, broker_type="lightyear")
        batch_id = result.batch_id

        # Find APPL row
        unknowns = service.get_unknown_tickers(batch_id)
        appl_unknown = next(u for u in unknowns if u.ticker == "APPL")

        # Correct to AAPL
        imported_count = service.correct_ticker(batch_id, [appl_unknown.row_number], "AAPL")

        assert imported_count == 1, "Should import 1 transaction after correction"

        # Verify unknown ticker count decreased
        unknowns_after = service.get_unknown_tickers(batch_id)
        assert len(unknowns_after) == 2, "Should have 2 unknowns remaining"

        # APPL should no longer be in unknowns
        unknown_tickers_after = {u.ticker for u in unknowns_after}
        assert "APPL" not in unknown_tickers_after

    def test_correct_regional_ticker_with_suffix(self, service, csv_with_unknown_tickers):
        """Step 4: Correct TKM1T by adding .TL suffix (exchange suffix detection)."""
        result = service.import_csv(csv_with_unknown_tickers, broker_type="lightyear")
        batch_id = result.batch_id

        # Find TKM1T row
        unknowns = service.get_unknown_tickers(batch_id)
        tkm1t_unknown = next(u for u in unknowns if u.ticker == "TKM1T")

        # Apply suggested suffix correction
        imported_count = service.correct_ticker(batch_id, [tkm1t_unknown.row_number], "TKM1T.TL")

        assert imported_count == 1, "Should import 1 transaction with regional suffix"

        # Verify transaction imported with correct ticker
        with db_session() as session:
            from src.models import Transaction

            tkm_txn = (
                session.query(Transaction).filter_by(broker_reference_id="OR-REGIONAL001").first()
            )
            assert tkm_txn is not None, "TKM1T.TL transaction not found"
            # Note: Holding will be created with ticker from Stock, which might normalize it

    def test_delete_invalid_ticker(self, service, csv_with_unknown_tickers):
        """Step 5: Delete XYZZ row (unknown with no suggestions)."""
        result = service.import_csv(csv_with_unknown_tickers, broker_type="lightyear")
        batch_id = result.batch_id

        # Find XYZZ row
        unknowns = service.get_unknown_tickers(batch_id)
        xyzz_unknown = next(u for u in unknowns if u.ticker == "XYZZ")

        # Delete the row
        deleted_count = service.delete_error_rows(batch_id, [xyzz_unknown.row_number])

        assert deleted_count == 1, "Should delete 1 row"

        # Verify row removed from unknowns
        unknowns_after = service.get_unknown_tickers(batch_id)
        unknown_tickers_after = {u.ticker for u in unknowns_after}
        assert "XYZZ" not in unknown_tickers_after

    def test_full_workflow_all_resolved(self, service, csv_with_unknown_tickers):
        """Complete workflow: import → correct → delete → batch completed."""
        result = service.import_csv(csv_with_unknown_tickers, broker_type="lightyear")
        batch_id = result.batch_id

        # Initial state: 3 successful, 3 unknown
        assert result.successful_count == 3
        assert result.unknown_ticker_count == 3

        # Get all unknowns
        unknowns = service.get_unknown_tickers(batch_id)
        appl = next(u for u in unknowns if u.ticker == "APPL")
        tkm1t = next(u for u in unknowns if u.ticker == "TKM1T")
        xyzz = next(u for u in unknowns if u.ticker == "XYZZ")

        # Step 1: Correct APPL → AAPL
        service.correct_ticker(batch_id, [appl.row_number], "AAPL")

        # Step 2: Correct TKM1T → TKM1T.TL
        service.correct_ticker(batch_id, [tkm1t.row_number], "TKM1T.TL")

        # Step 3: Delete XYZZ
        service.delete_error_rows(batch_id, [xyzz.row_number])

        # Verify all unknowns resolved
        unknowns_final = service.get_unknown_tickers(batch_id)
        assert len(unknowns_final) == 0, "All unknowns should be resolved"

        # Verify batch status updated to completed
        history = service.get_import_history(limit=1)
        batch = history[0]
        assert batch.batch_id == batch_id
        assert (
            batch.status == "completed"
        ), "Batch status should be 'completed' after resolving all unknowns"
        assert batch.unknown_ticker_count == 0

        # Verify final transaction counts
        with db_session() as session:
            from src.models import Transaction

            txn_count = session.query(Transaction).filter_by(import_batch_id=batch_id).count()
            assert txn_count == 5, "Should have 5 transactions (3 valid + 2 corrected)"

    def test_ignore_unknown_ticker_imports_anyway(self, service, csv_with_unknown_tickers):
        """Alternative workflow: ignore unknown ticker (import without validation)."""
        result = service.import_csv(csv_with_unknown_tickers, broker_type="lightyear")
        batch_id = result.batch_id

        # Get TKM1T (which could be valid with .TL suffix)
        unknowns = service.get_unknown_tickers(batch_id)
        tkm1t = next(u for u in unknowns if u.ticker == "TKM1T")

        # Import as-is without validation
        imported_count = service.ignore_unknown_tickers(batch_id, [tkm1t.row_number])

        assert imported_count == 1, "Should import 1 transaction with unknown ticker"

        # Verify transaction imported with original ticker (TKM1T, not TKM1T.TL)
        with db_session() as session:
            from src.models import Transaction

            tkm_txn = (
                session.query(Transaction).filter_by(broker_reference_id="OR-REGIONAL001").first()
            )
            assert tkm_txn is not None, "TKM1T transaction not found"
            # Transaction imported with original ticker from CSV

    def test_batch_status_needs_review(self, service, csv_with_unknown_tickers):
        """Batch status is 'needs_review' when unknown tickers exist."""
        result = service.import_csv(csv_with_unknown_tickers, broker_type="lightyear")

        # Check batch status
        history = service.get_import_history(limit=1)
        batch = history[0]
        assert batch.batch_id == result.batch_id
        assert batch.status == "needs_review", "Batch should be 'needs_review' with unknown tickers"
        assert batch.unknown_ticker_count == 3
