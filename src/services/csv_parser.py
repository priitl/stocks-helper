"""CSV parsers for broker-specific transaction imports.

Implements parsers for Swedbank and Lightyear broker CSV formats.
"""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

import pandas as pd
from pydantic import ValidationError as PydanticValidationError

from src.lib.broker_mappings import LIGHTYEAR_TYPE_MAPPING, SWEDBANK_TYPE_MAPPING
from src.lib.csv_models import LightyearCSVRow, ParsedTransaction, SwedbankCSVRow
from src.models.transaction import TransactionType


class CSVParseError(Exception):
    """Raised when CSV file cannot be parsed."""

    def __init__(self, message: str, row_number: int | None = None):
        self.row_number = row_number
        super().__init__(message)


class ValidationError(Exception):
    """Raised when CSV row fails validation."""

    def __init__(self, message: str, row_number: int, field_name: str | None = None):
        self.row_number = row_number
        self.field_name = field_name
        super().__init__(f"Row {row_number}: {message}")


class SwedbankCSVParser:
    """Parser for Swedbank bank statement CSV format.

    Handles Estonian CSV format with semicolon delimiters.
    Uses Tehingu tüüp + Deebet/Kreedit for transaction type mapping.
    Uses regex pattern matching ONLY to extract transaction details (ticker, price, etc.).
    """

    broker_name: str = "swedbank"

    # Regex patterns for extracting details from "Selgitus" field
    # Pattern 1: Stock BUY/SELL - make /SE: reference optional
    BUY_SELL_PATTERN = re.compile(
        r"(?P<ticker>[A-Z0-9\-]+)\s+"
        r"(?P<sign>[+-])(?P<quantity>[\d.]+)"
        r"@(?P<price>[\d.]+)"
        r"(?:PCT)?(?:/SE:(?P<reference>\S+))?\s+"
        r"(?P<exchange>\w+)"
    )

    # Pattern 2: Dividend with tax
    DIVIDEND_PATTERN = re.compile(
        r"'/(?P<reference>\d+)/ "
        r"(?P<isin>[A-Z]{2}\d+) "
        r"(?P<company>.+?) dividend "
        r"(?P<gross>[\d.]+) EUR, tulumaks (?P<tax>[\d.]+) EUR"
    )

    # Pattern 3: Bond interest payment
    BOND_INTEREST_PATTERN = re.compile(
        r"'/(?P<reference>\d+)/ "
        r"(?P<isin>[A-Z]{2}\d+) "
        r"(?P<bond_name>.+?) "
        r"(?P<coupon>[\d.]+)% .+ "
        r"intressimakse "
        r"(?P<amount>[\d.]+) EUR"
    )

    # Pattern 4: Deposit interest
    DEPOSIT_INTEREST_PATTERN = re.compile(
        r"Deposiidi netointress kontolt .+ Intressisummalt (?P<amount>[\d.]+) EUR"
    )

    # Pattern 5: Currency conversion
    CONVERSION_PATTERN = re.compile(
        r"VV: (?:(?P<from_ccy>[A-Z]{3}) )?(?P<from_amt>[\d,]+)\.(?P<from_dec>\d+) -> "
        r"(?P<to_ccy>[A-Z]{3})(?: kurss (?P<rate>[\d.]+))?"
    )

    # Pattern 6: Custody fees
    CUSTODY_FEE_PATTERN = re.compile(r"Vp\.konto \d+ hooldustasud")

    # Fee prefixes
    FEE_PREFIXES = ["K: ", "T: "]

    def parse_file(self, filepath: Path) -> "ParseResult":
        """Parse Swedbank CSV file and return results."""
        transactions = []
        errors = []
        total_rows = 0

        try:
            # Read CSV with Swedbank-specific settings
            df = pd.read_csv(
                filepath,
                delimiter=";",
                encoding="utf-8",
                decimal=",",
                dtype=str,
                na_filter=False,
            )

            # Validate required columns
            required_cols = [
                "Kliendi konto",
                "Kuupäev",
                "Selgitus",
                "Summa",
                "Valuuta",
                "Deebet/Kreedit",
                "Tehingu tüüp",
            ]
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                raise CSVParseError(
                    f"Invalid Swedbank CSV format. Missing columns: {', '.join(missing_cols)}. "
                    "Expected semicolon-delimited CSV with Estonian headers."
                )

            for idx, row in df.iterrows():
                total_rows += 1
                try:
                    txn = self._parse_row(row, idx + 2)  # +2 for header and 1-indexing
                    if txn:
                        transactions.append(txn)
                except (ValidationError, ValueError, InvalidOperation) as e:
                    errors.append({"row": idx + 2, "error": str(e)})

        except Exception as e:
            raise CSVParseError(f"Failed to parse Swedbank CSV: {e}")

        return ParseResult(transactions=transactions, errors=errors, total_rows=total_rows)

    def parse(self, filepath: Path) -> Iterator[ParsedTransaction]:
        """Parse CSV file into validated transaction models (iterator)."""
        result = self.parse_file(filepath)
        for txn in result.transactions:
            yield txn

    def _parse_row(self, row: pd.Series, row_number: int) -> ParsedTransaction | None:
        """Parse a single Swedbank CSV row into ParsedTransaction."""
        try:
            csv_row = SwedbankCSVRow(**row.to_dict())
        except PydanticValidationError as e:
            raise ValidationError(f"Invalid row data: {e}", row_number)

        # Skip empty rows
        if not csv_row.selgitus or csv_row.selgitus.strip() == "":
            return None

        # Skip opening/closing balances and summaries
        skip_keywords = ["Algsaldo", "lõppsaldo", "Käive"]
        if any(kw in csv_row.selgitus for kw in skip_keywords):
            return None

        description = csv_row.selgitus
        original_data = row.to_dict()

        # Parse common fields
        date = datetime.strptime(csv_row.kuupaev, "%d.%m.%Y")
        amount = abs(Decimal(csv_row.summa))  # Always positive
        currency = csv_row.valuuta
        debit_credit = csv_row.deebet_kreedit
        reference_id = csv_row.arhiveerimistunnus or f"swed-{row_number}"

        # Get base transaction type from mapping
        type_key = (csv_row.tehingu_tyup, debit_credit)
        base_type = SWEDBANK_TYPE_MAPPING.get(type_key)

        # For "M" type, determine specific type from description patterns
        # (M types map to None, meaning "parse from description")
        if csv_row.tehingu_tyup == "M":
            return self._parse_m_type_transaction(
                description,
                date,
                amount,
                currency,
                debit_credit,
                reference_id,
                original_data,
            )

        # Skip if explicitly mapped to None (opening balance, closing balance, etc.)
        if base_type is None:
            return None

        # Handle mapped types
        if base_type:
            # Check for special patterns that override the base type
            if base_type == TransactionType.TAX:  # KM - VAT
                return self._create_transaction(
                    transaction_type="TAX",
                    date=date,
                    amount=amount,
                    currency=currency,
                    debit_credit=debit_credit,
                    reference_id=reference_id,
                    description=description,
                    original_data=original_data,
                )

            # Interest from type I
            if base_type.value == "INTEREST":
                # Check if it's deposit interest
                match = self.DEPOSIT_INTEREST_PATTERN.search(description)
                if match:
                    interest_amt = Decimal(match.group("amount"))
                    return self._create_transaction(
                        transaction_type="INTEREST",
                        date=date,
                        amount=interest_amt,
                        currency=currency,
                        debit_credit=debit_credit,
                        reference_id=reference_id,
                        description=description,
                        original_data=original_data,
                    )

            # Currency conversion from type X
            if base_type.value == "CONVERSION":
                return self._parse_conversion(
                    description,
                    date,
                    amount,
                    currency,
                    debit_credit,
                    reference_id,
                    original_data,
                )

            # Default: use the mapped type
            return self._create_transaction(
                transaction_type=base_type.value,
                date=date,
                amount=amount,
                currency=currency,
                debit_credit=debit_credit,
                reference_id=reference_id,
                description=description,
                original_data=original_data,
            )

        # Unknown type - still import as generic transaction
        return self._create_transaction(
            transaction_type="ADJUSTMENT",
            date=date,
            amount=amount,
            currency=currency,
            debit_credit=debit_credit,
            reference_id=reference_id,
            description=description,
            original_data=original_data,
        )

    def _parse_m_type_transaction(
        self,
        description: str,
        date: datetime,
        amount: Decimal,
        currency: str,
        debit_credit: str,
        reference_id: str,
        original_data: dict[str, str],
    ) -> ParsedTransaction | None:
        """Parse M-type transaction (stock trades, dividends, fees)."""
        # Check for fee prefix (K: or T:)
        for prefix in self.FEE_PREFIXES:
            if description.startswith(prefix):
                # Extract ticker if present in fee description
                fee_desc = description[len(prefix) :]
                match = self.BUY_SELL_PATTERN.search(fee_desc)
                ticker = match.group("ticker") if match else None

                return self._create_transaction(
                    transaction_type="FEE",
                    date=date,
                    amount=amount,
                    currency=currency,
                    debit_credit=debit_credit,
                    reference_id=reference_id,
                    ticker=ticker,
                    description=description,
                    original_data=original_data,
                )

        # Check for buy/sell pattern
        match = self.BUY_SELL_PATTERN.search(description)
        if match:
            ticker = match.group("ticker")
            sign = match.group("sign")
            quantity = Decimal(match.group("quantity"))
            price_str = match.group("price")
            exchange = match.group("exchange")

            price = Decimal(price_str)

            # Determine BUY vs SELL from sign
            transaction_type = "SELL" if sign == "-" else "BUY"

            return self._create_transaction(
                transaction_type=transaction_type,
                date=date,
                amount=amount,
                currency=currency,
                debit_credit=debit_credit,
                reference_id=reference_id,
                ticker=ticker,
                quantity=quantity,
                price=price,
                exchange=exchange,
                description=description,
                original_data=original_data,
            )

        # Check for dividend
        match = self.DIVIDEND_PATTERN.search(description)
        if match:
            isin = match.group("isin")
            company = match.group("company")
            gross = Decimal(match.group("gross"))
            tax = Decimal(match.group("tax"))
            net = gross - tax

            return self._create_transaction(
                transaction_type="DIVIDEND",
                date=date,
                amount=net,
                currency=currency,
                debit_credit=debit_credit,
                reference_id=reference_id,
                isin=isin,
                company_name=company,
                gross_amount=gross,
                tax_amount=tax,
                description=description,
                original_data=original_data,
            )

        # Check for bond interest
        match = self.BOND_INTEREST_PATTERN.search(description)
        if match:
            isin = match.group("isin")
            bond_name = match.group("bond_name")
            interest_amt = Decimal(match.group("amount"))

            return self._create_transaction(
                transaction_type="INTEREST",
                date=date,
                amount=interest_amt,
                currency=currency,
                debit_credit=debit_credit,
                reference_id=reference_id,
                isin=isin,
                company_name=bond_name,
                description=description,
                original_data=original_data,
            )

        # Check for custody fee
        if self.CUSTODY_FEE_PATTERN.search(description):
            return self._create_transaction(
                transaction_type="FEE",
                date=date,
                amount=amount,
                currency=currency,
                debit_credit=debit_credit,
                reference_id=reference_id,
                description=description,
                original_data=original_data,
            )

        # Unknown M-type - import as adjustment
        return self._create_transaction(
            transaction_type="ADJUSTMENT",
            date=date,
            amount=amount,
            currency=currency,
            debit_credit=debit_credit,
            reference_id=reference_id,
            description=description,
            original_data=original_data,
        )

    def _parse_conversion(
        self,
        description: str,
        date: datetime,
        amount: Decimal,
        currency: str,
        debit_credit: str,
        reference_id: str,
        original_data: dict[str, str],
    ) -> ParsedTransaction:
        """Parse currency conversion transaction."""
        match = self.CONVERSION_PATTERN.search(description)
        if match:
            from_amt_int = match.group("from_amt").replace(",", "")
            from_amt_dec = match.group("from_dec")
            from_amt = Decimal(f"{from_amt_int}.{from_amt_dec}")
            to_ccy = match.group("to_ccy")
            from_ccy = match.group("from_ccy") or currency

            # For conversion, store both sides
            if debit_credit == "D":
                # Debit from source currency
                return self._create_transaction(
                    transaction_type="CONVERSION",
                    date=date,
                    amount=from_amt,
                    currency=from_ccy,
                    debit_credit=debit_credit,
                    reference_id=reference_id,
                    conversion_from_amount=from_amt,
                    conversion_from_currency=from_ccy,
                    description=description,
                    original_data=original_data,
                )
            else:
                # Credit to target currency
                return self._create_transaction(
                    transaction_type="CONVERSION",
                    date=date,
                    amount=amount,
                    currency=to_ccy,
                    debit_credit=debit_credit,
                    reference_id=reference_id,
                    conversion_from_amount=from_amt,
                    conversion_from_currency=from_ccy,
                    description=description,
                    original_data=original_data,
                )

        # Fallback: generic conversion
        return self._create_transaction(
            transaction_type="CONVERSION",
            date=date,
            amount=amount,
            currency=currency,
            debit_credit=debit_credit,
            reference_id=reference_id,
            description=description,
            original_data=original_data,
        )

    def _create_transaction(
        self,
        transaction_type: str,
        date: datetime,
        amount: Decimal,
        currency: str,
        debit_credit: str,
        reference_id: str,
        original_data: dict[str, str],
        ticker: str | None = None,
        isin: str | None = None,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        exchange: str | None = None,
        description: str | None = None,
        company_name: str | None = None,
        gross_amount: Decimal | None = None,
        tax_amount: Decimal | None = None,
        conversion_from_amount: Decimal | None = None,
        conversion_from_currency: str | None = None,
    ) -> ParsedTransaction:
        """Helper to create ParsedTransaction."""
        # For FEE transactions, amount goes into fees field
        if transaction_type == "FEE":
            fees = amount
            net_amount = Decimal("0.00")
        else:
            fees = Decimal("0.00")
            net_amount = amount

        return ParsedTransaction(
            date=date,
            transaction_type=transaction_type,
            amount=amount,
            currency=currency,
            debit_credit=debit_credit,
            ticker=ticker,
            isin=isin,
            quantity=quantity,
            price=price,
            conversion_from_amount=conversion_from_amount,
            conversion_from_currency=conversion_from_currency,
            fees=fees,
            tax_amount=tax_amount,
            net_amount=net_amount,
            gross_amount=gross_amount,
            broker_reference_id=reference_id,
            broker_source=self.broker_name,
            original_data=original_data,
            company_name=company_name,
            exchange=exchange,
            description=description,
        )


class LightyearCSVParser:
    """Parser for Lightyear broker CSV export format.

    Handles English CSV format with comma delimiters and direct column mapping.
    Uses Type column directly from CSV.
    """

    broker_name: str = "lightyear"

    def parse_file(self, filepath: Path) -> "ParseResult":
        """Parse Lightyear CSV file and return results."""
        transactions = []
        errors = []
        total_rows = 0

        try:
            df = pd.read_csv(
                filepath,
                delimiter=",",
                encoding="utf-8",
                decimal=".",
                dtype=str,
                na_filter=False,
            )

            # Validate required columns
            required_cols = ["Date", "Reference", "Type", "CCY", "Net Amt."]
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                raise CSVParseError(
                    f"Invalid Lightyear CSV format. Missing columns: {', '.join(missing_cols)}. "
                    "Expected comma-delimited CSV with English headers."
                )

            for idx, row in df.iterrows():
                total_rows += 1
                try:
                    txn = self._parse_row(row, idx + 2)
                    if txn:
                        transactions.append(txn)
                except (ValidationError, ValueError, InvalidOperation) as e:
                    errors.append({"row": idx + 2, "error": str(e)})

        except Exception as e:
            raise CSVParseError(f"Failed to parse Lightyear CSV: {e}")

        return ParseResult(transactions=transactions, errors=errors, total_rows=total_rows)

    def parse(self, filepath: Path) -> Iterator[ParsedTransaction]:
        """Parse CSV file into validated transaction models (iterator)."""
        result = self.parse_file(filepath)
        for txn in result.transactions:
            yield txn

    def _parse_row(self, row: pd.Series, row_number: int) -> ParsedTransaction:
        """Parse a single Lightyear CSV row into ParsedTransaction."""
        try:
            csv_row = LightyearCSVRow(**row.to_dict())
        except PydanticValidationError as e:
            raise ValidationError(f"Invalid row data: {e}", row_number)

        # Parse date with timestamp
        date = datetime.strptime(csv_row.date, "%d/%m/%Y %H:%M:%S")

        # Get transaction type from mapping
        transaction_type = LIGHTYEAR_TYPE_MAPPING.get(csv_row.type, "ADJUSTMENT")

        # Parse amounts
        quantity = (
            Decimal(csv_row.quantity) if csv_row.quantity and csv_row.quantity != "0" else None
        )
        price = (
            Decimal(csv_row.price_per_share)
            if csv_row.price_per_share and csv_row.price_per_share != "0"
            else None
        )
        fee = Decimal(csv_row.fee) if csv_row.fee else Decimal("0")
        net_amt = Decimal(csv_row.net_amt) if csv_row.net_amt else Decimal("0")
        tax_amt = Decimal(csv_row.tax_amt) if csv_row.tax_amt and csv_row.tax_amt != "0" else None
        gross_amt = (
            Decimal(csv_row.gross_amount)
            if csv_row.gross_amount and csv_row.gross_amount != "0"
            else None
        )

        # Determine debit/credit from net amount
        debit_credit = "D" if net_amt < 0 else "K"
        amount = abs(net_amt)

        # Get ticker (may be empty for non-stock transactions)
        ticker = csv_row.ticker if csv_row.ticker and csv_row.ticker.strip() else None
        isin = csv_row.isin if csv_row.isin and csv_row.isin.strip() else None

        return ParsedTransaction(
            date=date,
            transaction_type=transaction_type,
            amount=amount,
            currency=csv_row.ccy,
            debit_credit=debit_credit,
            ticker=ticker,
            isin=isin,
            quantity=quantity,
            price=price,
            fees=fee,
            tax_amount=tax_amt,
            net_amount=amount,
            gross_amount=gross_amt,
            broker_reference_id=csv_row.reference,
            broker_source=self.broker_name,
            original_data=row.to_dict(),
        )


class ParseResult:
    """Result of parsing a CSV file."""

    def __init__(
        self,
        transactions: list[ParsedTransaction],
        errors: list[dict[str, str | int]],
        total_rows: int,
    ):
        self.transactions = transactions
        self.errors = errors
        self.total_rows = total_rows
