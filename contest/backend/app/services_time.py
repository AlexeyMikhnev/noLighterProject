from datetime import datetime, timezone


def utcnow() -> datetime:
    """Наивное UTC-время: так его хранит SQLite, и так проще сравнивать."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None
