"""Contract tests for Swedbank CSV parsing.

These tests verify that the Swedbank CSV parser correctly handles the broker's
CSV format with semicolon delimiters, Estonian locale, and embedded transaction
details in the description field.

Uses anonymized test data in tests/fixtures/csv/swedbank_sample.csv

Run with: pytest -m contract tests/contract/test_swedbank_csv_contract.py
"""

from decimal import Decimal
from pathlib import Path

import pytest

from src.services.csv_parser import SwedbankCSVParser


@pytest.mark.contract
class TestSwedbankCSVContract:
    """Contract tests for Swedbank CSV parser.

    These tests use anonymized test data (tests/fixtures/csv/swedbank_sample.csv)
    to verify parsing logic handles all transaction types.
    """

    @pytest.fixture
    def parser(self):
        """Provide Swedbank CSV parser instance."""
        return SwedbankCSVParser()

    @pytest.fixture
    def sample_csv_path(self):
        """Path to Swedbank sample CSV file."""
        return Path(__file__).parent.parent / "fixtures" / "csv" / "swedbank_sample.csv"

    def test_parse_complete_file(self, parser, sample_csv_path):
        """Swedbank parser successfully parses all rows without errors."""
        assert sample_csv_path.exists(), f"Sample CSV not found: {sample_csv_path}"

        result = parser.parse_file(sample_csv_path)

        # Should parse all valid transaction rows (skip header and opening balance)
        assert result.total_rows > 0, "No rows parsed"
        assert len(result.transactions) > 0, "No transactions extracted"
        assert result.errors == [], f"Unexpected parsing errors: {result.errors}"

    def test_parse_buy_transaction(self, parser, sample_csv_path):
        """Swedbank parser extracts buy transactions from description field."""
        result = parser.parse_file(sample_csv_path)

        # Find a known buy transaction: ACME1T +10@13.50/SE:4100001 TSE
        buy_txns = [t for t in result.transactions if t.ticker == "ACME1T" and t.quantity == 10]
        assert len(buy_txns) > 0, "Buy transaction ACME1T not found"

        buy = buy_txns[0]
        assert buy.transaction_type == "BUY"
        assert buy.ticker == "ACME1T"
        assert buy.quantity == 10.0
        assert buy.price == 13.5
        # broker_reference_id comes from Arhiveerimistunnus field
        assert buy.broker_reference_id == "2020100600000001"
        assert buy.exchange == "TSE"  # Tallinn Stock Exchange
        assert buy.currency == "EUR"

    def test_parse_sell_transaction(self, parser, sample_csv_path):
        """Swedbank parser extracts sell transactions with negative quantity."""
        result = parser.parse_file(sample_csv_path)

        # Find a known sell transaction: RETAIL1L -60@1.804/SE:2100001 TSE
        sell_txns = [
            t
            for t in result.transactions
            if t.ticker == "RETAIL1L" and t.transaction_type == "SELL"
        ]
        assert len(sell_txns) > 0, "Sell transaction RETAIL1L not found"

        sell = sell_txns[0]
        assert sell.transaction_type == "SELL"
        assert sell.ticker == "RETAIL1L"
        assert sell.quantity == Decimal("60")  # Absolute value for SELL type
        assert sell.price == Decimal("1.804")
        # broker_reference_id comes from Arhiveerimistunnus field
        assert sell.broker_reference_id == "2020122000000001"

    def test_parse_dividend_transaction(self, parser, sample_csv_path):
        """Swedbank parser extracts dividend transactions from description."""
        result = parser.parse_file(sample_csv_path)

        # Find dividend transaction:
        # '/333333/ EE0000001111 ACME CORPORATION dividend 5.53 EUR, tulumaks 0.00 EUR'
        dividend_txns = [
            t
            for t in result.transactions
            if t.transaction_type == "DIVIDEND"
            and (
                t.isin == "EE0000001111"
                or (t.gross_amount and abs(t.gross_amount - Decimal("5.53")) < Decimal("0.01"))
            )
        ]
        assert len(dividend_txns) > 0, "Dividend transaction not found"

        div = dividend_txns[0]
        assert div.transaction_type == "DIVIDEND"
        assert div.isin == "EE0000001111"
        assert div.company_name == "ACME CORPORATION"
        assert div.gross_amount == Decimal("5.53")
        assert div.tax_amount == Decimal("0.00")
        assert div.currency == "EUR"

    def test_parse_dividend_with_tax(self, parser, sample_csv_path):
        """Swedbank parser correctly extracts dividend with withholding tax."""
        result = parser.parse_file(sample_csv_path)

        # Find dividend with tax:
        # '/555555/ EE0000002222 TECH CORPORATION dividend 12.50 EUR, tulumaks 2.50 EUR'
        dividend_txns = [
            t
            for t in result.transactions
            if t.transaction_type == "DIVIDEND"
            and t.gross_amount
            and abs(t.gross_amount - Decimal("12.50")) < Decimal("0.01")
        ]
        assert len(dividend_txns) > 0, "Dividend with tax not found"

        div = dividend_txns[0]
        assert abs(div.gross_amount - Decimal("12.50")) < Decimal("0.01")
        assert abs(div.tax_amount - Decimal("2.50")) < Decimal("0.01")
        assert abs(div.net_amount - Decimal("10.00")) < Decimal("0.01")  # 12.50 - 2.50

    def test_parse_fee_transaction(self, parser, sample_csv_path):
        """Swedbank parser identifies fee transactions from 'K:' prefix."""
        result = parser.parse_file(sample_csv_path)

        # Find fee transaction: K: Kauplemistasu (trading fee)
        fee_txns = [
            t
            for t in result.transactions
            if t.transaction_type == "FEE" and t.description and "Kauplemistasu" in t.description
        ]
        assert len(fee_txns) > 0, "Fee transaction not found"

        fee = fee_txns[0]
        assert fee.transaction_type == "FEE"
        assert fee.fees > 0  # Fees field contains the fee amount
        assert fee.currency == "EUR"

    def test_parse_date_format(self, parser, sample_csv_path):
        """Swedbank parser correctly parses DD.MM.YYYY date format."""
        result = parser.parse_file(sample_csv_path)

        # Check a known transaction date: 05.10.2020 (ACME1T buy)
        oct_txns = [
            t
            for t in result.transactions
            if t.date.year == 2020 and t.date.month == 10 and t.date.day == 5
        ]
        assert len(oct_txns) > 0, "October 5, 2020 transaction not found"

    def test_parse_decimal_comma_separator(self, parser, sample_csv_path):
        """Swedbank parser handles European decimal comma separator."""
        result = parser.parse_file(sample_csv_path)

        # Verify decimal values parsed correctly (CSV uses comma: 13,50 -> 13.5)
        acme_txns = [t for t in result.transactions if t.ticker == "ACME1T"]
        assert len(acme_txns) > 0

        acme = acme_txns[0]
        assert acme.price == 13.5  # Parsed from "13,50"

    def test_parse_multi_currency_support(self, parser, sample_csv_path):
        """Swedbank parser handles EUR currency from Valuuta column."""
        result = parser.parse_file(sample_csv_path)

        # All transactions in this CSV should be EUR
        currencies = {t.currency for t in result.transactions}
        assert "EUR" in currencies
        # Swedbank sample only has EUR, but parser should support others

    def test_skip_non_transaction_rows(self, parser, sample_csv_path):
        """Swedbank parser skips header and opening balance rows."""
        result = parser.parse_file(sample_csv_path)

        # Should not include "Algsaldo" (opening balance) as transaction
        opening_balance_txns = [
            t for t in result.transactions if t.description and "Algsaldo" in t.description
        ]
        assert len(opening_balance_txns) == 0, "Opening balance incorrectly parsed as transaction"
