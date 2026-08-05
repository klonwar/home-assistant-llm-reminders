from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest

_HELPERS_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "llm_reminders"
    / "helpers.py"
)
_HELPERS_SPEC = importlib.util.spec_from_file_location("llm_reminders_helpers", _HELPERS_PATH)
assert _HELPERS_SPEC and _HELPERS_SPEC.loader
_HELPERS_MODULE = importlib.util.module_from_spec(_HELPERS_SPEC)
_HELPERS_SPEC.loader.exec_module(_HELPERS_MODULE)

normalize_message = _HELPERS_MODULE.normalize_message
parse_iso_datetime = _HELPERS_MODULE.parse_iso_datetime


def test_parse_iso_datetime_requires_timezone() -> None:
    value = parse_iso_datetime("2026-08-01T19:00:00+03:00")

    assert value.utcoffset().total_seconds() == 3 * 60 * 60


def test_parse_iso_datetime_accepts_zulu_suffix() -> None:
    value = parse_iso_datetime("2026-08-01T16:00:00Z")

    assert value == datetime(2026, 8, 1, 16, tzinfo=timezone.utc)


def test_parse_iso_datetime_rejects_naive_value() -> None:
    with pytest.raises(ValueError):
        parse_iso_datetime("2026-08-01T19:00:00")


def test_parse_iso_datetime_rejects_date_only_value() -> None:
    with pytest.raises(ValueError):
        parse_iso_datetime(
            "2026-08-01",
            local_timezone=timezone(timedelta(hours=3)),
        )


def test_parse_iso_datetime_localizes_naive_value() -> None:
    local_timezone = timezone(timedelta(hours=3))

    value = parse_iso_datetime(
        "2026-08-01T19:00:00",
        local_timezone=local_timezone,
    )

    assert value == datetime(2026, 8, 1, 19, tzinfo=local_timezone)


def test_parse_iso_datetime_preserves_explicit_offset() -> None:
    local_timezone = timezone(timedelta(hours=3))

    value = parse_iso_datetime(
        "2026-08-01T19:00:00+05:00",
        local_timezone=local_timezone,
    )

    assert value.utcoffset() == timedelta(hours=5)


def test_normalize_message_collapses_whitespace() -> None:
    assert normalize_message("  купить   хлеб ", 100) == "купить хлеб"


def test_normalize_message_rejects_empty_text() -> None:
    with pytest.raises(ValueError):
        normalize_message("  ", 100)
