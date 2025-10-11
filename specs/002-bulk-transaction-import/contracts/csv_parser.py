"""
CSV Parser Contract

Defines the interface for broker-specific CSV parsers.
This contract specifies expected behavior, not implementation.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Protocol


@dataclass
class ParsedTransaction:
    """
    Unified transaction representation after parsing broker CSV.

    This model is broker-agnostic and used by ImportService.
    Parsers convert broker-specific CSV formats to this common format.
    """

    date: datetime
    ticker: str | None  # NULL for deposits, withdrawals, interest
    quantity: Decimal | None  # NULL for non-trade transactions
    price: Decimal | None  # NULL for non-trade transactions
    fees: Decimal
    transaction_type: str  # Normalized: 'buy', 'sell', 'dividend', 'deposit', 'withdrawal', etc.
    currency: str  # ISO currency code: EUR, USD, GBP
    broker_reference_id: str  # Unique ID from broker CSV
    broker_source: str  # 'swedbank' or 'lightyear'
    net_amount: Decimal  # Net amount after fees/taxes
    tax_amount: Decimal | None  # Tax withheld (NULL if not applicable)
    original_data: dict  # Original CSV row for audit trail


class CSVParser(Protocol):
    """
    Interface for broker-specific CSV parsers.

    Contract Guarantees:
    - Iterator pattern for memory efficiency (yield rows, don't load all)
    - Validates each row with pydantic models
    - Raises CSVParseError with row number on unrecoverable errors
    - Returns ParsedTransaction in normalized format
    - Preserves original CSV row in ParsedTransaction.original_data
    """

    broker_name: str  # 'swedbank' or 'lightyear'

    def parse(self, filepath: Path) -> Iterator[ParsedTransaction]:
        """
        Parse CSV file into validated transaction models.

        Args:
            filepath: Path to CSV file

        Yields:
            ParsedTransaction for each successfully parsed row

        Raises:
            FileNotFoundError: CSV file doesn't exist
            CSVParseError: File format invalid (wrong delimiter, encoding, corrupt data)
            ValidationError: Row data invalid (from pydantic validation)

        Behavior:
        - Reads CSV with broker-specific configuration (delimiter, encoding, decimal separator)
        - Converts dates to datetime with correct format (DD.MM.YYYY for Swedbank, DD/MM/YYYY HH:MM:SS for Lightyear)
        - Normalizes transaction types to common vocabulary
        - Validates each row, raises ValidationError with row number
        - Yields rows one at a time (iterator pattern for large files)
        - Includes original CSV row in ParsedTransaction.original_data

        Performance:
        - Must handle CSV files up to 50,000 rows
        - Memory: O(1) per row (iterator, not list)
        - Parsing: < 3 seconds for 10,000 rows
        """
        ...


class SwedbankCSVParser(CSVParser):
    """
    Parser for Swedbank bank statement CSV format.

    CSV Format:
    - Delimiter: Semicolon (;)
    - Encoding: UTF-8 with Estonian headers
    - Decimal: Comma (e.g., "135,00")
    - Date Format: DD.MM.YYYY

    Key Fields:
    - "Kuupäev": Transaction date
    - "Selgitus": Description (contains transaction details to parse)
    - "Summa": Amount
    - "Valuuta": Currency
    - "Deebet/Kreedit": D (debit) or K (credit)
    - "Arhiveerimistunnus": Archive reference (broker reference ID)

    Transaction Patterns in "Selgitus":
    - Buy: "TICKER +quantity@price/SE:reference EXCHANGE"
    - Sell: "TICKER -quantity@price/SE:reference EXCHANGE"
    - Dividend: "'/reference/ ISIN COMPANY dividend X EUR, tulumaks Y EUR"
    - Fee: "K: TICKER +quantity@price/SE:reference EXCHANGE"
    - Deposit/Withdrawal: "Makse oma kontode vahel"

    Special Handling:
    - Must parse "Selgitus" field with regex to extract ticker, quantity, price
    - Dividend tax ("tulumaks") must be subtracted from gross to get net
    - Fee rows (starts with "K:") must be identified and parsed separately
    - Deebet/Kreedit determines sign (D = outflow, K = inflow)
    """

    broker_name: str = "swedbank"


class LightyearCSVParser(CSVParser):
    """
    Parser for Lightyear broker CSV export format.

    CSV Format:
    - Delimiter: Comma (,)
    - Encoding: UTF-8 with English headers
    - Decimal: Dot (e.g., "135.00")
    - Date Format: DD/MM/YYYY HH:MM:SS

    Key Fields:
    - "Date": Transaction date with timestamp
    - "Reference": Broker reference ID (format: XX-XXXXXXXXXX)
    - "Ticker": Stock ticker symbol (optional for some transaction types)
    - "ISIN": International Securities Identification Number (optional)
    - "Type": Transaction type (Buy, Sell, Dividend, Distribution, Deposit, Withdrawal, Conversion, Interest, Reward)
    - "Quantity": Number of shares (decimal, optional for non-trade)
    - "CCY": Currency code
    - "Price/share": Price per share (optional for non-trade)
    - "Fee": Transaction fee
    - "Net Amt.": Net amount after fees and taxes
    - "Tax Amt.": Tax amount withheld (optional)

    Special Handling:
    - Type field directly maps to transaction_type (normalize to lowercase)
    - Distribution transactions are dividend-like (map to 'dividend')
    - Interest/Reward transactions are income (map to 'interest'/'reward')
    - Empty ticker for Deposit/Withdrawal is valid
    """

    broker_name: str = "lightyear"


# Exception Types


class ValidationError(Exception):
    """Raised when CSV row fails validation."""

    def __init__(self, message: str, row_number: int, field_name: str | None = None):
        self.row_number = row_number
        self.field_name = field_name
        super().__init__(f"Row {row_number}: {message}")


class CSVParseError(Exception):
    """Raised when CSV file cannot be parsed."""

    def __init__(self, message: str, row_number: int | None = None):
        self.row_number = row_number
        super().__init__(message)


# Contract Test Cases


class TestSwedbankParserContract:
    """Contract tests for Swedbank CSV parser."""

    def test_parse_buy_transaction(self, parser: SwedbankCSVParser):
        """
        Given: Swedbank CSV with buy transaction "LHV1T +10@13.5/SE:4100088 TSE"
        When: parse() called
        Then: Yields ParsedTransaction with:
            - transaction_type = 'buy'
            - ticker = 'LHV1T'
            - quantity = 10
            - price = 13.5
            - broker_reference_id = '2020100600247429'
        """
        pass

    def test_parse_sell_transaction(self, parser: SwedbankCSVParser):
        """
        Given: Swedbank CSV with sell transaction "CPA1T -60@1.804/SE:2173825 TSE"
        When: parse() called
        Then: Yields ParsedTransaction with:
            - transaction_type = 'sell'
            - ticker = 'CPA1T'
            - quantity = 60 (positive)
            - price = 1.804
        """
        pass

    def test_parse_dividend(self, parser: SwedbankCSVParser):
        """
        Given: Swedbank CSV with dividend "'/212759/ EE0000001105 TALLINNA KAUBAMAJA GRUPP AKTSIA dividend 5.53 EUR, tulumaks 0.00 EUR"
        When: parse() called
        Then: Yields ParsedTransaction with:
            - transaction_type = 'dividend'
            - ticker = 'TKM1T' (extracted from ISIN or company name)
            - net_amount = 5.53
            - tax_amount = 0.00
        """
        pass

    def test_parse_full_csv(self, parser: SwedbankCSVParser, sample_csv_path: Path):
        """
        Given: research/swed_2020_2021.csv (real sample file)
        When: parse() called
        Then: Yields N transactions without errors
        And: All required fields populated
        And: No ValidationError raised
        """
        pass

    def test_invalid_delimiter(self, parser: SwedbankCSVParser):
        """
        Given: CSV with comma delimiter (should be semicolon)
        When: parse() called
        Then: CSVParseError raised with message about delimiter
        """
        pass


class TestLightyearParserContract:
    """Contract tests for Lightyear CSV parser."""

    def test_parse_buy_transaction(self, parser: LightyearCSVParser):
        """
        Given: Lightyear CSV with Buy transaction
        When: parse() called
        Then: Yields ParsedTransaction with:
            - transaction_type = 'buy'
            - ticker from "Ticker" column
            - quantity from "Quantity" column
            - price from "Price/share" column
            - broker_reference_id from "Reference" column
        """
        pass

    def test_parse_dividend(self, parser: LightyearCSVParser):
        """
        Given: Lightyear CSV with Dividend transaction
        When: parse() called
        Then: Yields ParsedTransaction with:
            - transaction_type = 'dividend'
            - ticker from "Ticker" column
            - net_amount from "Net Amt." column
            - tax_amount from "Tax Amt." column
        """
        pass

    def test_parse_deposit(self, parser: LightyearCSVParser):
        """
        Given: Lightyear CSV with Deposit transaction (no ticker)
        When: parse() called
        Then: Yields ParsedTransaction with:
            - transaction_type = 'deposit'
            - ticker = None
            - quantity = None
            - net_amount = deposit amount
        """
        pass

    def test_parse_full_csv(self, parser: LightyearCSVParser, sample_csv_path: Path):
        """
        Given: research/lightyear_2022_2025.csv (real sample file)
        When: parse() called
        Then: Yields N transactions without errors
        And: All transaction types handled (Buy, Sell, Dividend, Distribution, etc.)
        """
        pass

    def test_invalid_transaction_type(self, parser: LightyearCSVParser):
        """
        Given: CSV with invalid Type value "InvalidType"
        When: parse() called
        Then: ValidationError raised with row number and message
        """
        pass
