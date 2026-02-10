"""Market hours validation utilities for US stock markets."""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

# US stock market timezone
US_EASTERN = ZoneInfo("America/New_York")

# Regular trading hours (9:30 AM - 4:00 PM ET)
MARKET_OPEN_TIME = time(9, 30)
MARKET_CLOSE_TIME = time(16, 0)

# Pre-market hours (4:00 AM - 9:30 AM ET)
PREMARKET_OPEN_TIME = time(4, 0)

# After-hours trading (4:00 PM - 8:00 PM ET)
AFTERHOURS_CLOSE_TIME = time(20, 0)

# Market holidays (2026) - update annually
MARKET_HOLIDAYS_2026 = {
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # MLK Jr. Day
    "2026-02-16",  # Presidents Day
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-07-03",  # Independence Day (observed)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
}


def is_market_holiday(dt: datetime | None = None) -> bool:
    """Check if the given date is a market holiday.

    Args:
        dt: Datetime to check (defaults to now in US Eastern time)

    Returns:
        True if the date is a market holiday
    """
    if dt is None:
        dt = datetime.now(US_EASTERN)
    elif dt.tzinfo is None:
        # Convert naive datetime to US Eastern
        dt = dt.replace(tzinfo=US_EASTERN)
    else:
        # Convert to US Eastern
        dt = dt.astimezone(US_EASTERN)

    date_str = dt.strftime("%Y-%m-%d")
    return date_str in MARKET_HOLIDAYS_2026


def is_weekend(dt: datetime | None = None) -> bool:
    """Check if the given date is a weekend (Saturday or Sunday).

    Args:
        dt: Datetime to check (defaults to now in US Eastern time)

    Returns:
        True if the date is a weekend
    """
    if dt is None:
        dt = datetime.now(US_EASTERN)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=US_EASTERN)
    else:
        dt = dt.astimezone(US_EASTERN)

    return dt.weekday() >= 5  # 5=Saturday, 6=Sunday


def is_regular_market_hours(dt: datetime | None = None) -> bool:
    """Check if the given time is during regular trading hours (9:30 AM - 4:00 PM ET).

    Args:
        dt: Datetime to check (defaults to now in US Eastern time)

    Returns:
        True if within regular market hours
    """
    if dt is None:
        dt = datetime.now(US_EASTERN)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=US_EASTERN)
    else:
        dt = dt.astimezone(US_EASTERN)

    if is_weekend(dt) or is_market_holiday(dt):
        return False

    current_time = dt.time()
    return MARKET_OPEN_TIME <= current_time < MARKET_CLOSE_TIME


def is_extended_hours(dt: datetime | None = None) -> bool:
    """Check if the given time is during extended hours (pre-market or after-hours).

    Pre-market: 4:00 AM - 9:30 AM ET
    After-hours: 4:00 PM - 8:00 PM ET

    Args:
        dt: Datetime to check (defaults to now in US Eastern time)

    Returns:
        True if within extended trading hours
    """
    if dt is None:
        dt = datetime.now(US_EASTERN)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=US_EASTERN)
    else:
        dt = dt.astimezone(US_EASTERN)

    if is_weekend(dt) or is_market_holiday(dt):
        return False

    current_time = dt.time()

    # Pre-market hours
    if PREMARKET_OPEN_TIME <= current_time < MARKET_OPEN_TIME:
        return True

    # After-hours
    if MARKET_CLOSE_TIME <= current_time < AFTERHOURS_CLOSE_TIME:
        return True

    return False


def is_market_open(dt: datetime | None = None, *, allow_extended_hours: bool = False) -> bool:
    """Check if the market is currently open for trading.

    Args:
        dt: Datetime to check (defaults to now in US Eastern time)
        allow_extended_hours: If True, returns True during pre-market and after-hours

    Returns:
        True if the market is open for trading
    """
    if is_regular_market_hours(dt):
        return True

    if allow_extended_hours and is_extended_hours(dt):
        return True

    return False


def next_market_open() -> datetime:
    """Calculate the next market open time.

    Returns:
        Datetime of the next market open (9:30 AM ET)
    """
    now = datetime.now(US_EASTERN)
    current_date = now.date()
    current_time = now.time()

    # If before market open today and not weekend/holiday, return today
    if current_time < MARKET_OPEN_TIME and not is_weekend(now) and not is_market_holiday(now):
        return datetime.combine(current_date, MARKET_OPEN_TIME, tzinfo=US_EASTERN)

    # Otherwise find next business day
    from datetime import timedelta

    next_day = now + timedelta(days=1)
    for _ in range(10):  # Check up to 10 days ahead
        next_day_dt = datetime.combine(next_day.date(), MARKET_OPEN_TIME, tzinfo=US_EASTERN)
        if not is_weekend(next_day_dt) and not is_market_holiday(next_day_dt):
            return next_day_dt
        next_day += timedelta(days=1)

    # Fallback: return tomorrow at market open
    return datetime.combine(
        (now + timedelta(days=1)).date(),
        MARKET_OPEN_TIME,
        tzinfo=US_EASTERN,
    )


def time_until_market_open() -> float:
    """Calculate seconds until the next market open.

    Returns:
        Number of seconds until market opens (0 if already open)
    """
    if is_market_open():
        return 0.0

    now = datetime.now(US_EASTERN)
    next_open = next_market_open()
    delta = next_open - now
    return delta.total_seconds()


def get_market_status() -> dict[str, any]:
    """Get comprehensive market status information.

    Returns:
        Dict with market status details:
        - is_open: bool, whether market is currently open
        - is_regular_hours: bool, whether it's regular trading hours
        - is_extended_hours: bool, whether it's extended hours
        - is_weekend: bool, whether it's a weekend
        - is_holiday: bool, whether it's a market holiday
        - next_open: datetime, next market open time
        - seconds_until_open: float, seconds until next open
    """
    now = datetime.now(US_EASTERN)

    return {
        "is_open": is_market_open(now),
        "is_regular_hours": is_regular_market_hours(now),
        "is_extended_hours": is_extended_hours(now),
        "is_weekend": is_weekend(now),
        "is_holiday": is_market_holiday(now),
        "next_open": next_market_open(),
        "seconds_until_open": time_until_market_open(),
        "current_time_et": now,
    }
