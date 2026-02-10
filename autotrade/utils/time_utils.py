"""Timezone-aware datetime utilities for consistent time handling."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Standard timezones
UTC = timezone.utc
US_EASTERN = ZoneInfo("America/New_York")


def now_utc() -> datetime:
    """Get current time in UTC with timezone awareness.

    Returns:
        Timezone-aware datetime in UTC
    """
    return datetime.now(UTC)


def now_eastern() -> datetime:
    """Get current time in US Eastern timezone.

    Returns:
        Timezone-aware datetime in US Eastern time
    """
    return datetime.now(US_EASTERN)


def to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC.

    Args:
        dt: Datetime to convert (can be naive or aware)

    Returns:
        Timezone-aware datetime in UTC
    """
    if dt.tzinfo is None:
        # Assume naive datetime is in local time, convert to UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(UTC)


def to_eastern(dt: datetime) -> datetime:
    """Convert datetime to US Eastern timezone.

    Args:
        dt: Datetime to convert (can be naive or aware)

    Returns:
        Timezone-aware datetime in US Eastern time
    """
    if dt.tzinfo is None:
        # Assume naive datetime is in UTC
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(US_EASTERN)


def ensure_timezone(dt: datetime, tz: timezone | ZoneInfo = UTC) -> datetime:
    """Ensure datetime has timezone information.

    Args:
        dt: Datetime that may or may not have timezone
        tz: Timezone to assume for naive datetimes (default: UTC)

    Returns:
        Timezone-aware datetime
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt


def format_timestamp(dt: datetime, *, include_tz: bool = True) -> str:
    """Format datetime for logging/display.

    Args:
        dt: Datetime to format
        include_tz: Whether to include timezone in output

    Returns:
        Formatted timestamp string
    """
    dt = ensure_timezone(dt)
    if include_tz:
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    return dt.strftime("%Y-%m-%d %H:%M:%S")
