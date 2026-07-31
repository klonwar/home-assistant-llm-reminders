from __future__ import annotations

from datetime import datetime


def parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO-8601 datetime and require timezone information."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A non-empty ISO-8601 datetime is required")

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    result = datetime.fromisoformat(normalized)
    if result.tzinfo is None:
        raise ValueError("The datetime must include a timezone offset")
    return result


def normalize_message(value: str, max_length: int) -> str:
    """Normalize user text without rewriting its meaning."""
    if not isinstance(value, str):
        raise ValueError("The reminder message must be text")

    result = " ".join(value.split())
    if not result:
        raise ValueError("The reminder message must not be empty")
    if len(result) > max_length:
        raise ValueError(f"The reminder message must be {max_length} characters or shorter")
    return result
