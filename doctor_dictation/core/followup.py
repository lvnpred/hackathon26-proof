"""The follow-up date from the review line (plan I2-b). Pure; the visit day is passed in. One clear duration gives a date;
anything unclear gives "": no duration, a range, two different durations, a duration counted from an event, over LIMITS."""
import calendar
import re
from datetime import date, timedelta

MAX_REVIEW_CHARS = 200
LIMITS = {"day": 366, "week": 52, "month": 24, "year": 5}
_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
        "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
        "chhe": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10, "pandrah": 15}
_UNIT = {"day": "day", "days": "day", "din": "day", "week": "week", "weeks": "week", "wk": "week", "wks": "week", "hafta": "week", "hafte": "week",
         "haftey": "week", "month": "month", "months": "month", "mahina": "month", "mahine": "month", "year": "year", "years": "year", "yr": "year",
         "yrs": "year", "saal": "year"}
_ONE = {"next week": (1, "week"), "next month": (1, "month"), "next year": (1, "year"), "fortnight": (2, "week"), "tomorrow": (1, "day")}
_alt = lambda words: "|".join(sorted(map(re.escape, words), key=len, reverse=True))   # noqa: E731
_N, _U = rf"(\d{{1,3}}(?!\d)|{_alt(_NUM)})", f"({_alt(_UNIT)})"
_DUR = re.compile(rf"\b{_N}\s*-?\s*{_U}\b")
_RANGE = re.compile(rf"\b{_N}\s*(?:[-\u2013\u2014,/]|to|or)?\s*{_N}\s*{_U}\b")   # 3-4, 3\u20134, 3 4, 1,2, 1 to 2
_WEEKDAYS = "mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?"
# Anything that is not ONE plain, unconditional review interval gets no date. Checked on the lower-cased line BEFORE parsing.
_REFUSE = [re.compile(p) for p in (
    r"day after tomorrow",                                    # two days, not the +1 that "tomorrow" gives
    r"\d\s*[.,]\s*\d|\bhalf\b|\band a half\b",                             # 1.5 months, half a month: no fractions
    r"\d\s*/\s*\d",                                                       # 1/52, 25/10: a fraction or an explicit date
    r"\b(?:once|twice|thrice|every|each|per|times?)\b|\b(?:weekly|daily|monthly|yearly|fortnightly)\b",   # a frequency, not a date
    r"\b(?:no|not|never|nahi|nahin|without|dont|don't|nil|stop)\b",         # a negation: no review, or none needed
    r"\bfor\s+(?:\d{1,3}|" + _alt(_NUM) + r")\s*" + _U + r"\b|\bthen\b|\bcourse\b|\bcontinue\b|\bcomplet\w*",   # a treatment duration
    r"\brepeat\b[^,.;]*?\b(?:after|in|at)\s+" + _N + r"\s*" + _U + r"\b",   # a repeat test's interval; "in 2 weeks with repeat USG" stays
    r"(?<![\w.])[-\u2212\u2013]\s*\d",                                         # a dropped sign: -1 week
    r"\b(?:if|unless|incase|when|only|else|earlier|sos|prn|persist\w*|worse|needed|required|within|maximum|max|upto|up to)\b",   # a condition or open end
    r"\bnext\s+(?:\d{1,3}|" + _alt(_NUM) + r")\b|\b(?:" + _WEEKDAYS + r")\b",   # "next 2 weeks"; a weekday the label could contradict
)]
_EVENT = re.compile(rf"\b{_N}\s*-?\s*{_U}\s+(?:after|before|post|of|from)\b")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

def parse(text):
    """(n, "day" | "week" | "month" | "year") for the ONE duration the review line states, else None."""
    t = " ".join(str(text or "").lower().split())
    if not t or len(t) > MAX_REVIEW_CHARS or any(r.search(t) for r in _REFUSE) or _RANGE.search(t) or _EVENT.search(t):
        return None
    found = {(int(n) if n.isdigit() else _NUM[n], _UNIT[u]) for n, u in _DUR.findall(t)}
    found |= {v for k, v in _ONE.items() if re.search(rf"\b{k}\b", t)}
    if len(found) != 1:
        return None
    n, unit = found.pop()
    return (n, unit) if 0 < n <= LIMITS[unit] else None

def add(visit: date, n: int, unit: str) -> date:
    """visit + n units; a month or a year that lands past the month's end is clamped to its last day."""
    if unit in ("day", "week"):
        return visit + timedelta(days=n * (7 if unit == "week" else 1))
    y, m = divmod(visit.month - 1 + n * (12 if unit == "year" else 1), 12)
    year, month = visit.year + y, m + 1
    return date(year, month, min(visit.day, calendar.monthrange(year, month)[1]))


def review_date(text, visit) -> str:
    """ISO date of the visit plus the one duration the review line states; "" when unclear or no visit day."""
    got = parse(text)
    if not got or not isinstance(visit, date):
        return ""
    try:
        return add(visit, *got).isoformat()
    except (OverflowError, ValueError):   # a visit day at the end of the calendar: no date, never an error
        return ""


def date_label(iso) -> str:
    """Fixed-English label for an ISO date ("Sat 24 Oct 2026"); not the server locale. "" for anything else."""
    try:
        d = date.fromisoformat(str(iso or ""))
    except ValueError:
        return ""
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"


def stamp(structured: dict, visit) -> dict:
    """Set structured["review_date"] from its review line (replacing any client value) and return it."""
    structured["review_date"] = review_date(structured.get("review"), visit)
    return structured
