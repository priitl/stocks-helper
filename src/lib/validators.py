"""
Input validation utilities.

Provides validation functions for user inputs including ticker symbols,
currency codes, quantities, prices, and dates.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Union

from src.lib.errors import InvalidCurrencyError, InvalidQuantityError, ValidationError


def validate_ticker(ticker: str) -> str:
    """
    Validate and normalize ticker symbol.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Normalized ticker symbol (uppercase, trimmed)

    Raises:
        ValidationError: If ticker format is invalid

    Examples:
        >>> validate_ticker("aapl")
        'AAPL'
        >>> validate_ticker("  MSFT  ")
        'MSFT'
        >>> validate_ticker("123")
        Traceback (most recent call last):
        ...
        ValidationError: Invalid ticker format: 123
    """
    ticker = ticker.upper().strip()

    # Ticker symbols: 1-10 total characters, uppercase letters, may include one dot
    if not re.match(r"^[A-Z]{1,10}(\.[A-Z]{1,3})?$", ticker) or len(ticker) > 10:
        raise ValidationError(
            f"Invalid ticker format: {ticker}. "
            "Ticker must be 1-10 uppercase letters (e.g., AAPL, MSFT, BRK.B)"
        )

    return ticker


def validate_quantity(
    quantity: Decimal, min_value: Decimal = Decimal("0"), max_value: Decimal = Decimal("1000000")
) -> Decimal:
    """
    Validate quantity is positive and within reasonable range.

    Args:
        quantity: Quantity to validate
        min_value: Minimum allowed value (default: 0, exclusive)
        max_value: Maximum allowed value (default: 1,000,000)

    Returns:
        Validated quantity

    Raises:
        InvalidQuantityError: If quantity is out of range

    Examples:
        >>> validate_quantity(Decimal("10"))
        Decimal('10')
        >>> validate_quantity(Decimal("-5"))
        Traceback (most recent call last):
        ...
        InvalidQuantityError: Quantity -5 must be positive
        >>> validate_quantity(Decimal("2000000"))
        Traceback (most recent call last):
        ...
        InvalidQuantityError: Quantity 2000000 exceeds maximum 1000000
    """
    if quantity <= min_value:
        raise InvalidQuantityError(quantity, "must be positive")

    if quantity > max_value:
        raise InvalidQuantityError(quantity, f"exceeds maximum {max_value}")

    return quantity


def validate_price(
    price: Decimal, min_value: Decimal = Decimal("0"), max_value: Decimal = Decimal("1000000")
) -> Decimal:
    """
    Validate price is positive and within reasonable range.

    Args:
        price: Price to validate
        min_value: Minimum allowed value (default: 0, exclusive)
        max_value: Maximum allowed value (default: 1,000,000)

    Returns:
        Validated price

    Raises:
        ValidationError: If price is out of range

    Examples:
        >>> validate_price(Decimal("150.50"))
        Decimal('150.50')
        >>> validate_price(Decimal("0"))
        Traceback (most recent call last):
        ...
        ValidationError: Price 0 must be positive
    """
    if price <= min_value:
        raise ValidationError(f"Price {price} must be positive")

    if price > max_value:
        raise ValidationError(f"Price {price} exceeds maximum {max_value}")

    return price


def validate_currency(currency: str, valid_currencies: Optional[set[str]] = None) -> str:
    """
    Validate ISO 4217 currency code.

    Args:
        currency: Currency code to validate
        valid_currencies: Optional set of valid currencies. Defaults to common currencies.

    Returns:
        Normalized currency code (uppercase, trimmed)

    Raises:
        InvalidCurrencyError: If currency code is invalid

    Examples:
        >>> validate_currency("usd")
        'USD'
        >>> validate_currency("  EUR  ")
        'EUR'
        >>> validate_currency("XXX")
        Traceback (most recent call last):
        ...
        InvalidCurrencyError: Invalid currency code: XXX
    """
    if valid_currencies is None:
        # Common currencies supported by the application
        valid_currencies = {
            "USD",
            "EUR",
            "GBP",
            "JPY",
            "CHF",
            "CAD",
            "AUD",
            "CNY",
            "HKD",
            "SGD",
            "SEK",
            "NOK",
            "DKK",
            "INR",
            "KRW",
            "BRL",
            "MXN",
            "ZAR",
        }

    currency = currency.upper().strip()

    # Currency codes must be exactly 3 letters
    if not re.match(r"^[A-Z]{3}$", currency):
        raise InvalidCurrencyError(currency, "Currency code must be exactly 3 letters")

    if currency not in valid_currencies:
        raise InvalidCurrencyError(
            currency,
            f"Currency not supported. Valid currencies: {', '.join(sorted(valid_currencies))}",
        )

    return currency


def validate_date(
    date_value: Union[date, datetime, str],
    min_date: Optional[date] = None,
    max_date: Optional[date] = None,
    allow_future: bool = False,
) -> date:
    """
    Validate date is within allowed range.

    Args:
        date_value: Date to validate (date object, datetime object, or string)
        min_date: Minimum allowed date (default: 2000-01-01)
        max_date: Maximum allowed date (default: today)
        allow_future: Whether to allow future dates (default: False)

    Returns:
        Validated date

    Raises:
        ValidationError: If date is out of range

    Examples:
        >>> from datetime import date
        >>> validate_date(date(2023, 1, 15))
        datetime.date(2023, 1, 15)
        >>> validate_date("2023-01-15")
        datetime.date(2023, 1, 15)
        >>> validate_date(date(1999, 1, 1))
        Traceback (most recent call last):
        ...
        ValidationError: Date 1999-01-01 is too far in the past
    """
    # Parse string to date if needed
    parsed_date: date
    if isinstance(date_value, str):
        # Try common date formats
        original_value = date_value
        parsed = False
        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
            try:
                parsed_date = datetime.strptime(date_value, fmt).date()
                parsed = True
                break
            except ValueError:
                continue
        if not parsed:
            raise ValidationError(f"Invalid date format: {original_value}")
    elif isinstance(date_value, datetime):
        parsed_date = date_value.date()
    else:
        parsed_date = date_value

    if min_date is None:
        min_date = date(2000, 1, 1)  # Reasonable historical data limit

    # Set max_date to today only if not allowing future dates
    if max_date is None and not allow_future:
        max_date = date.today()

    if parsed_date < min_date:
        raise ValidationError(f"Date {parsed_date} is too far in the past (minimum: {min_date})")

    if max_date is not None and parsed_date > max_date:
        if not allow_future:
            raise ValidationError(f"Date {parsed_date} cannot be in the future")
        else:
            raise ValidationError(f"Date {parsed_date} is after maximum allowed date {max_date}")

    return parsed_date


def validate_percentage(
    percentage: Decimal, min_value: Decimal = Decimal("0"), max_value: Decimal = Decimal("100")
) -> Decimal:
    """
    Validate percentage is within reasonable range.

    Args:
        percentage: Percentage to validate
        min_value: Minimum allowed value (default: 0%)
        max_value: Maximum allowed value (default: 100%)

    Returns:
        Validated percentage

    Raises:
        ValidationError: If percentage is out of range

    Examples:
        >>> validate_percentage(Decimal("15.5"))
        Decimal('15.5')
        >>> validate_percentage(Decimal("150"))
        Traceback (most recent call last):
        ...
        ValidationError: Percentage must be between 0 and 100
    """
    if percentage < min_value or percentage > max_value:
        raise ValidationError(f"Percentage must be between {min_value} and {max_value}")

    return percentage


def sanitize_string(
    text: str, max_length: int = 1000, allowed_pattern: Optional[str] = None
) -> str:
    """
    Sanitize user input string.

    Args:
        text: String to sanitize
        max_length: Maximum allowed length
        allowed_pattern: Optional regex pattern for allowed characters

    Returns:
        Sanitized string (trimmed, length-limited)

    Raises:
        ValidationError: If string exceeds length or contains disallowed characters

    Examples:
        >>> sanitize_string("  Hello World  ", max_length=20)
        'Hello World'
        >>> sanitize_string("Too" * 500, max_length=100)
        Traceback (most recent call last):
        ...
        ValidationError: Input exceeds maximum length of 100 characters
    """
    text = text.strip()

    if len(text) > max_length:
        raise ValidationError(f"Input exceeds maximum length of {max_length} characters")

    if allowed_pattern and not re.match(allowed_pattern, text):
        raise ValidationError("Input contains disallowed characters")

    return text
