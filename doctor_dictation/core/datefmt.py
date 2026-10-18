"""Date and time text for the page and the printed sheet (iteration 3). Pure: no I/O, no clock, no zone data.

One setting, DATE_LOCALE, picks the tables. The page has the same tables in frontend/dates.js; both are tested against
tests/data/date_formats.json, so screen and print cannot drift. Text is assembled from our own tables, never from the
host's locale data, so it is identical on every machine. Invalid input gives "".
"""
import logging
import re
from datetime import date, datetime

log = logging.getLogger(__name__)

DEFAULT_LOCALE = "en-IN"
# Per locale: month words, weekday words (Monday first), the am/pm words. en-IN: "17 Oct 2026", "Sat 24 Oct 2026", "3:05 pm".
TABLES = {
    "en-IN": {
        "months": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        "days": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
        "am": "am", "pm": "pm",
    },
}
SUPPORTED = tuple(TABLES)
_ISO = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})\Z")   # ASCII digits only; no trailing newline (same rule as dates.js)
_warned: set = set()


def resolve_locale(name) -> str:
    """The supported locale for a setting value. Blank gives the default quietly; an unknown value gives the default
    and ONE logged warning per value, never an error."""
    value = str(name or "").strip()
    if not value:
        return DEFAULT_LOCALE
    if value in TABLES:
        return value
    if value not in _warned:
        _warned.add(value)
        log.warning("DATE_LOCALE %r is not supported (supported: %s); using %s", value, ", ".join(SUPPORTED), DEFAULT_LOCALE)
    return DEFAULT_LOCALE


def _table(locale):
    return TABLES[resolve_locale(locale)]


def _as_date(value):
    """A date from a date, a datetime, or a strict YYYY-MM-DD string; None for anything else, and for a year before 1000
    (one rule with dates.js: Date.UTC maps years 0-99 to 1900-1999)."""
    d = _date_of(value)
    return d if d is not None and d.year >= 1000 else None


def _date_of(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    m = _ISO.match(value) if isinstance(value, str) else None
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def format_date(value, locale=DEFAULT_LOCALE) -> str:
    """"17 Oct 2026"."""
    d = _as_date(value)
    return "" if d is None else f"{d.day} {_table(locale)['months'][d.month - 1]} {d.year}"


def format_label(value, locale=DEFAULT_LOCALE) -> str:
    """The date with its weekday: "Sat 24 Oct 2026"."""
    d = _as_date(value)
    return "" if d is None else f"{_table(locale)['days'][d.weekday()]} {format_date(d, locale)}"


def format_time(dt, locale=DEFAULT_LOCALE) -> str:
    """The wall-clock time of ``dt`` as given (convert to the clinic zone first): "3:05 pm"."""
    if not isinstance(dt, datetime):
        return ""
    t = _table(locale)
    return f"{dt.hour % 12 or 12}:{dt.minute:02d} {t['pm'] if dt.hour >= 12 else t['am']}"


def format_datetime(dt, locale=DEFAULT_LOCALE) -> str:
    """"17 Oct 2026, 3:05 pm"."""
    if not isinstance(dt, datetime):
        return ""
    return f"{format_date(dt, locale)}, {format_time(dt, locale)}"
