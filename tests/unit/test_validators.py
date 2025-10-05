"""Unit tests for input validators."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from src.lib.errors import (
    InvalidCurrencyError,
    InvalidQuantityError,
    ValidationError,
)
from src.lib.validators import (
    validate_currency,
    validate_date,
    validate_percentage,
    validate_price,
    validate_quantity,
    validate_ticker,
)


@pytest.mark.unit
class TestValidateTicker:
    """Test suite for validate_ticker."""

    def test_validate_ticker_uppercase(self):
        """Ticker is converted to uppercase."""
        assert validate_ticker("aapl") == "AAPL"
        assert validate_ticker("msft") == "MSFT"

    def test_validate_ticker_strips_whitespace(self):
        """Leading/trailing whitespace is removed."""
        assert validate_ticker("  AAPL  ") == "AAPL"
        assert validate_ticker("\tGOOGL\n") == "GOOGL"

    def test_validate_ticker_valid_formats(self):
        """Valid ticker formats are accepted."""
        assert validate_ticker("A") == "A"  # Single letter
        assert validate_ticker("AAPL") == "AAPL"  # 4 letters
        assert validate_ticker("MSFT") == "MSFT"  # Standard
        assert validate_ticker("GOOGL") == "GOOGL"  # 5 letters
        assert validate_ticker("BRK.B") == "BRK.B"  # With dot (Berkshire B shares)

    def test_validate_ticker_invalid_too_long(self):
        """Ticker longer than 10 characters is rejected."""
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("TOOLONGTICKERXYZ")

    def test_validate_ticker_invalid_numbers(self):
        """Ticker with only numbers is rejected."""
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("123")

    def test_validate_ticker_invalid_special_chars(self):
        """Ticker with special characters (except dot) is rejected."""
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("AAPL@")
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("AA-PL")
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("AA_PL")

    def test_validate_ticker_empty(self):
        """Empty ticker is rejected."""
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("")
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("   ")

    def test_validate_ticker_lowercase_numbers(self):
        """Lowercase ticker with numbers is rejected."""
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("aapl123")


@pytest.mark.unit
class TestValidateQuantity:
    """Test suite for validate_quantity."""

    def test_validate_quantity_positive(self):
        """Positive quantities are accepted."""
        assert validate_quantity(Decimal("1")) == Decimal("1")
        assert validate_quantity(Decimal("10.5")) == Decimal("10.5")
        assert validate_quantity(Decimal("1000")) == Decimal("1000")

    def test_validate_quantity_zero_rejected(self):
        """Zero quantity is rejected."""
        with pytest.raises(InvalidQuantityError, match="must be positive"):
            validate_quantity(Decimal("0"))

    def test_validate_quantity_negative_rejected(self):
        """Negative quantities are rejected."""
        with pytest.raises(InvalidQuantityError, match="must be positive"):
            validate_quantity(Decimal("-1"))
        with pytest.raises(InvalidQuantityError, match="must be positive"):
            validate_quantity(Decimal("-10.5"))

    def test_validate_quantity_max_limit(self):
        """Quantities exceeding max limit are rejected."""
        with pytest.raises(InvalidQuantityError, match="exceeds maximum"):
            validate_quantity(Decimal("2000000"))

    def test_validate_quantity_at_max_limit(self):
        """Quantity exactly at max limit is accepted."""
        max_val = Decimal("1000000")
        assert validate_quantity(max_val) == max_val

    def test_validate_quantity_custom_limits(self):
        """Custom min/max limits work correctly."""
        # Custom minimum
        with pytest.raises(InvalidQuantityError):
            validate_quantity(Decimal("5"), min_value=Decimal("10"))

        # Custom maximum
        with pytest.raises(InvalidQuantityError):
            validate_quantity(Decimal("100"), max_value=Decimal("50"))

    def test_validate_quantity_fractional(self):
        """Fractional quantities are accepted."""
        assert validate_quantity(Decimal("0.5")) == Decimal("0.5")
        assert validate_quantity(Decimal("0.01")) == Decimal("0.01")
        assert validate_quantity(Decimal("10.123456")) == Decimal("10.123456")


@pytest.mark.unit
class TestValidatePrice:
    """Test suite for validate_price."""

    def test_validate_price_positive(self):
        """Positive prices are accepted."""
        assert validate_price(Decimal("10.50")) == Decimal("10.50")
        assert validate_price(Decimal("100")) == Decimal("100")
        assert validate_price(Decimal("0.01")) == Decimal("0.01")

    def test_validate_price_zero_rejected(self):
        """Zero price is rejected."""
        with pytest.raises(ValidationError, match="must be positive"):
            validate_price(Decimal("0"))

    def test_validate_price_negative_rejected(self):
        """Negative prices are rejected."""
        with pytest.raises(ValidationError, match="must be positive"):
            validate_price(Decimal("-10"))

    def test_validate_price_max_limit(self):
        """Prices exceeding max limit are rejected."""
        with pytest.raises(ValidationError, match="exceeds maximum"):
            validate_price(Decimal("2000000"))

    def test_validate_price_high_precision(self):
        """High precision prices are accepted."""
        assert validate_price(Decimal("10.123456")) == Decimal("10.123456")
        assert validate_price(Decimal("0.00001")) == Decimal("0.00001")

    def test_validate_price_custom_limits(self):
        """Custom min/max limits work correctly."""
        # Custom minimum
        with pytest.raises(ValidationError):
            validate_price(Decimal("5"), min_value=Decimal("10"))

        # Custom maximum
        with pytest.raises(ValidationError):
            validate_price(Decimal("100"), max_value=Decimal("50"))


@pytest.mark.unit
class TestValidateCurrency:
    """Test suite for validate_currency."""

    def test_validate_currency_standard_codes(self):
        """Standard ISO 4217 currency codes are accepted."""
        assert validate_currency("USD") == "USD"
        assert validate_currency("EUR") == "EUR"
        assert validate_currency("GBP") == "GBP"
        assert validate_currency("JPY") == "JPY"

    def test_validate_currency_lowercase_uppercase(self):
        """Currency codes are converted to uppercase."""
        assert validate_currency("usd") == "USD"
        assert validate_currency("eur") == "EUR"

    def test_validate_currency_strips_whitespace(self):
        """Leading/trailing whitespace is removed."""
        assert validate_currency("  USD  ") == "USD"

    def test_validate_currency_invalid_length(self):
        """Currency codes must be exactly 3 characters."""
        with pytest.raises(InvalidCurrencyError, match="Invalid currency"):
            validate_currency("US")
        with pytest.raises(InvalidCurrencyError, match="Invalid currency"):
            validate_currency("USDD")

    def test_validate_currency_numbers_rejected(self):
        """Currency codes with numbers are rejected."""
        with pytest.raises(InvalidCurrencyError, match="Invalid currency"):
            validate_currency("US1")
        with pytest.raises(InvalidCurrencyError, match="Invalid currency"):
            validate_currency("123")

    def test_validate_currency_special_chars_rejected(self):
        """Currency codes with special characters are rejected."""
        with pytest.raises(InvalidCurrencyError, match="Invalid currency"):
            validate_currency("US$")
        with pytest.raises(InvalidCurrencyError, match="Invalid currency"):
            validate_currency("U-D")

    def test_validate_currency_empty_rejected(self):
        """Empty currency code is rejected."""
        with pytest.raises(InvalidCurrencyError):
            validate_currency("")

    def test_validate_currency_custom_whitelist(self):
        """Custom currency whitelist is enforced."""
        valid_currencies = {"USD", "EUR", "GBP"}

        # Accepted currencies
        assert validate_currency("USD", valid_currencies) == "USD"
        assert validate_currency("EUR", valid_currencies) == "EUR"

        # Rejected currency not in whitelist
        with pytest.raises(InvalidCurrencyError, match="not supported"):
            validate_currency("JPY", valid_currencies)


@pytest.mark.unit
class TestValidateDate:
    """Test suite for validate_date."""

    def test_validate_date_valid_object(self):
        """Date objects are accepted."""
        test_date = date(2025, 10, 5)
        assert validate_date(test_date) == test_date

    def test_validate_date_string_iso_format(self):
        """ISO format date strings are parsed."""
        assert validate_date("2025-10-05") == date(2025, 10, 5)

    def test_validate_date_string_various_formats(self):
        """Various date string formats are accepted."""
        # ISO format
        assert validate_date("2025-10-05") == date(2025, 10, 5)
        # US format
        assert validate_date("10/05/2025") == date(2025, 10, 5)

    def test_validate_date_future_rejected_by_default(self):
        """Future dates are rejected by default."""
        future_date = date(2030, 1, 1)
        with pytest.raises(ValidationError, match="cannot be in the future"):
            validate_date(future_date)

    def test_validate_date_future_allowed_with_flag(self):
        """Future dates can be allowed with allow_future=True."""
        future_date = date(2030, 1, 1)
        assert validate_date(future_date, allow_future=True) == future_date

    def test_validate_date_too_old_rejected(self):
        """Very old dates are rejected."""
        old_date = date(1800, 1, 1)
        with pytest.raises(ValidationError, match="too far in the past"):
            validate_date(old_date)

    def test_validate_date_invalid_string_format(self):
        """Invalid date strings are rejected."""
        with pytest.raises(ValidationError, match="Invalid date"):
            validate_date("not-a-date")
        with pytest.raises(ValidationError, match="Invalid date"):
            validate_date("2025-13-45")  # Invalid month/day

    def test_validate_date_empty_string(self):
        """Empty string is rejected."""
        with pytest.raises(ValidationError):
            validate_date("")

    def test_validate_date_datetime_object(self):
        """Datetime objects are converted to date."""
        test_datetime = datetime(2025, 10, 5, 14, 30, 0)
        result = validate_date(test_datetime)
        assert result == date(2025, 10, 5)


@pytest.mark.unit
class TestValidatePercentage:
    """Test suite for validate_percentage."""

    def test_validate_percentage_valid_range(self):
        """Percentages in valid range are accepted."""
        assert validate_percentage(Decimal("0")) == Decimal("0")
        assert validate_percentage(Decimal("50")) == Decimal("50")
        assert validate_percentage(Decimal("100")) == Decimal("100")

    def test_validate_percentage_decimal_values(self):
        """Decimal percentages are accepted."""
        assert validate_percentage(Decimal("25.5")) == Decimal("25.5")
        assert validate_percentage(Decimal("0.01")) == Decimal("0.01")
        assert validate_percentage(Decimal("99.99")) == Decimal("99.99")

    def test_validate_percentage_negative_rejected(self):
        """Negative percentages are rejected."""
        with pytest.raises(ValidationError, match="must be between 0 and 100"):
            validate_percentage(Decimal("-1"))

    def test_validate_percentage_over_100_rejected(self):
        """Percentages over 100 are rejected."""
        with pytest.raises(ValidationError, match="must be between 0 and 100"):
            validate_percentage(Decimal("101"))
        with pytest.raises(ValidationError, match="must be between 0 and 100"):
            validate_percentage(Decimal("200"))

    def test_validate_percentage_boundary_values(self):
        """Boundary values (0 and 100) are accepted."""
        assert validate_percentage(Decimal("0")) == Decimal("0")
        assert validate_percentage(Decimal("100")) == Decimal("100")


@pytest.mark.unit
class TestValidatorErrorMessages:
    """Test that validators provide helpful error messages."""

    def test_ticker_error_message_includes_format(self):
        """Ticker validation error includes format requirements."""
        try:
            validate_ticker("123")
        except ValidationError as e:
            assert "1-10 uppercase letters" in str(e)

    def test_quantity_error_message_includes_value(self):
        """Quantity validation error includes the invalid value."""
        try:
            validate_quantity(Decimal("-5"))
        except InvalidQuantityError as e:
            assert "-5" in str(e)

    def test_currency_error_message_includes_supported_list(self):
        """Currency validation error with whitelist shows supported currencies."""
        try:
            validate_currency("JPY", valid_currencies={"USD", "EUR"})
        except InvalidCurrencyError as e:
            assert "USD" in str(e) or "supported" in str(e).lower()

    def test_date_error_message_includes_reason(self):
        """Date validation error includes reason for failure."""
        try:
            validate_date(date(2030, 1, 1))
        except ValidationError as e:
            assert "future" in str(e).lower()


@pytest.mark.unit
class TestValidatorEdgeCases:
    """Test edge cases and unusual inputs."""

    def test_very_large_quantity(self):
        """Very large (but valid) quantities are accepted."""
        large_qty = Decimal("999999")
        assert validate_quantity(large_qty) == large_qty

    def test_very_small_quantity(self):
        """Very small fractional quantities are accepted."""
        small_qty = Decimal("0.00000001")
        assert validate_quantity(small_qty) == small_qty

    def test_price_with_many_decimals(self):
        """Prices with many decimal places are accepted."""
        precise_price = Decimal("123.123456789")
        assert validate_price(precise_price) == precise_price

    def test_ticker_with_dot(self):
        """International tickers with dots are accepted."""
        assert validate_ticker("BRK.A") == "BRK.A"
        assert validate_ticker("BRK.B") == "BRK.B"

    def test_ticker_max_length_with_dot(self):
        """Maximum length ticker with dot."""
        # 10 chars + .XXX
        long_ticker = "ABCDEFGHIJ.ABC"
        with pytest.raises(ValidationError):
            validate_ticker(long_ticker)

    def test_currency_from_different_case(self):
        """Mixed case currencies are normalized."""
        assert validate_currency("UsD") == "USD"
        assert validate_currency("EuR") == "EUR"
