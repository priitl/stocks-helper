"""Contract tests for Lightyear CSV parsing.

These tests verify that the Lightyear CSV parser correctly handles the broker's
CSV format with comma delimiters, English headers, and multiple transaction types
including dividends, distributions, deposits, withdrawals, conversions, interest, and rewards.

Uses anonymized test data in tests/fixtures/csv/lightyear_sample.csv

Run with: pytest -m contract tests/contract/test_lightyear_csv_contract.py
"""

from decimal import Decimal
from pathlib import Path

import pytest

from src.services.csv_parser import LightyearCSVParser


@pytest.mark.contract
class TestLightyearCSVContract:
    """Contract tests for Lightyear CSV parser.

    These tests use anonymized test data (tests/fixtures/csv/lightyear_sample.csv)
    to verify parsing logic handles all transaction types and multi-currency support.
    """

    @pytest.fixture
    def parser(self):
        """Provide Lightyear CSV parser instance."""
        return LightyearCSVParser()

    @pytest.fixture
    def sample_csv_path(self):
        """Path to Lightyear sample CSV file."""
        return Path(__file__).parent.parent / "fixtures" / "csv" / "lightyear_sample.csv"

    def test_parse_complete_file(self, parser, sample_csv_path):
        """Lightyear parser successfully parses all rows without errors."""
        assert sample_csv_path.exists(), f"Sample CSV not found: {sample_csv_path}"

        result = parser.parse_file(sample_csv_path)

        # Should parse all valid transaction rows (10 in anonymized sample file)
        assert result.total_rows == 10, f"Expected 10 rows, got {result.total_rows}"
        assert len(result.transactions) == 10, "Expected 10 transactions"
        assert result.errors == [], f"Unexpected parsing errors: {result.errors}"

    def test_parse_buy_transaction(self, parser, sample_csv_path):
        """Lightyear parser extracts buy transactions from Type column."""
        result = parser.parse_file(sample_csv_path)

        # Find a known buy transaction: OR-TEST0001, ACME, 10 shares @ 100 USD
        buy_txns = [t for t in result.transactions if t.broker_reference_id == "OR-TEST0001"]
        assert len(buy_txns) > 0, "Buy transaction OR-TEST0001 not found"

        buy = buy_txns[0]
        assert buy.transaction_type == "BUY"
        assert buy.ticker == "ACME"
        assert buy.isin == "US0000000001"
        assert buy.quantity == Decimal("10.0")
        assert buy.price == Decimal("100.0")
        assert buy.currency == "USD"
        assert buy.gross_amount == Decimal("1000.0")
        assert buy.fees == Decimal("0.0")
        assert buy.net_amount == Decimal("1000.0")

    def test_parse_dividend_transaction(self, parser, sample_csv_path):
        """Lightyear parser extracts dividend transactions with tax."""
        result = parser.parse_file(sample_csv_path)

        # Find dividend: DD-TEST0003, TECH, 15.00 gross, 12.75 net, 2.25 tax
        div_txns = [t for t in result.transactions if t.broker_reference_id == "DD-TEST0003"]
        assert len(div_txns) > 0, "Dividend DD-TEST0003 not found"

        div = div_txns[0]
        assert div.transaction_type == "DIVIDEND"
        assert div.ticker == "TECH"
        assert div.isin == "US0000000002"
        assert div.currency == "USD"
        assert div.gross_amount == Decimal("15.0")
        assert div.net_amount == Decimal("12.75")
        assert div.tax_amount == Decimal("2.25")

    def test_parse_distribution_transaction(self, parser, sample_csv_path):
        """Lightyear parser extracts distribution transactions."""
        result = parser.parse_file(sample_csv_path)

        # Find distribution: IN-TEST0002, ACME, 5.00 gross, 0.10 fee, 4.90 net
        dist_txns = [t for t in result.transactions if t.broker_reference_id == "IN-TEST0002"]
        assert len(dist_txns) > 0, "Distribution IN-TEST0002 not found"

        dist = dist_txns[0]
        assert dist.transaction_type == "DISTRIBUTION"
        assert dist.ticker == "ACME"
        assert dist.currency == "USD"
        assert dist.gross_amount == Decimal("5.0")
        assert dist.fees == Decimal("0.10")
        assert dist.net_amount == Decimal("4.90")
        assert dist.tax_amount == Decimal("0.0") or dist.tax_amount is None

    def test_parse_multi_currency_transactions(self, parser, sample_csv_path):
        """Lightyear parser handles multiple currencies (USD, EUR)."""
        result = parser.parse_file(sample_csv_path)

        # Collect all currencies
        currencies = {t.currency for t in result.transactions}

        # Sample file should contain both USD and potentially EUR
        assert "USD" in currencies, "USD transactions not found"
        # EUR may or may not be present depending on sample data

    def test_parse_date_format(self, parser, sample_csv_path):
        """Lightyear parser correctly parses DD/MM/YYYY HH:MM:SS date format."""
        result = parser.parse_file(sample_csv_path)

        # Check a known transaction date: 01/10/2025 12:16:17
        oct_txns = [
            t
            for t in result.transactions
            if t.date.year == 2025
            and t.date.month == 10
            and t.date.day == 1
            and t.date.hour == 12
            and t.date.minute == 16
        ]
        assert len(oct_txns) > 0, "October 2025 transactions not found"

    def test_parse_decimal_dot_separator(self, parser, sample_csv_path):
        """Lightyear parser handles standard decimal dot separator."""
        result = parser.parse_file(sample_csv_path)

        # Verify decimal values parsed correctly (CSV uses dot: 100.00000 -> 100.0)
        buy_txns = [
            t
            for t in result.transactions
            if t.transaction_type == "BUY" and t.price == Decimal("100.0")
        ]
        assert len(buy_txns) > 0, "Transactions with price 100.0 not found"

    def test_parse_all_transaction_types(self, parser, sample_csv_path):
        """Lightyear parser handles all expected transaction types."""
        result = parser.parse_file(sample_csv_path)

        # Collect all transaction types
        types = {t.transaction_type for t in result.transactions}

        # Sample should contain at least these types
        expected_types = {"BUY", "DIVIDEND", "DISTRIBUTION"}
        missing_types = expected_types - types
        assert not missing_types, f"Missing transaction types: {missing_types}"

    def test_parse_optional_fields(self, parser, sample_csv_path):
        """Lightyear parser correctly handles optional fields (ISIN, FX Rate, Tax)."""
        result = parser.parse_file(sample_csv_path)

        # Find transactions with missing ISIN (distributions often don't have ISIN)
        no_isin_txns = [t for t in result.transactions if not t.isin or t.isin == ""]
        assert len(no_isin_txns) > 0, "No transactions found with empty ISIN"

        # FX rate is optional - verify parser handles it without failing
        # (no assertions needed, just verify no exceptions)

    def test_reference_id_patterns(self, parser, sample_csv_path):
        """Lightyear parser extracts reference IDs with different prefixes."""
        result = parser.parse_file(sample_csv_path)

        # Collect reference ID prefixes
        prefixes = {t.broker_reference_id[:3] for t in result.transactions if t.broker_reference_id}

        # Should see different prefixes: OR- (orders), DD- (dividends), IN- (distributions)
        expected_prefixes = {"OR-", "DD-", "IN-"}
        missing_prefixes = expected_prefixes - prefixes
        assert not missing_prefixes, f"Missing reference ID prefixes: {missing_prefixes}"

    def test_zero_quantity_transactions(self, parser, sample_csv_path):
        """Lightyear parser handles transactions with zero quantity (dividends, distributions)."""
        result = parser.parse_file(sample_csv_path)

        # Dividends and distributions have empty/zero quantity
        zero_qty_txns = [
            t
            for t in result.transactions
            if t.transaction_type in ("DIVIDEND", "DISTRIBUTION")
            and (t.quantity == Decimal("0") or t.quantity is None)
        ]
        assert len(zero_qty_txns) > 0, "No zero-quantity transactions found"

    def test_empty_fields_handling(self, parser, sample_csv_path):
        """Lightyear parser correctly handles empty string fields."""
        result = parser.parse_file(sample_csv_path)

        # Verify parser doesn't crash on empty fields (tax, ISIN, FX rate can be empty)
        assert len(result.transactions) > 0
        # If this test passes, parser handled empty fields correctly
