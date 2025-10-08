"""Market hours utilities for dynamic cache TTL based on trading hours.

Provides functions to determine if markets are open and calculate
appropriate cache TTLs for fresher data during trading hours.
"""

from datetime import datetime, time

import pytz


# Major US market holidays (NYSE/NASDAQ)
# Note: This is a simplified list. For production, consider using a library like pandas_market_calendars
US_MARKET_HOLIDAYS_2025 = [
    "2025-01-01",  # New Year's Day
    "2025-01-20",  # Martin Luther King Jr. Day
    "2025-02-17",  # Presidents Day
    "2025-04-18",  # Good Friday
    "2025-05-26",  # Memorial Day
    "2025-07-03",  # Independence Day (observed)
    "2025-09-01",  # Labor Day
    "2025-11-27",  # Thanksgiving
    "2025-12-25",  # Christmas
]


def is_market_open(exchange: str = "NYSE", now: datetime | None = None) -> bool:
    """Check if a market is currently open.

    Args:
        exchange: Exchange code (default: NYSE)
        now: Current datetime (defaults to now in market timezone)

    Returns:
        True if market is open, False otherwise
    """
    if now is None:
        now = datetime.now(get_market_timezone(exchange))
    elif now.tzinfo is None:
        # Assume UTC if no timezone
        now = now.replace(tzinfo=pytz.UTC)

    # Convert to market timezone
    market_tz = get_market_timezone(exchange)
    now = now.astimezone(market_tz)

    # Check if it's a weekend
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    # Check if it's a holiday
    date_str = now.strftime("%Y-%m-%d")
    if date_str in US_MARKET_HOLIDAYS_2025:
        return False

    # Check if it's within market hours
    market_open, market_close = get_market_hours(exchange)
    current_time = now.time()

    return market_open <= current_time <= market_close


def get_market_timezone(exchange: str = "NYSE") -> pytz.tzinfo.BaseTzInfo:
    """Get timezone for a market exchange.

    Args:
        exchange: Exchange code

    Returns:
        pytz timezone object
    """
    # Map exchanges to timezones
    exchange_timezones = {
        "NYSE": "America/New_York",
        "NASDAQ": "America/New_York",
        "LSE": "Europe/London",  # London Stock Exchange
        "TSE": "Asia/Tokyo",  # Tokyo Stock Exchange
        "HKEX": "Asia/Hong_Kong",  # Hong Kong Exchange
        "SSE": "Asia/Shanghai",  # Shanghai Stock Exchange
    }

    tz_name = exchange_timezones.get(exchange, "America/New_York")
    return pytz.timezone(tz_name)


def get_market_hours(exchange: str = "NYSE") -> tuple[time, time]:
    """Get market open and close times for an exchange.

    Args:
        exchange: Exchange code

    Returns:
        Tuple of (open_time, close_time) as time objects
    """
    # Market hours by exchange (in local time)
    hours = {
        "NYSE": (time(9, 30), time(16, 0)),  # 9:30 AM - 4:00 PM ET
        "NASDAQ": (time(9, 30), time(16, 0)),  # 9:30 AM - 4:00 PM ET
        "LSE": (time(8, 0), time(16, 30)),  # 8:00 AM - 4:30 PM GMT
        "TSE": (time(9, 0), time(15, 0)),  # 9:00 AM - 3:00 PM JST
        "HKEX": (time(9, 30), time(16, 0)),  # 9:30 AM - 4:00 PM HKT
        "SSE": (time(9, 30), time(15, 0)),  # 9:30 AM - 3:00 PM CST
    }

    return hours.get(exchange, hours["NYSE"])


def get_cache_ttl(exchange: str = "NYSE", now: datetime | None = None) -> int:
    """Get cache TTL in seconds based on market hours.

    Returns shorter TTL during trading hours for fresher data,
    longer TTL after hours when prices don't change.

    Args:
        exchange: Exchange code (default: NYSE)
        now: Current datetime (defaults to now)

    Returns:
        TTL in seconds
            - 300 (5 minutes) during market hours
            - 3600 (1 hour) after hours/weekends
    """
    if is_market_open(exchange, now):
        return 300  # 5 minutes during trading
    else:
        return 3600  # 1 hour after hours/weekends


def time_until_market_open(exchange: str = "NYSE", now: datetime | None = None) -> int:
    """Calculate seconds until market opens.

    Args:
        exchange: Exchange code
        now: Current datetime (defaults to now)

    Returns:
        Seconds until market opens, or 0 if already open
    """
    if now is None:
        now = datetime.now(get_market_timezone(exchange))
    elif now.tzinfo is None:
        now = now.replace(tzinfo=pytz.UTC)

    # Convert to market timezone
    market_tz = get_market_timezone(exchange)
    now = now.astimezone(market_tz)

    if is_market_open(exchange, now):
        return 0

    # Calculate next market open
    market_open, _ = get_market_hours(exchange)

    # Check if market opens later today
    next_open = datetime.combine(now.date(), market_open)
    next_open = market_tz.localize(next_open)

    # If we're past today's open time, move to next weekday
    if now.time() > market_open or now.weekday() >= 5:
        # Move to next day
        next_day = now
        for _ in range(7):  # Max 7 days to find next trading day
            next_day = next_day.replace(
                day=next_day.day + 1,
                hour=market_open.hour,
                minute=market_open.minute,
                second=0,
                microsecond=0,
            )

            # Skip weekends
            if next_day.weekday() < 5:
                # Check if not a holiday
                date_str = next_day.strftime("%Y-%m-%d")
                if date_str not in US_MARKET_HOLIDAYS_2025:
                    next_open = next_day
                    break

    seconds_until = int((next_open - now).total_seconds())
    return max(0, seconds_until)


def get_adaptive_cache_ttl(
    exchange: str = "NYSE",
    min_ttl: int = 300,
    max_ttl: int = 3600,
    now: datetime | None = None,
) -> int:
    """Get adaptive cache TTL that gradually increases as market close approaches.

    Args:
        exchange: Exchange code
        min_ttl: Minimum TTL during peak hours (default: 5 minutes)
        max_ttl: Maximum TTL after hours (default: 1 hour)
        now: Current datetime (defaults to now)

    Returns:
        TTL in seconds, scaled based on time in trading day
    """
    if not is_market_open(exchange, now):
        return max_ttl

    if now is None:
        now = datetime.now(get_market_timezone(exchange))
    elif now.tzinfo is None:
        now = now.replace(tzinfo=pytz.UTC)

    market_tz = get_market_timezone(exchange)
    now = now.astimezone(market_tz)

    market_open, market_close = get_market_hours(exchange)

    # Calculate how far through the trading day we are (0.0 to 1.0)
    open_dt = datetime.combine(now.date(), market_open)
    open_dt = market_tz.localize(open_dt)

    close_dt = datetime.combine(now.date(), market_close)
    close_dt = market_tz.localize(close_dt)

    total_seconds = (close_dt - open_dt).total_seconds()
    elapsed_seconds = (now - open_dt).total_seconds()

    # Progress through the day (0.0 = open, 1.0 = close)
    progress = elapsed_seconds / total_seconds

    # Scale TTL: shorter at open/close (high volatility), longer mid-day
    # Use inverse parabola: ttl is shortest at 0 and 1, longest at 0.5
    volatility_factor = 1 - (4 * (progress - 0.5) ** 2)  # Max 1.0 at midpoint

    ttl = int(min_ttl + (max_ttl - min_ttl) * (1 - volatility_factor))

    return ttl
