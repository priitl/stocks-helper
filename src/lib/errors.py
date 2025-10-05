"""Custom exception classes for stocks-helper."""


class StocksHelperError(Exception):
    """Base exception for all stocks-helper errors."""

    def __init__(self, message: str):
        """Initialize with error message."""
        self.message = message
        super().__init__(message)


class APIError(StocksHelperError):
    """API-related errors."""

    pass


class APIRateLimitError(APIError):
    """API rate limit exceeded."""

    def __init__(self, api_name: str, retry_after: str = "later"):
        """
        Initialize rate limit error.

        Args:
            api_name: Name of the API that hit rate limit
            retry_after: When to retry (e.g., "15 minutes", "tomorrow")
        """
        message = f"{api_name} API rate limit exceeded. Try again {retry_after}."
        super().__init__(message)


class APIConnectionError(APIError):
    """Failed to connect to API."""

    def __init__(self, api_name: str, details: str = ""):
        """
        Initialize connection error.

        Args:
            api_name: Name of the API
            details: Additional error details
        """
        message = f"Failed to connect to {api_name} API"
        if details:
            message += f": {details}"
        super().__init__(message)


class DataError(StocksHelperError):
    """Data validation or processing errors."""

    pass


class InvalidCurrencyError(DataError):
    """Invalid currency code."""

    def __init__(self, currency: str, custom_message: str = ""):
        """
        Initialize with invalid currency.

        Args:
            currency: The invalid currency code
            custom_message: Optional custom error message
        """
        if custom_message:
            message = f"Invalid currency code: '{currency}'. {custom_message}"
        else:
            message = (
                f"Invalid currency code: '{currency}'. "
                f"Must be a valid ISO 4217 code (e.g., USD, EUR, GBP)."
            )
        super().__init__(message)


class InsufficientQuantityError(DataError):
    """Attempt to sell more shares than owned."""

    def __init__(self, ticker: str, available: float, requested: float):
        """
        Initialize with quantity details.

        Args:
            ticker: Stock ticker symbol
            available: Available quantity
            requested: Requested quantity to sell
        """
        message = (
            f"Cannot sell {requested} shares of {ticker}. " f"Only {available} shares available."
        )
        super().__init__(message)


class InvalidTickerError(DataError):
    """Invalid or unknown stock ticker."""

    def __init__(self, ticker: str):
        """
        Initialize with ticker.

        Args:
            ticker: The invalid ticker symbol
        """
        message = f"Invalid or unknown ticker symbol: '{ticker}'"
        super().__init__(message)


class DatabaseError(StocksHelperError):
    """Database operation errors."""

    pass


class PortfolioNotFoundError(DatabaseError):
    """Portfolio not found in database."""

    def __init__(self, portfolio_id: str):
        """
        Initialize with portfolio ID.

        Args:
            portfolio_id: The portfolio ID that wasn't found
        """
        message = f"Portfolio not found: {portfolio_id}"
        super().__init__(message)


class StockNotFoundError(DatabaseError):
    """Stock not found in database."""

    def __init__(self, ticker: str):
        """
        Initialize with ticker.

        Args:
            ticker: The ticker that wasn't found
        """
        message = (
            f"Stock not found in database: {ticker}. Add it first with: "
            f"stocks-helper stock add-batch --tickers {ticker}"
        )
        super().__init__(message)


class HoldingNotFoundError(DatabaseError):
    """Holding not found in portfolio."""

    def __init__(self, ticker: str, portfolio_id: str):
        """
        Initialize with ticker and portfolio.

        Args:
            ticker: Stock ticker
            portfolio_id: Portfolio ID
        """
        message = f"Holding '{ticker}' not found in portfolio {portfolio_id}"
        super().__init__(message)


class ConfigurationError(StocksHelperError):
    """Configuration errors."""

    pass


class MissingAPIKeyError(ConfigurationError):
    """Required API key not configured."""

    def __init__(self, api_name: str, env_var: str):
        """
        Initialize with API details.

        Args:
            api_name: Name of the API
            env_var: Environment variable name
        """
        message = (
            f"{api_name} API key not configured. "
            f"Set environment variable: export {env_var}=your-key-here"
        )
        super().__init__(message)


class ValidationError(DataError):
    """Input validation errors."""

    pass


class BatchProcessingError(StocksHelperError):
    """Batch processing errors."""

    pass


class InvalidDateError(ValidationError):
    """Invalid date format or value."""

    def __init__(self, date_str: str, expected_format: str = "YYYY-MM-DD"):
        """
        Initialize with date details.

        Args:
            date_str: The invalid date string
            expected_format: Expected date format
        """
        message = f"Invalid date: '{date_str}'. Expected format: {expected_format}"
        super().__init__(message)


class InvalidPriceError(ValidationError):
    """Invalid price value."""

    def __init__(self, price: float, reason: str = ""):
        """
        Initialize with price details.

        Args:
            price: The invalid price
            reason: Reason why price is invalid
        """
        message = f"Invalid price: {price}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)


class InvalidQuantityError(ValidationError):
    """Invalid quantity value."""

    def __init__(self, quantity: float, reason: str = ""):
        """
        Initialize with quantity details.

        Args:
            quantity: The invalid quantity
            reason: Reason why quantity is invalid
        """
        message = f"Invalid quantity: {quantity}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)


# Error message helpers


def format_error_message(error: Exception) -> str:
    """
    Format exception into user-friendly error message.

    Args:
        error: The exception to format

    Returns:
        Formatted error message
    """
    if isinstance(error, StocksHelperError):
        return error.message

    # Generic errors
    error_type = type(error).__name__
    return f"{error_type}: {str(error)}"


def get_error_color(error: Exception) -> str:
    """
    Get Rich color for error type.

    Args:
        error: The exception

    Returns:
        Rich color name
    """
    if isinstance(error, APIRateLimitError):
        return "yellow"
    elif isinstance(error, (ValidationError, DataError)):
        return "red"
    elif isinstance(error, ConfigurationError):
        return "orange"
    elif isinstance(error, DatabaseError):
        return "magenta"
    else:
        return "red"
