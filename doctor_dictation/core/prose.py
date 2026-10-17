"""Prose sections (plan I2-b): Brief history and Diagnosis are short dictated sentences. Pure: cap the items, and list the
words of an item the dictation never said (information for the doctor; nothing is rewritten)."""
import difflib
import re

PROSE_FIELDS = ("complaints", "diagnosis")
ITEM_CHARS, MIN_WORD = 400, 4
NEGATION = frozenset("no not without denies denied nil absent negative never none".split())
FRAME = frozenset("""about after along also associated before case clinical complaint complaints days diagnosis during episode episodes from history
impression known months noted over patient presented presents reports similar since than that there this under week weeks which with years year month
day""".split())                       # framing words a summary adds without new facts


def _words(text):
    return re.findall(r"[a-z]+|\d+(?:\.\d+)?", str(text or "").lower())


def _items(structured, field):
    v = structured.get(field) if isinstance(structured, dict) else None
    return v if isinstance(v, list) else []


def unheard(structured: dict, *transcripts) -> list:
    """[{"field", "index", "words"}]: words (4+ letters, not FRAME) and numbers of each prose item not in the dictation."""
    heard = {w for t in transcripts for w in _words(t)}
    pool, out = sorted(w for w in heard if not w[0].isdigit()), []
    said_neg = max((sum(w in NEGATION for w in _words(t)) for t in transcripts), default=0)   # "no", "denies"... count alike
    for field in PROSE_FIELDS:
        for i, item in enumerate(_items(structured, field)):
            missing, neg = [], 0
            for w in _words(item):
                if w in NEGATION:                                  # "vomiting" turned into "no vomiting": more negations than dictated
                    neg += 1
                    if neg > said_neg and w not in missing:
                        missing.append(w)
                    continue
                number = w[0].isdigit()
                if w in heard or w in FRAME or w in missing or (not number and len(w) < MIN_WORD):
                    continue
                if not number and difflib.get_close_matches(w, pool, n=1, cutoff=0.8):
                    continue                                        # a speech spelling ("chils") of a dictated word
                missing.append(w)
            if missing:
                out.append({"field": field, "index": i, "words": missing})
    return out


def cap_items(structured: dict) -> list:
    """Cut each prose item over ITEM_CHARS at a word (mutates); returns one warning per cut item."""
    warnings = []
    for field in PROSE_FIELDS:
        items = _items(structured, field)
        for i, item in enumerate(items):
            text = str(item)
            items[i] = text
            if len(text) > ITEM_CHARS:
                items[i] = text[:ITEM_CHARS].rsplit(" ", 1)[0].rstrip(" ,;") + "\u2026"
                warnings.append(f"{field}[{i}]: shortened from {len(text)} to {len(items[i])} characters")
    return warnings
