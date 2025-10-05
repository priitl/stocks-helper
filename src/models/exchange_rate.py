"""
Exchange rate model for currency conversions.
"""

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.lib.db import Base


class ExchangeRate(Base):
    """
    Represents exchange rates between currency pairs on specific dates.

    Uses composite primary key (from_currency, to_currency, date) to ensure
    unique rates per currency pair per day.
    """

    __tablename__ = "exchange_rates"

    # Composite primary key fields
    from_currency: Mapped[str] = mapped_column(
        String(3),
        primary_key=True,
        nullable=False,
        comment="Source currency ISO 4217 code (e.g., USD, EUR)",
    )

    to_currency: Mapped[str] = mapped_column(
        String(3),
        primary_key=True,
        nullable=False,
        comment="Target currency ISO 4217 code (e.g., USD, EUR)",
    )

    date: Mapped[date_type] = mapped_column(
        Date,
        primary_key=True,
        nullable=False,
        comment="Date of the exchange rate",
    )

    # Rate field with validation
    rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=False,
        comment="Exchange rate from source to target currency",
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint("rate > 0", name="check_rate_positive"),
        Index(
            "ix_exchange_rates_lookup",
            "from_currency",
            "to_currency",
            "date",
        ),
    )

    def validate_self_conversion(self) -> None:
        """
        Validate that self-conversion rates equal 1.0.

        Raises:
            ValueError: If currency converts to itself with rate != 1.0
        """
        if self.from_currency == self.to_currency and self.rate != Decimal("1.0"):
            raise ValueError(
                f"Self-conversion rate for {self.from_currency} must be 1.0, " f"got {self.rate}"
            )

    def __repr__(self) -> str:
        """String representation showing the conversion rate."""
        return (
            f"ExchangeRate({self.from_currency}/{self.to_currency} "
            f"= {self.rate} on {self.date})"
        )
