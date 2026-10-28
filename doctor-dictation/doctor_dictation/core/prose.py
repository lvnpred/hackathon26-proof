"""Prose sections (plan I2-b): Brief history and Diagnosis are short dictated sentences. Pure: cap the items, and list the
words of an item the dictation never said (information for the doctor; nothing is rewritten)."""
import difflib
import re

PROSE_FIELDS = ("complaints", "diagnosis", "findings")
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


def heard_pool(*transcripts) -> tuple:
    """(heard words, sorted non-numeric pool for speech spellings, negations said) of the dictation, for ``missing_in_pool``."""
    heard = {w for t in transcripts for w in _words(t)}
    pool = sorted(w for w in heard if not w[0].isdigit())
    said_neg = max((sum(w in NEGATION for w in _words(t)) for t in transcripts), default=0)   # "no", "denies"... count alike
    return heard, pool, said_neg


def missing_in_pool(text, pool: tuple, min_word: int = MIN_WORD, frame: frozenset = FRAME) -> list:
    """Words (``min_word``+ letters, not in ``frame``) and numbers of ``text`` not in ``pool`` (from ``heard_pool``); a
    negation beyond the number said is listed too."""
    heard, spellings, said_neg = pool
    missing, neg = [], 0
    for w in _words(text):
        if w in NEGATION:                                  # "vomiting" turned into "no vomiting": more negations than dictated
            neg += 1
            if neg > said_neg and w not in missing:
                missing.append(w)
            continue
        number = w[0].isdigit()
        if w in heard or w in frame or w in missing or (not number and len(w) < min_word):
            continue
        if not number and difflib.get_close_matches(w, spellings, n=1, cutoff=0.8):
            continue                                        # a speech spelling ("chils") of a dictated word
        missing.append(w)
    return missing


def unheard(structured: dict, *transcripts) -> list:
    """[{"field", "index", "words"}]: words (4+ letters, not FRAME) and numbers of each prose item not in the dictation."""
    pool, out = heard_pool(*transcripts), []
    for field in PROSE_FIELDS:
        for i, item in enumerate(_items(structured, field)):
            missing = missing_in_pool(item, pool)
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


_TOKEN_RE = re.compile(r"[a-z]+\d+[a-z\d]*|[a-z]+|\d+(?:\.\d+)?")      # "b12" and "d3" stay one token


def _tokens(text) -> list:
    return _TOKEN_RE.findall(str(text or "").lower())


def heard_words(*transcripts) -> set:
    """The tokens of the dictation (lower case): words, numbers and letter-digit tokens ("b12"). A spoken split form
    ("b 12") also counts as its joined token, and a letter-digit token also counts as its letter and number parts."""
    heard = set()
    for t in transcripts:
        toks = _tokens(t)
        heard.update(toks)
        heard.update(a + b for a, b in zip(toks, toks[1:]) if a.isalpha() and b.isdigit())
        heard.update(p for w in toks if not w.isalpha() and not _is_number(w) for p in re.findall(r"[a-z]+|\d+", w))
    return heard


def _is_number(w) -> bool:
    return w[0].isdigit()


def missing_words(text, *transcripts, min_len: int = 3) -> list:
    """The tokens of ``text`` the dictation never said. A letter-digit token ("b12") or a number must be heard exactly
    (lower case; "b 12" counts for "b12"). A letter word of ``min_len`` or more may be a close speech spelling
    ("aceclofenak"), as in ``unheard``; a shorter one is not checked."""
    heard = heard_words(*transcripts)
    pool, out = sorted(w for w in heard if w.isalpha()), []
    for w in _tokens(text):
        if w in heard or w in out:
            continue
        if w.isalpha() and (len(w) < min_len or difflib.get_close_matches(w, pool, n=1, cutoff=0.8)):
            continue
        out.append(w)
    return out
