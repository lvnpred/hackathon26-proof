"""The visit day and the clinic zone, in one place so tests can inject them (plans I2-b and I3).

The zone NAME comes from the TZ environment variable (default Asia/Kolkata). zoneinfo only names it for the page and does
the date maths here; the container clock zone no longer decides the visit day. The OP number (db/opno.py) and the stored
UTC timestamps are not changed by this module.
"""
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from doctor_dictation.config import get_settings
from doctor_dictation.core import datefmt

log = logging.getLogger(__name__)
DEFAULT_ZONE = "Asia/Kolkata"
_warned: set = set()


def zone_name() -> str:
    """The clinic time zone name as set in TZ (a leading ':' is dropped), else Asia/Kolkata."""
    return (os.environ.get("TZ") or "").strip().lstrip(":").strip() or DEFAULT_ZONE


def _zone(name=None):
    """The ZoneInfo for ``name`` (default: the clinic zone); None, logged once, when its data is missing or the name is not a zone."""
    name = name or zone_name()
    try:
        return ZoneInfo(name)
    except (ValueError, OSError, KeyError):          # ZoneInfoNotFoundError is a KeyError
        if name not in _warned:
            _warned.add(name)
            log.warning("time zone %r has no zone data here; using the server's local time for the visit day", name)
        return None


def effective_zone_name() -> str:
    """The zone the server really uses: the TZ name when its data loads, else the host's own zone name (what to_clinic falls back to)."""
    return zone_name() if _zone() is not None else (datetime.now().astimezone().tzname() or "UTC")


def to_clinic(dt: datetime, name=None) -> datetime:
    """``dt`` as wall-clock time in the clinic zone. A naive value is taken as UTC. Missing zone data: the server's local zone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    zone = _zone(name)
    return dt.astimezone(zone) if zone else dt.astimezone()


def today(now=None) -> date:
    """The clinic calendar day: the day the PDF prints on Save (api/persistence.py). ``now`` is an aware instant for tests."""
    return to_clinic(now or datetime.now(timezone.utc)).date()


def day_bounds_utc(day: date) -> tuple[str, str]:
    """UTC bounds ``[start, end)`` of the clinic-zone calendar ``day``, formatted like stored ``created_at`` values
    (``%Y-%m-%dT%H:%M:%SZ``). Missing zone data: the server's local zone, as ``to_clinic``."""
    zone = _zone()

    def midnight(d):
        local = datetime(d.year, d.month, d.day, tzinfo=zone) if zone else datetime(d.year, d.month, d.day).astimezone()
        return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return midnight(day), midnight(day + timedelta(days=1))


_ISO_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def parse_day(text) -> date | None:
    """A strict ``YYYY-MM-DD`` that is a real day, else None (``date.fromisoformat`` alone also takes other forms)."""
    if not isinstance(text, str) or not _ISO_DAY.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def locale() -> str:
    """The app-wide DATE_LOCALE, resolved (unknown values give en-IN with one warning)."""
    return datefmt.resolve_locale(get_settings().date_locale)


def date_text(day) -> str:
    """A day as the sheet header prints it: "17 Oct 2026"."""
    return datefmt.format_date(day, locale())
