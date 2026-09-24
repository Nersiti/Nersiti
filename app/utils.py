from __future__ import annotations

import html
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    """Naive UTC datetime — the only kind stored in the database."""
    return datetime.now(UTC).replace(tzinfo=None)


def local_today(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


def local_day_start_utc(tz: ZoneInfo, days_ago: int = 0) -> datetime:
    """Start of the local day (minus ``days_ago``) as naive UTC."""
    day = local_today(tz) - timedelta(days=days_ago)
    return datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC).replace(tzinfo=None)


def fmt_dt(value: datetime | None, tz: ZoneInfo) -> str:
    if value is None:
        return "—"
    return value.replace(tzinfo=UTC).astimezone(tz).strftime("%d.%m.%Y %H:%M")


def from_timestamp(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, UTC).replace(tzinfo=None)


def esc(text: str | None) -> str:
    return html.escape(text or "", quote=False)


def plural(n: int, one: str, few: str, many: str) -> str:
    n_abs = abs(n) % 100
    if 11 <= n_abs <= 19:
        return many
    last = n_abs % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def credits_word(n: int) -> str:
    return f"{n} {plural(n, 'кредит', 'кредита', 'кредитов')}"


_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)


def has_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC.search(text))


_TAG_RE = re.compile(r"[^a-zA-Z0-9_-]")


def sanitize_tag(value: str, max_len: int = 32) -> str:
    return _TAG_RE.sub("", value)[:max_len]
