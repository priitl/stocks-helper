"""Pydantic models for CSV row validation.

These models validate broker-specific CSV row data before parsing into
the unified ParsedTransaction format.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class SwedbankCSVRow(BaseModel):
    """Swedbank bank statement CSV row model.

    Fields match Estonian CSV headers from Swedbank export.
    """

    kliendi_konto: str = Field(alias="Kliendi konto")
    reatyup: str = Field(alias="Reatüüp")
    kuupaev: str = Field(alias="Kuupäev")  # Will be parsed to date
    saaja_maksja: str = Field(alias="Saaja/Maksja")
    selgitus: str = Field(alias="Selgitus")  # Transaction description
    summa: str = Field(alias="Summa")  # Will be parsed to Decimal
    valuuta: str = Field(alias="Valuuta")
    deebet_kreedit: str = Field(alias="Deebet/Kreedit")  # D or K
    arhiveerimistunnus: str = Field(alias="Arhiveerimistunnus")  # Reference ID
    tehingu_tyup: str = Field(alias="Tehingu tüüp")
    viitenumber: str = Field(alias="Viitenumber")
    dokumendi_number: str = Field(alias="Dokumendi number")

    class Config:
        """Pydantic configuration."""

        populate_by_name = True
        str_strip_whitespace = True

    @field_validator("summa", mode="before")
    @classmethod
    def parse_decimal(cls, v: str) -> str:
        """Allow Estonian decimal comma separator."""
        if isinstance(v, str):
            return v.replace(",", ".")
        return v  # type: ignore[unreachable]


class LightyearCSVRow(BaseModel):
    """Lightyear broker CSV row model.

    Fields match English CSV headers from Lightyear export.
    """

    date: str = Field(alias="Date")  # Will be parsed to datetime
    reference: str = Field(alias="Reference")
    ticker: str = Field(default="", alias="Ticker")
    isin: str = Field(default="", alias="ISIN")
    type: str = Field(alias="Type")
    quantity: str = Field(default="", alias="Quantity")
    ccy: str = Field(alias="CCY")
    price_per_share: str = Field(default="", alias="Price/share")
    gross_amount: str = Field(default="", alias="Gross Amount")
    fx_rate: str = Field(default="", alias="FX Rate")
    fee: str = Field(default="0.00", alias="Fee")
    net_amt: str = Field(alias="Net Amt.")
    tax_amt: str = Field(default="", alias="Tax Amt.")

    class Config:
        """Pydantic configuration."""

        populate_by_name = True
        str_strip_whitespace = True

    @field_validator(
        "quantity", "price_per_share", "gross_amount", "fee", "net_amt", "tax_amt", mode="before"
    )
    @classmethod
    def handle_empty_decimal(cls, v: str) -> str:
        """Convert empty strings to '0' for decimal fields."""
        if v == "" or v is None:
            return "0"
        return v


class ParsedTransaction(BaseModel):
    """Unified transaction representation after parsing broker CSV.

    This model is broker-agnostic and used by ImportService.
    """

    date: datetime
    transaction_type: str  # Normalized: 'BUY', 'SELL', 'DIVIDEND', etc.

    # Amount (always positive)
    amount: Decimal  # Transaction amount (positive)
    currency: str  # ISO currency code: EUR, USD, GBP
    debit_credit: str  # "D" for debit (out), "K" for credit (in)

    # For stock/bond transactions
    ticker: str | None = None  # NULL for non-security transactions
    isin: str | None = None  # For bonds and international securities
    quantity: Decimal | None = None  # NULL for non-trade transactions
    price: Decimal | None = None  # NULL for non-trade transactions

    # For currency conversions
    conversion_from_amount: Decimal | None = None  # Source amount
    conversion_from_currency: str | None = None  # Source currency

    # Common fields
    fees: Decimal = Decimal("0.00")
    tax_amount: Decimal | None = None  # Tax withheld
    net_amount: Decimal  # Net amount after fees/taxes
    gross_amount: Decimal | None = None  # Gross before deductions

    # Import tracking
    broker_reference_id: str  # Unique ID from broker CSV
    broker_source: str  # 'swedbank' or 'lightyear'
    original_data: dict[str, str]  # Original CSV row for audit trail

    # Optional details
    company_name: str | None = None
    exchange: str | None = None
    description: str | None = None

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True
