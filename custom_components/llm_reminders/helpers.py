from __future__ import annotations

from datetime import datetime, timezone, tzinfo


def parse_iso_datetime(
    value: str,
    local_timezone: tzinfo | None = None,
) -> datetime:
    """Parse an ISO-8601 datetime, optionally localizing naive values."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A non-empty ISO-8601 datetime is required")

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    if not any(separator in normalized for separator in ("T", "t", " ")):
        raise ValueError("The datetime must include a time")

    result = datetime.fromisoformat(normalized)
    if result.tzinfo is not None:
        return result

    if local_timezone is None:
        raise ValueError("The datetime must include a timezone offset")

    candidates = [
        result.replace(tzinfo=local_timezone, fold=fold)
        for fold in (0, 1)
    ]
    valid_candidates = [
        candidate
        for candidate in candidates
        if candidate.astimezone(timezone.utc)
        .astimezone(local_timezone)
        .replace(tzinfo=None)
        == result
    ]
    if not valid_candidates:
        raise ValueError(
            "The datetime does not exist in the configured timezone"
        )
    if len(valid_candidates) == 2 and (
        valid_candidates[0].utcoffset() != valid_candidates[1].utcoffset()
    ):
        raise ValueError("The datetime is ambiguous in the configured timezone")

    return valid_candidates[0]


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
