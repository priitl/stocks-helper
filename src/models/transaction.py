"""
Transaction model for all account transactions.

Tracks all financial transactions (buy/sell, deposits, withdrawals, conversions, etc.)
with account-based structure and proper debit/credit accounting.
"""

import enum
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.lib.db import Base

if TYPE_CHECKING:
    from src.models.account import Account
    from src.models.holding import Holding
    from src.models.import_batch import ImportBatch
    from src.models.reconciliation import Reconciliation


class TransactionType(str, enum.Enum):
    """Enumeration of transaction types."""

    # Stock/Security related
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    DISTRIBUTION = "DISTRIBUTION"

    # Account level
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    CONVERSION = "CONVERSION"  # Currency conversion
    INTEREST = "INTEREST"
    REWARD = "REWARD"
    FEE = "FEE"
    TAX = "TAX"  # VAT, withholding tax, etc.

    # Other
    ADJUSTMENT = "ADJUSTMENT"  # Manual corrections


class Transaction(Base):  # type: ignore[misc,valid-type]
    """
    Represents any financial transaction in an account.

    Uses account-based structure where all transactions belong to an account.
    Some transactions (BUY, SELL, DIVIDEND) also link to holdings.

    Attributes:
        id: Unique identifier
        account_id: Reference to the account (required)
        holding_id: Reference to holding (optional, for stock-related transactions)
        type: Transaction type
        date: Transaction date
        amount: Transaction amount (always positive)
        currency: Currency of the transaction
        debit_credit: "D" for debit (money out), "K" for credit (money in)

        # For stock transactions
        quantity: Number of shares/units
        price: Price per share/unit

        # For currency conversions
        conversion_from_amount: Source amount (e.g., 20.10 USD)
        conversion_from_currency: Source currency

        # Common
        fees: Transaction fees
        exchange_rate: Exchange rate to base currency
        notes: Optional notes

        # Import tracking
        broker_source: Source broker/bank
        broker_reference_id: Broker's transaction ID
        import_batch_id: Import batch reference
    """

    __tablename__ = "transactions"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Foreign keys
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    holding_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("holdings.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    import_batch_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("import_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Transaction details
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType),
        nullable=False,
        index=True,
    )

    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    # Main amount (always positive, use debit_credit for direction)
    # DECIMAL PRECISION: Numeric(20, 8) for exact accounting
    # - 20 digits total: handles up to $999,999,999,999.99999999
    # - 8 decimal places: required for exact cost basis tracking with fractional shares
    # - Used for: transaction amounts, fees, taxes, conversion amounts
    # - Rationale: Fractional shares × high-precision prices = amounts requiring >2 decimals
    #   Example: 0.12345678 shares × $123.456789/share = $15.24141295 (needs 8 decimals)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    debit_credit: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
    )

    # For stock/bond transactions
    # DECIMAL PRECISION: Numeric(20, 8) for quantities and prices
    # - 20 digits total: handles up to 999,999,999,999.99999999
    # - 8 decimal places: supports fractional shares and precise pricing
    # - Used for: share quantities, prices per share, exchange rates
    # - Rationale: Modern brokers support fractional shares (e.g., 0.12345678 shares)
    #   and some assets trade at very precise prices (crypto, forex, etc.)
    # - Example: DRIP programs often result in fractional shares like 1.23456789
    quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    # For currency conversions (the "from" side)
    # Uses Numeric(20, 8) - same as amount field (exact accounting precision)
    conversion_from_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    conversion_from_currency: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
    )

    # Common fields
    # Uses Numeric(20, 8) - exact accounting precision for monetary amounts
    fees: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        default=Decimal("0.00"),
    )

    tax_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    # Uses Numeric(20, 8) - high precision for exchange rates
    # Example: EUR/USD rate might be 1.08345678
    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
        default=Decimal("1.0"),
    )

    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Import tracking
    broker_source: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    broker_reference_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
    )

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    account: Mapped["Account"] = relationship(
        "Account",
        back_populates="transactions",
    )

    holding: Mapped["Holding | None"] = relationship(
        "Holding",
        back_populates="transactions",
    )

    import_batch: Mapped["ImportBatch | None"] = relationship(
        "ImportBatch",
        back_populates="transactions",
    )

    reconciliation: Mapped["Reconciliation | None"] = relationship(
        "Reconciliation",
        back_populates="transaction",
        uselist=False,
    )

    # Constraints
    __table_args__ = (
        # Amount and fees must be non-negative (allow 0 for gifts)
        CheckConstraint("amount >= 0", name="check_amount_positive"),
        CheckConstraint("fees >= 0", name="check_fees_non_negative"),
        # Quantity and price non-negative when present (allow 0 for gifts)
        CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="check_quantity_positive_if_present",
        ),
        CheckConstraint(
            "price IS NULL OR price >= 0",
            name="check_price_positive_if_present",
        ),
        # Exchange rate must be positive
        CheckConstraint("exchange_rate > 0", name="check_exchange_rate_positive"),
        # Debit/Credit validation
        CheckConstraint(
            "debit_credit IN ('D', 'K')",
            name="check_debit_credit_valid",
        ),
        # Conversion fields must both be set or both NULL
        CheckConstraint(
            "(conversion_from_amount IS NULL AND conversion_from_currency IS NULL) OR "
            "(conversion_from_amount IS NOT NULL AND conversion_from_currency IS NOT NULL)",
            name="check_conversion_fields_together",
        ),
        # Unique constraint: (broker_source, broker_reference_id, type, currency)
        # Added currency to support conversions where same ref ID is used for both sides
        UniqueConstraint(
            "broker_source",
            "broker_reference_id",
            "type",
            "currency",
            name="unique_broker_transaction_type_currency",
        ),
        # Composite indexes for common query patterns
        Index(
            "idx_transactions_account_date",
            "account_id",
            "date",
        ),
        Index(
            "idx_transactions_holding_date",
            "holding_id",
            "date",
        ),
        Index(
            "idx_transactions_batch_type",
            "import_batch_id",
            "type",
        ),
    )

    def __repr__(self) -> str:
        """Return string representation of transaction."""
        return (
            f"<Transaction(id={self.id!r}, "
            f"type={self.type.value}, "
            f"date={self.date}, "
            f"amount={self.amount} {self.currency} {self.debit_credit})>"
        )
