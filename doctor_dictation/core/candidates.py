"""Sound-alike candidates for medicine names the lexicon does not know.

Pure and deterministic: stdlib only (re, difflib), no I/O, no randomness.
Candidates are only ever *suggestions* shown to the LLM in the repair message;
nothing here changes a prescription row.
"""
import difflib
import re
from collections import Counter

from .lexmemo import per_lexicon

MIN_SCORE = 0.78
MIN_LEN = 4  # shorter lexicon keys ("pan", "pcm") are too noisy to rank
MAX_NAME_LETTERS = 40  # a longer "name" is not a medicine name; keep difflib work bounded

# Consonant classes that speech recognisers confuse: voiced/unvoiced pairs and
# near-identical sounds share one letter.
_CLASS = {
    "b": "p", "p": "p", "d": "t", "t": "t", "g": "k", "k": "k", "q": "k",
    "v": "f", "f": "f", "z": "s", "s": "s", "j": "j", "m": "m", "n": "n",
    "l": "l", "r": "r", "x": "x",
}
_VOWELS = set("aeiouy")


def phonetic_key(word: str) -> str:
    """Compact English phonetic key for drug names (lowercase letters).

    Case, spaces, digits and punctuation are ignored; then, in order:
    1. leading kn/gn/pn/wr lose the first letter; leading x is s.
    2. ph->f, ck->k, sch->sk, ch->k, th->t, sh->s; gh is silent.
    3. c before e/i/y is s, otherwise k; x is ks.
    4. Keep the first letter (a vowel there becomes a); drop later vowels, h, w.
    5. Merge confusable consonants: b/p, d/t, g/k/q, v/f, z/s.
    6. Collapse runs of the same letter ("all" -> "l").
    """
    s = re.sub(r"[^a-z]", "", (word or "").lower())
    if not s:
        return ""
    if s[:2] in ("kn", "gn", "pn", "wr"):
        s = s[1:]
    if s[0] == "x":
        s = "s" + s[1:]
    s = s.replace("sch", "sk").replace("ph", "f").replace("ck", "k")
    s = re.sub(r"gh", "", s)
    s = s.replace("ch", "k").replace("th", "t").replace("sh", "s")
    s = re.sub(r"c(?=[eiy])", "s", s).replace("c", "k").replace("x", "ks")
    out = []
    for i, ch in enumerate(s):
        if i == 0:
            code = "a" if ch in _VOWELS else _CLASS.get(ch, ch)
        elif ch in _VOWELS or ch in "hw":
            continue
        else:
            code = _CLASS.get(ch, ch)
        if not out or out[-1] != code:
            out.append(code)
    return "".join(out)


_slot: dict = {}  # per_lexicon: lexicon list -> rows
_blocked_slot: dict = {}  # per_lexicon: lexicon list -> stand-in rows of the names the clinic's overlay removed


def _rows():
    """[(spelling, phonetic key, canonical)], sorted, cached per lexicon."""
    from .determinism import _alias_map, load_lexicon
    lex = load_lexicon()
    return per_lexicon(_slot, lex, lambda: tuple((text, phonetic_key(text), canon)
                                                 for text, canon in sorted(_alias_map(lex).items())
                                                 if len(text) >= MIN_LEN and " " not in text))


def _score(a: str, ka: str, b: str, kb: str) -> float:
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    kratio = difflib.SequenceMatcher(None, ka, kb).ratio() if ka and kb else 0.0
    score = 0.5 * ratio + 0.5 * kratio
    if ka and ka == kb:
        score += 0.15
    elif min(len(ka), len(kb)) >= 3 and (ka.startswith(kb) or kb.startswith(ka)):
        score += 0.10
    return min(score, 1.0)


def _blocked_rows() -> tuple:
    """((letters, phonetic key)) of every name the clinic's overlay removed (``drugnames.blocked_names``): stand-ins
    that compete with the list's spellings but are never offered. () without an overlay."""
    from .determinism import load_lexicon
    from .drugnames import blocked_names
    lex = load_lexicon()
    if not blocked_names(lex):
        return ()
    return per_lexicon(_blocked_slot, lex, lambda: tuple(sorted(
        {(t, phonetic_key(t)) for t in (re.sub(r"[^a-z]", "", b) for b in blocked_names(lex)) if len(t) >= MIN_LEN})))


def _steered_off(name: str, low: str, key: str, top: float) -> bool:
    """True when ``name`` is a blocked name, or a blocked name scores at least as well as the best listed spelling
    (``top``): its nearest spelling is a drug the clinic removed, so no look-alike of it is offered (plan PQ-f C1)."""
    from .drugnames import is_blocked
    if is_blocked(name):
        return True
    cl, ck = Counter(low), Counter(key)
    floor = max(MIN_SCORE, top)
    return any(_bound(low, cl, key, ck, t, tk) >= floor and _score(low, key, t, tk) >= floor for t, tk in _blocked_rows())


def scored_candidates(name: str, k: int = 3, guard: bool = True) -> list:
    """[(canonical, score)] behind suggest_candidates: the same rules, the same order. [] when ``guard`` and the name,
    or its nearest spelling, is a name the clinic's overlay removed (``_steered_off``); ``guard=False`` is for the
    look-alike flag of a clinic's own name, which must still see the look-alike."""
    low = re.sub(r"[^a-z]", "", (name or "").lower())
    key = phonetic_key(low)
    if k <= 0 or len(low) < 4 or len(low) > MAX_NAME_LETTERS or len(key) < 3:
        return []
    best = {}
    for text, tkey, canon in _rows():
        sc = _score(low, key, text, tkey)
        if sc >= MIN_SCORE and sc > best.get(canon, 0.0):
            best[canon] = sc
    if guard and _steered_off(name, low, key, max(best.values(), default=0.0)):
        return []
    return sorted(best.items(), key=lambda kv: (-round(kv[1], 6), kv[0].lower(), kv[0]))[:k]


def _bound(a: str, ca: Counter, ka: str, cka: Counter, b: str, kb: str) -> float:
    """An upper bound of _score(a, ka, b, kb): difflib's ratio never exceeds 2 * (shared letters) / (len a + len b),
    and the key bonus is at most 0.15. Never below the real score, so skipping under MIN_SCORE changes no result."""
    text = 2 * sum((ca & Counter(b)).values()) / (len(a) + len(b))
    keys = 2 * sum((cka & Counter(kb)).values()) / (len(ka) + len(kb)) if ka and kb else 0.0
    return 0.5 * text + 0.5 * keys + 0.15


def scored_spellings(name: str, k: int = 3) -> list:
    """[(spelling, canonical, score)] by the same rules as scored_candidates, one entry per lexicon spelling as written
    (a brand in its own spelling, an alias as its generic), best first; ties by spelling (plan I2-a)."""
    from .determinism import _maps
    low = re.sub(r"[^a-z]", "", (name or "").lower())
    key = phonetic_key(low)
    if k <= 0 or len(low) < 4 or len(low) > MAX_NAME_LETTERS or len(key) < 3:
        return []
    shown, best = _maps()[0], {}
    cl, ck = Counter(low), Counter(key)
    for text, tkey, canon in _rows():
        if _bound(low, cl, key, ck, text, tkey) < MIN_SCORE:         # cannot reach MIN_SCORE: skip the two difflib passes
            continue
        sc = _score(low, key, text, tkey)
        spelling = shown.get(text, canon)                       # a name two generics claim is not in the surface map
        if sc >= MIN_SCORE and sc > best.get(spelling, (0.0, ""))[0]:
            best[spelling] = (sc, canon)
    if _steered_off(name, low, key, max((v[0] for v in best.values()), default=0.0)):
        return []                                               # never steer a removed name to a look-alike
    ranked = sorted(best.items(), key=lambda kv: (-round(kv[1][0], 6), kv[0].lower(), kv[0]))
    return [(s, c, sc) for s, (sc, c) in ranked[:k]]


def suggest_candidates(name: str, k: int = 3, guard: bool = True) -> list:
    """Up to ``k`` lexicon canonical names that sound like ``name``, best first.

    Score = 0.5 * spelling ratio + 0.5 * phonetic-key ratio (difflib), +0.15
    for equal keys, +0.10 for a key prefix (3+ letters), capped at 1.0. A
    canonical keeps its best spelling (generic, alias or brand). Under
    MIN_SCORE nothing is returned, so garbage gives []. Ties sort by name.
    """
    return [c for c, _ in scored_candidates(name, k, guard)]


def similarity(name: str, spelling: str) -> float:
    """The score suggest_candidates would give one more single-word ``spelling`` for ``name``; 0.0 outside its rules."""
    low = re.sub(r"[^a-z]", "", (name or "").lower())
    text = " ".join(str(spelling or "").split()).lower()
    key = phonetic_key(low)
    if len(low) < 4 or len(low) > MAX_NAME_LETTERS or len(key) < 3 or len(text) < MIN_LEN or " " in text:
        return 0.0
    return _score(low, key, text, phonetic_key(text))
