"""Strict UTC datetime boundary for durable Session and approval authority."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator

_RAW_UTC6 = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}")


class UTC6DateTime(TypeDecorator[datetime]):
    """Normalize aware inputs to UTC and restore UTC awareness after SQLite load."""

    impl = DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=True)

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authority timestamps require an aware datetime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def aware_utc(value: datetime) -> datetime:
    """Normalize a Clock observation to the authority layer's aware UTC form."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def raw_utc6(value: datetime) -> str:
    """Return the authoritative fixed-width SQLite UTC6 representation."""
    return aware_utc(value).strftime("%Y-%m-%d %H:%M:%S.%f")


def parse_raw_utc6(value: object) -> datetime:
    """Validate and parse the exact SQLite authority representation."""
    if not isinstance(value, str) or _RAW_UTC6.fullmatch(value) is None:
        raise ValueError("authority clock must return exact UTC6 text")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError("authority clock must return a valid UTC6 instant") from exc
    if raw_utc6(parsed) != value:
        raise ValueError("authority clock must return canonical UTC6 text")
    return parsed
