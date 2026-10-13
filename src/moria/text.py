"""Small, deterministic helpers for normalisation: dates in the sources' many formats, canonical URLs, and plain text.

Dates: every moment becomes a timezone-aware UTC datetime. A date or a time without a zone is read as UTC (the Federal
Register of Legislation's register times carry no zone; this is stated in its census). Unparseable values give None,
and the caller counts them.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_FRACTION = re.compile(r"(\.\d{6})\d+")  # FRL writes seven fractional digits; Python reads at most six
_COMPACT = (("%Y%m%dT%H%M%SZ", 16), ("%Y%m%d%H%M%S", 14), ("%Y%m%d", 8))
_YEAR = re.compile(r"^\d{4}$")
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_QUARTER = re.compile(r"^(\d{4})-?Q([1-4])$")
_SEMESTER = re.compile(r"^(\d{4})-S([12])$")


def parse_moment(value: object) -> datetime | None:
    """A UTC datetime from an ISO 8601 string (with or without a zone or time), an RFC 2822 date (feeds), a compact
    GDELT stamp, a bare year, or a date or datetime object."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    if _YEAR.match(text):
        return datetime(int(text), 1, 1, tzinfo=UTC)
    for fmt, n in _COMPACT:
        if len(text) == n and text[:8].isdigit():
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=UTC)
            except ValueError:
                pass
    iso = _FRACTION.sub(r"\1", text.replace("Z", "+00:00") if text.endswith("Z") else text)
    try:
        moment = datetime.fromisoformat(iso)
        return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)
    except ValueError:
        pass
    try:
        moment = parsedate_to_datetime(text)
        return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)
    except (TypeError, ValueError, IndexError):
        return None


def iso(moment: datetime | None) -> str | None:
    return moment.astimezone(UTC).isoformat(timespec="seconds") if moment else None


def period_start(period: str) -> tuple[str, date | None]:
    """A statistical period's kind and first day: 2024 (year), 2024-03 (month), 2024-Q1 (quarter), 2024-S2 (half),
    2024-03-31 (day). Financial years and other wordings are kept as published, with no start date."""
    p = period.strip()
    if _YEAR.match(p):
        return "year", date(int(p), 1, 1)
    if (m := _MONTH.match(p)) and 1 <= int(m[2]) <= 12:
        return "month", date(int(m[1]), int(m[2]), 1)
    if m := _QUARTER.match(p):
        return "quarter", date(int(m[1]), 3 * int(m[2]) - 2, 1)
    if m := _SEMESTER.match(p):
        return "half", date(int(m[1]), 6 * int(m[2]) - 5, 1)
    try:
        return "day", date.fromisoformat(p)
    except ValueError:
        return "other", None


# Query parameters that only track a click, never change the page
_TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|mc_cid|mc_eid|ref|ref_src|cmpid|ocid|at_medium|at_campaign|cid|s_cid)$")


def canonical_url(url: str | None) -> str | None:
    """The URL with what doesn't identify the page removed: scheme, letter case of the host, a leading www. or m.,
    default ports, tracking parameters, the fragment, an AMP suffix and a trailing slash."""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if not parts.netloc:
        return None
    host = (parts.hostname or "").lower()
    for prefix in ("www.", "m.", "amp."):
        if host.startswith(prefix) and host.count(".") > 1:
            host = host[len(prefix) :]
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    path = re.sub(r"/+", "/", parts.path or "/")
    path = re.sub(r"(/amp|\.amp)$", "", path)
    if len(path) > 1:
        path = path.rstrip("/")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                             if not _TRACKING.match(k.lower()) and k.lower() != "amp"))  # fmt: skip
    return urlunsplit(("", host, path, query, "")).lstrip("/")


_TAGS = re.compile(r"<[^>]{0,2000}>")
_SPACE = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def plain_text(value: object) -> str:
    """Text with markup removed (feed summaries can carry HTML), entities decoded and whitespace collapsed."""
    if value is None:
        return ""
    text = str(value)
    if "<" in text and ">" in text:
        text = _TAGS.sub(" ", text)
    if "&" in text:
        text = html.unescape(text)
    return _SPACE.sub(" ", _CONTROL.sub(" ", text)).strip()


def cut(text: str, limit: int) -> str:
    """At most `limit` characters, cut at the last space before the limit when there is one in the last fifth."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    space = head.rfind(" ")
    return head[:space] if space > limit * 0.8 else head


_WORDS = re.compile(r"[^\W_]+")


def title_key(title: str, min_words: int) -> str | None:
    """A title's words in lower case, for exact-title de-duplication; None for titles too short to identify a story."""
    words = _WORDS.findall(title.lower())
    return " ".join(words) if len(words) >= min_words else None
