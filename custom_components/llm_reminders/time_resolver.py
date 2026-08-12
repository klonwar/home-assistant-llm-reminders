"""Resolve structured natural-language time values without an LLM clock."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal, InvalidOperation
import calendar
import re
from typing import Any

from .helpers import parse_iso_datetime

_DAY_MICROSECONDS = 24 * 60 * 60 * 1_000_000
_CLOCK_PATTERN = re.compile(r"^(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d)$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INTEGER_PATTERN = re.compile(r"^[0-9]+$")

_RELATIVE_UNIT_MICROSECONDS = {
    "second": Decimal(1_000_000),
    "minute": Decimal(60 * 1_000_000),
    "hour": Decimal(60 * 60 * 1_000_000),
    "day": Decimal(_DAY_MICROSECONDS),
    "week": Decimal(7 * _DAY_MICROSECONDS),
}
_DAY_PERIOD_TIMES = {
    "morning": (9, 0),
    "day": (13, 0),
    "evening": (19, 0),
}
_WEEKDAY_NUMBERS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_CALENDAR_TIME_FIELDS = frozenset(
    {"local_time", "day_period", "hour", "meridiem"}
)
_CALENDAR_REFERENCE_FIELDS = {
    "today": frozenset(),
    "tomorrow": frozenset(),
    "day_after_tomorrow": frozenset(),
    "weekday": frozenset({"weekday", "occurrence"}),
    "next_weekday": frozenset({"weekday", "occurrence"}),
    "day_of_month": frozenset({"day_of_month", "month_ref"}),
    "month_day": frozenset({"month", "day_of_month", "year_ref"}),
    "explicit": frozenset({"date_value"}),
    "nearest_future": frozenset(),
}
_RELATIVE_FORBIDDEN_FIELDS = frozenset(
    {
        "date_ref",
        "occurrence",
        "weekday",
        "month_ref",
        "month",
        "year_ref",
        "day_of_month",
        "date_value",
        "local_time",
        "day_period",
        "hour",
        "meridiem",
    }
)


def resolve_when(
    when: Mapping[str, Any],
    now: datetime,
    local_timezone: tzinfo,
) -> datetime:
    """Resolve a structured ``when`` value using the Home Assistant clock."""
    if not isinstance(when, Mapping):
        raise ValueError("The reminder time must be a structured object")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("The current time must include a timezone")

    kind = _required_text(when, "kind")
    if kind == "relative":
        return _resolve_relative(when, now, local_timezone)
    if kind == "calendar":
        return _resolve_calendar(when, now, local_timezone)
    raise ValueError("The reminder time kind must be relative or calendar")


def _resolve_relative(
    when: Mapping[str, Any],
    now: datetime,
    local_timezone: tzinfo,
) -> datetime:
    _reject_fields(
        when,
        _RELATIVE_FORBIDDEN_FIELDS,
        "A relative reminder cannot include calendar fields",
    )
    duration = when.get("duration")
    if not isinstance(duration, list) or not duration:
        raise ValueError("A relative reminder requires a duration")

    total_microseconds = Decimal(0)
    for component in duration:
        if not isinstance(component, Mapping):
            raise ValueError("Each duration component must be an object")
        value = _positive_decimal(component.get("value"), "duration value")
        unit = _text(component.get("unit"))
        if unit not in _RELATIVE_UNIT_MICROSECONDS:
            raise ValueError(
                "The duration unit must be second, minute, hour, day, or week"
            )
        total_microseconds += value * _RELATIVE_UNIT_MICROSECONDS[unit]

    if total_microseconds <= 0:
        raise ValueError("The relative duration must be positive")
    integral_microseconds = total_microseconds.to_integral_value()
    if total_microseconds != integral_microseconds:
        raise ValueError("The relative duration is more precise than a microsecond")

    try:
        delta = timedelta(microseconds=int(integral_microseconds))
    except (OverflowError, ValueError) as err:
        raise ValueError("The relative duration is too large") from err

    target_time = when.get("target_time")
    if target_time is None:
        return (now.astimezone(timezone.utc) + delta).astimezone(local_timezone)

    if integral_microseconds % _DAY_MICROSECONDS:
        raise ValueError("target_time requires a whole number of days or weeks")
    hour, minute = _parse_clock(target_time)
    local_now = now.astimezone(local_timezone)
    target_date = local_now.date() + timedelta(
        days=int(integral_microseconds // _DAY_MICROSECONDS)
    )
    return _make_local_datetime(target_date, hour, minute, local_timezone)


def _resolve_calendar(
    when: Mapping[str, Any],
    now: datetime,
    local_timezone: tzinfo,
) -> datetime:
    _reject_fields(
        when,
        {"duration", "target_time"},
        "A calendar reminder cannot include relative fields",
    )
    local_now = now.astimezone(local_timezone)
    date_ref = _required_text(when, "date_ref")
    _validate_calendar_reference_fields(when, date_ref)
    times = _parse_calendar_times(when)

    if date_ref == "today":
        return _select_future(
            [local_now.date()], times, now, local_timezone, explicit=True
        )
    if date_ref == "tomorrow":
        return _select_future(
            [local_now.date() + timedelta(days=1)],
            times,
            now,
            local_timezone,
        )
    if date_ref == "day_after_tomorrow":
        return _select_future(
            [local_now.date() + timedelta(days=2)],
            times,
            now,
            local_timezone,
        )
    if date_ref in {"weekday", "next_weekday"}:
        return _resolve_weekday(when, local_now, now, local_timezone, times, date_ref)
    if date_ref == "day_of_month":
        return _resolve_day_of_month(when, local_now, now, local_timezone, times)
    if date_ref == "month_day":
        return _resolve_month_day(when, local_now, now, local_timezone, times)
    if date_ref == "explicit":
        date_value = _required_text(when, "date_value")
        target_date = _parse_date(date_value)
        return _select_future(
            [target_date], times, now, local_timezone, explicit=True
        )
    if date_ref == "nearest_future":
        return _select_future(
            [local_now.date(), local_now.date() + timedelta(days=1)],
            times,
            now,
            local_timezone,
        )
    raise ValueError("The calendar date_ref is not supported")


def _resolve_weekday(
    when: Mapping[str, Any],
    local_now: datetime,
    now: datetime,
    local_timezone: tzinfo,
    times: list[tuple[int, int]],
    date_ref: str,
) -> datetime:
    weekday_name = _required_text(when, "weekday")
    if weekday_name not in _WEEKDAY_NUMBERS:
        raise ValueError("The weekday is not supported")
    occurrence = _text(when.get("occurrence"))
    if occurrence not in ("", "nearest_future", "next"):
        raise ValueError("The weekday occurrence is not supported")
    target_weekday = _WEEKDAY_NUMBERS[weekday_name]
    current_weekday = local_now.date().weekday()
    days_ahead = (target_weekday - current_weekday) % 7
    if date_ref == "next_weekday" or occurrence == "next":
        days_ahead = days_ahead or 7

    first_date = local_now.date() + timedelta(days=days_ahead)
    return _select_future(
        [first_date, first_date + timedelta(days=7)],
        times,
        now,
        local_timezone,
    )


def _resolve_day_of_month(
    when: Mapping[str, Any],
    local_now: datetime,
    now: datetime,
    local_timezone: tzinfo,
    times: list[tuple[int, int]],
) -> datetime:
    day = _positive_integer(when.get("day_of_month"), "day_of_month")
    month_ref = _text(when.get("month_ref")) or "nearest_future"
    if month_ref != "nearest_future":
        raise ValueError("The month_ref must be nearest_future")

    candidates: list[date] = []
    year = local_now.year
    month = local_now.month
    for _ in range(120):
        if day <= calendar.monthrange(year, month)[1]:
            candidates.append(date(year, month, day))
        year, month = _next_month(year, month)
    return _select_future(candidates, times, now, local_timezone)


def _resolve_month_day(
    when: Mapping[str, Any],
    local_now: datetime,
    now: datetime,
    local_timezone: tzinfo,
    times: list[tuple[int, int]],
) -> datetime:
    month = _positive_integer(when.get("month"), "month")
    day = _positive_integer(when.get("day_of_month"), "day_of_month")
    if month > 12:
        raise ValueError("The month must be between 1 and 12")
    year_ref = _text(when.get("year_ref")) or "nearest_future"
    if year_ref != "nearest_future":
        raise ValueError("The year_ref must be nearest_future")

    candidates: list[date] = []
    for year in (local_now.year, local_now.year + 1):
        if day <= calendar.monthrange(year, month)[1]:
            candidates.append(date(year, month, day))
    if not candidates:
        raise ValueError("The month and day do not form a valid date")
    return _select_future(candidates, times, now, local_timezone)


def _parse_calendar_times(when: Mapping[str, Any]) -> list[tuple[int, int]]:
    local_time = when.get("local_time")
    day_period = when.get("day_period")
    hour = when.get("hour")
    meridiem = _text(when.get("meridiem")) or "unspecified"
    populated = sum(value is not None for value in (local_time, day_period, hour))
    if populated != 1:
        raise ValueError("Provide exactly one local_time, day_period, or hour")

    if local_time is not None:
        if when.get("meridiem") is not None:
            raise ValueError("meridiem cannot be combined with local_time")
        return [_parse_clock(local_time)]
    if day_period is not None:
        if when.get("meridiem") is not None:
            raise ValueError("meridiem cannot be combined with day_period")
        try:
            return [_DAY_PERIOD_TIMES[_text(day_period)]]
        except KeyError as err:
            raise ValueError("The day_period is not supported") from err

    hour_value = _nonnegative_integer(hour, "hour")
    if meridiem not in {"am", "pm", "unspecified"}:
        raise ValueError("meridiem must be am, pm, or unspecified")
    if meridiem == "am":
        if hour_value < 1 or hour_value > 12:
            raise ValueError("An AM hour must be between 1 and 12")
        return [(hour_value % 12, 0)]
    if meridiem == "pm":
        if hour_value < 1 or hour_value > 12:
            raise ValueError("A PM hour must be between 1 and 12")
        return [((hour_value % 12) + 12, 0)]
    if hour_value == 8:
        return [(8, 0), (20, 0)]
    if hour_value == 0 or hour_value > 12:
        if hour_value > 23:
            raise ValueError("The hour must be between 0 and 23")
        return [(hour_value, 0)]
    raise ValueError("The hour is ambiguous; provide meridiem or local_time")


def _select_future(
    dates: list[date],
    times: list[tuple[int, int]],
    now: datetime,
    local_timezone: tzinfo,
    *,
    explicit: bool = False,
) -> datetime:
    candidates = sorted(
        _make_local_datetime(target_date, hour, minute, local_timezone)
        for target_date in dates
        for hour, minute in times
    )
    current = now.astimezone(local_timezone)
    for candidate in candidates:
        if candidate > current:
            return candidate
    if explicit:
        raise ValueError("The reminder time must be in the future")
    raise ValueError("No future occurrence was found for the reminder time")


def _make_local_datetime(
    target_date: date,
    hour: int,
    minute: int,
    local_timezone: tzinfo,
) -> datetime:
    return parse_iso_datetime(
        f"{target_date.isoformat()}T{hour:02d}:{minute:02d}",
        local_timezone=local_timezone,
    )


def _parse_clock(value: object) -> tuple[int, int]:
    text = _text(value)
    match = _CLOCK_PATTERN.fullmatch(text)
    if match is None:
        raise ValueError("local_time and target_time must use HH:MM")
    return int(match.group("hour")), int(match.group("minute"))


def _parse_date(value: object) -> date:
    text = _text(value)
    if _DATE_PATTERN.fullmatch(text) is None:
        raise ValueError("date_value must use YYYY-MM-DD")
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as err:
        raise ValueError("date_value is not a valid date") from err


def _required_text(mapping: Mapping[str, Any], key: str) -> str:
    value = _text(mapping.get(key))
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _text(value: object) -> str:
    return value.strip().casefold() if isinstance(value, str) else ""


def _positive_decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a positive string number")
    try:
        result = Decimal(value.strip())
    except InvalidOperation as err:
        raise ValueError(f"{field} must be a positive string number") from err
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{field} must be a positive string number")
    return result


def _positive_integer(value: object, field: str) -> int:
    text = _text(value)
    if _INTEGER_PATTERN.fullmatch(text) is None:
        raise ValueError(f"{field} must be a positive integer string")
    result = int(text)
    if result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _nonnegative_integer(value: object, field: str) -> int:
    text = _text(value)
    if _INTEGER_PATTERN.fullmatch(text) is None:
        raise ValueError(f"{field} must be a non-negative integer string")
    result = int(text)
    if result < 0:
        raise ValueError(f"{field} must be non-negative")
    return result


def _next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def _validate_calendar_reference_fields(
    when: Mapping[str, Any], date_ref: str
) -> None:
    allowed = _CALENDAR_REFERENCE_FIELDS.get(date_ref)
    if allowed is None:
        raise ValueError("The calendar date_ref is not supported")

    present = set(when) - {"kind", "date_ref"} - _CALENDAR_TIME_FIELDS
    unexpected = sorted(present - allowed)
    if unexpected:
        fields = ", ".join(unexpected)
        raise ValueError(
            f"The calendar date_ref {date_ref} cannot include: {fields}"
        )


def _reject_fields(
    when: Mapping[str, Any], forbidden: set[str] | frozenset[str], message: str
) -> None:
    present = sorted(set(when).intersection(forbidden))
    if present:
        raise ValueError(f"{message}: {', '.join(present)}")
