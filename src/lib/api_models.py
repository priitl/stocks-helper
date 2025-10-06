"""Pydantic models for API responses."""

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class AlphaVantageTimeSeriesData(BaseModel):
    """Alpha Vantage daily time series data point."""

    open: float = Field(alias="1. open")
    high: float = Field(alias="2. high")
    low: float = Field(alias="3. low")
    close: float = Field(alias="4. close")
    volume: int = Field(alias="5. volume")

    model_config = {"populate_by_name": True}

    @field_validator("open", "high", "low", "close")
    @classmethod
    def validate_price_positive(cls, v: float) -> float:
        """Ensure prices are positive."""
        if v <= 0:
            raise ValueError(f"Price must be positive, got {v}")
        return v

    @field_validator("volume")
    @classmethod
    def validate_volume_non_negative(cls, v: int) -> int:
        """Ensure volume is non-negative."""
        if v < 0:
            raise ValueError(f"Volume must be non-negative, got {v}")
        return v


class AlphaVantageTimeSeriesResponse(BaseModel):
    """Alpha Vantage TIME_SERIES_DAILY response."""

    meta_data: Optional[dict[str, str]] = Field(None, alias="Meta Data")
    time_series: Optional[dict[str, AlphaVantageTimeSeriesData]] = Field(
        None, alias="Time Series (Daily)"
    )
    error_message: Optional[str] = Field(None, alias="Error Message")
    note: Optional[str] = Field(None, alias="Note")

    model_config = {"populate_by_name": True}

    @field_validator("time_series")
    @classmethod
    def validate_time_series_not_empty(
        cls, v: Optional[dict[str, AlphaVantageTimeSeriesData]]
    ) -> Optional[dict[str, AlphaVantageTimeSeriesData]]:
        """Ensure time series has data if present."""
        if v is not None and len(v) == 0:
            raise ValueError("Time series cannot be empty")
        return v


class AlphaVantageOverviewResponse(BaseModel):
    """Alpha Vantage OVERVIEW (fundamental data) response."""

    symbol: Optional[str] = Field(None, alias="Symbol")
    name: Optional[str] = Field(None, alias="Name")
    exchange: Optional[str] = Field(None, alias="Exchange")
    sector: Optional[str] = Field(None, alias="Sector")
    industry: Optional[str] = Field(None, alias="Industry")
    market_cap: Optional[str] = Field(None, alias="MarketCapitalization")
    pe_ratio: Optional[str] = Field(None, alias="PERatio")
    peg_ratio: Optional[str] = Field(None, alias="PEGRatio")
    book_value: Optional[str] = Field(None, alias="BookValue")
    dividend_yield: Optional[str] = Field(None, alias="DividendYield")
    eps: Optional[str] = Field(None, alias="EPS")
    revenue_per_share: Optional[str] = Field(None, alias="RevenuePerShareTTM")
    profit_margin: Optional[str] = Field(None, alias="ProfitMargin")
    operating_margin: Optional[str] = Field(None, alias="OperatingMarginTTM")
    return_on_assets: Optional[str] = Field(None, alias="ReturnOnAssetsTTM")
    return_on_equity: Optional[str] = Field(None, alias="ReturnOnEquityTTM")
    revenue_ttm: Optional[str] = Field(None, alias="RevenueTTM")
    gross_profit_ttm: Optional[str] = Field(None, alias="GrossProfitTTM")
    diluted_eps_ttm: Optional[str] = Field(None, alias="DilutedEPSTTM")
    quarterly_earnings_growth_yoy: Optional[str] = Field(None, alias="QuarterlyEarningsGrowthYOY")
    quarterly_revenue_growth_yoy: Optional[str] = Field(None, alias="QuarterlyRevenueGrowthYOY")
    analyst_target_price: Optional[str] = Field(None, alias="AnalystTargetPrice")
    trailing_pe: Optional[str] = Field(None, alias="TrailingPE")
    forward_pe: Optional[str] = Field(None, alias="ForwardPE")
    price_to_sales_ratio: Optional[str] = Field(None, alias="PriceToSalesRatioTTM")
    price_to_book_ratio: Optional[str] = Field(None, alias="PriceToBookRatio")
    ev_to_revenue: Optional[str] = Field(None, alias="EVToRevenue")
    ev_to_ebitda: Optional[str] = Field(None, alias="EVToEBITDA")
    beta: Optional[str] = Field(None, alias="Beta")
    week_52_high: Optional[str] = Field(None, alias="52WeekHigh")
    week_52_low: Optional[str] = Field(None, alias="52WeekLow")
    moving_avg_50: Optional[str] = Field(None, alias="50DayMovingAverage")
    moving_avg_200: Optional[str] = Field(None, alias="200DayMovingAverage")
    shares_outstanding: Optional[str] = Field(None, alias="SharesOutstanding")
    description: Optional[str] = Field(None, alias="Description")
    error_message: Optional[str] = Field(None, alias="Error Message")
    note: Optional[str] = Field(None, alias="Note")

    model_config = {"populate_by_name": True}


class YahooFinanceQuote(BaseModel):
    """Yahoo Finance quote data (simplified)."""

    symbol: str
    regular_market_price: Optional[float] = None
    regular_market_open: Optional[float] = None
    regular_market_day_high: Optional[float] = None
    regular_market_day_low: Optional[float] = None
    regular_market_volume: Optional[int] = None
    regular_market_previous_close: Optional[float] = None

    @field_validator(
        "regular_market_price",
        "regular_market_open",
        "regular_market_day_high",
        "regular_market_day_low",
        "regular_market_previous_close",
    )
    @classmethod
    def validate_price_positive(cls, v: Optional[float]) -> Optional[float]:
        """Ensure prices are positive."""
        if v is not None and v <= 0:
            raise ValueError(f"Price must be positive, got {v}")
        return v

    @field_validator("regular_market_volume")
    @classmethod
    def validate_volume_non_negative(cls, v: Optional[int]) -> Optional[int]:
        """Ensure volume is non-negative."""
        if v is not None and v < 0:
            raise ValueError(f"Volume must be non-negative, got {v}")
        return v


class ExchangeRateResponse(BaseModel):
    """Exchange rate API response."""

    base: str
    target: str
    rate: float
    timestamp: Optional[str] = None

    @field_validator("rate")
    @classmethod
    def validate_rate_positive(cls, v: float) -> float:
        """Ensure exchange rate is positive."""
        if v <= 0:
            raise ValueError(f"Exchange rate must be positive, got {v}")
        return v

    @field_validator("base", "target")
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        """Ensure currency codes are 3 characters."""
        if len(v) != 3:
            raise ValueError(f"Currency code must be 3 characters, got '{v}'")
        return v.upper()


class MarketDataPoint(BaseModel):
    """Normalized market data point."""

    ticker: str
    timestamp: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    volume: Optional[int] = None
    source: str
    is_latest: bool = False

    @field_validator("open", "high", "low", "close")
    @classmethod
    def validate_price_positive(cls, v: Optional[float]) -> Optional[float]:
        """Ensure prices are positive."""
        if v is not None and v <= 0:
            raise ValueError(f"Price must be positive, got {v}")
        return v

    @field_validator("volume")
    @classmethod
    def validate_volume_non_negative(cls, v: Optional[int]) -> Optional[int]:
        """Ensure volume is non-negative."""
        if v is not None and v < 0:
            raise ValueError(f"Volume must be non-negative, got {v}")
        return v


def validate_alpha_vantage_response(data: dict[str, Any]) -> AlphaVantageTimeSeriesResponse:
    """
    Validate Alpha Vantage API response.

    Args:
        data: Raw API response

    Returns:
        Validated AlphaVantageTimeSeriesResponse

    Raises:
        ValueError: If response contains errors or is invalid
    """
    response: AlphaVantageTimeSeriesResponse = AlphaVantageTimeSeriesResponse.model_validate(data)

    # Check for API errors
    if response.error_message:
        raise ValueError(f"Alpha Vantage API error: {response.error_message}")

    if response.note:
        raise ValueError(f"Alpha Vantage rate limit: {response.note}")

    if not response.time_series:
        raise ValueError("Alpha Vantage response missing time series data")

    return response


def validate_alpha_vantage_overview(data: dict[str, Any]) -> AlphaVantageOverviewResponse:
    """
    Validate Alpha Vantage overview (fundamental) response.

    Args:
        data: Raw API response

    Returns:
        Validated AlphaVantageOverviewResponse

    Raises:
        ValueError: If response contains errors or is invalid
    """
    response: AlphaVantageOverviewResponse = AlphaVantageOverviewResponse.model_validate(data)

    # Check for API errors
    if response.error_message:
        raise ValueError(f"Alpha Vantage API error: {response.error_message}")

    if response.note:
        raise ValueError(f"Alpha Vantage rate limit: {response.note}")

    if not response.symbol:
        raise ValueError("Alpha Vantage overview response missing symbol")

    return response
