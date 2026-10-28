"""Detect "known brand + combination suffix" names such as Zerodol-P. Stdlib only."""
import re

from .lexmemo import per_lexicon

COMBO_SUFFIXES = frozenset({
    "a", "p", "d", "sp", "th", "dsr", "gp", "pg", "av", "cv", "xt", "lc", "am", "h", "m", "t",
    "mt", "dm", "ls", "plus", "forte", "mr", "sr", "er", "xr", "cr", "od", "trio",
})

SEP_CHARS = "\\s\\-\u2010-\u2015\u2212"   # whitespace, hyphen, Unicode dashes U+2010-2015 and the minus sign
_COMBO_RE = re.compile(rf"^(?P<base>.+?)[{SEP_CHARS}]+(?P<suffix>[A-Za-z]+)(?:[{SEP_CHARS}]*\d+(?:\.\d+)?)?$")
_canon_slot: dict = {}  # per_lexicon: lexicon list -> lower-cased canonical names


def _canonical_names(lex) -> frozenset:
    return per_lexicon(_canon_slot, lex, lambda: frozenset(e.get("canonical", "").strip().lower() for e in lex))


def combo_suffix(name: str) -> tuple[str, str] | None:
    """(base, suffix) as written when `name` is a known brand plus a combination suffix, else None."""
    from . import determinism as D  # lazy: determinism imports surface, which imports this module
    text = re.sub(r"\s+", " ", (name or "").strip()).rstrip(".").strip()
    lex = D.load_lexicon()
    if not text or D._exact_lookup(text):
        return None
    m = _COMBO_RE.match(text)
    if not m or m.group("suffix").casefold() not in COMBO_SUFFIXES:
        return None
    base = m.group("base")
    low = base.lower()
    if low not in D._alias_map(lex) or low in _canonical_names(lex):
        return None
    return base, m.group("suffix")
