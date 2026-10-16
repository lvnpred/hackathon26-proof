"""Look-alike guard and "heard" text (pure). `lasa_row` is the one hook determinism.py calls per row.

Two tiers: the curated list (lexicon/lasa_pairs.json) ALWAYS flags; any other computed pair flags
only on evidence in the raw transcript (the name was auto-corrected, or a twin is dictated too).
"""
import difflib
import json
import logging
import re
from pathlib import Path

from .candidates import phonetic_key

RX_LOOKALIKE = "lookalike-check"
PAIRS_PATH = Path(__file__).resolve().parent / "lexicon" / "lasa_pairs.json"
MIN_RATIO = 0.75   # spelling similarity that makes two generics look-alikes
MIN_EVIDENCE_LETTERS = 5   # a twin phrase shorter than this ("iron") is too common to be evidence
MIN_HEARD = 0.8    # the cut-off grounding uses to find a name in a transcript
MAX_NAME_WORDS = 8   # heard_as skips a longer name

_cache = (None, None)  # (lexicon list the index was built from, index)


def _words(text) -> list:
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def _has(words: list, phrase: tuple) -> bool:
    k = len(phrase)
    return bool(k) and any(tuple(words[i:i + k]) == phrase for i in range(len(words) - k + 1))


def _curated() -> list:
    try:
        pairs = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))["pairs"]
        if not isinstance(pairs, list):
            raise TypeError("'pairs' is not a list")
    except (OSError, ValueError, KeyError, TypeError) as err:
        logging.getLogger(__name__).warning("look-alike list %s unusable (%s): the always-flag tier is off",
                                            PAIRS_PATH, err)
        return []   # a missing or broken file only switches the always-flag tier off
    return [(str(p["a"]).strip().lower(), str(p["b"]).strip().lower())
            for p in pairs if isinstance(p, dict) and p.get("a") and p.get("b")]


def _index() -> dict:
    """by_low / twins / always / names / amap / exact, cached per loaded lexicon list."""
    global _cache
    from .determinism import _alias_map, load_lexicon

    lex = load_lexicon()
    if _cache[0] is lex:
        return _cache[1]
    canons = sorted({str(e["canonical"]).strip() for e in lex if str(e.get("canonical") or "").strip()})
    by_low = {c.lower(): c for c in canons}
    keys = {c: phonetic_key(c) for c in canons}
    twins: dict = {c: {} for c in canons}
    for i, a in enumerate(canons):
        sm = difflib.SequenceMatcher(None)
        sm.set_seq2(a.lower())
        for b in canons[i + 1:]:
            sm.set_seq1(b.lower())
            fast = sm.real_quick_ratio() >= MIN_RATIO and sm.quick_ratio() >= MIN_RATIO
            ratio = sm.ratio() if fast else 0.0
            if ratio >= MIN_RATIO or (keys[a] and keys[a] == keys[b]):
                twins[a][b] = twins[b][a] = max(ratio, MIN_RATIO)
    always = set()
    for a, b in _curated():
        if a in by_low and b in by_low:
            ca, cb = by_low[a], by_low[b]
            twins[ca][cb] = twins[cb][ca] = 1.0
            always.add(frozenset((ca, cb)))
    names = {c: [] for c in canons}   # every spelling of a canonical, as word tuples
    for e in lex:
        c = str(e.get("canonical") or "").strip()
        if c:
            names[c] += [tuple(_words(x)) for x in [c, *e.get("aliases", []), *e.get("brands", [])]]
    amap = _alias_map()
    exact = {" ".join(_words(k)): v for k, v in amap.items()}   # first spelling wins
    index = {"by_low": by_low, "twins": twins, "always": always, "names": names, "amap": amap, "exact": exact}
    _cache = (lex, index)
    return index


def twins(canonical: str) -> list:
    """Look-alike generics of ``canonical``, closest first; [] if none."""
    ix = _index()
    found = ix["twins"].get(ix["by_low"].get(str(canonical or "").strip().lower()), {})
    return sorted(found, key=lambda t: (-found[t], t.lower()))


def always_flag_names() -> frozenset:
    """Canonicals that flag on every dictation (the curated list)."""
    return frozenset(c for pair in _index()["always"] for c in pair)


def heard_as(name: str, raw_transcript: str) -> str:
    """The raw-transcript words ``name`` came from; "" when the name is there as written (case,
    punctuation and hyphens ignored). Else the best k-1..k+1 word stretch (k = words in the name),
    in its original case, that is an alias of the same generic or >= MIN_HEARD similar and within
    4 letters in length; the earlier stretch wins a tie. A name of more than MAX_NAME_WORDS (8) words is never a
    real drug name: it returns "" without searching (the cost grows with name words x transcript tokens)."""
    nw = _words(name)
    if len(nw) > MAX_NAME_WORDS:
        return ""
    toks = re.findall(r"[A-Za-z0-9]+", str(raw_transcript or ""))
    low = [t.lower() for t in toks]
    if not nw or not toks or _has(low, tuple(nw)):
        return ""
    amap = _index()["amap"]
    nj = " ".join(nw)
    want = amap.get(nj)
    best, best_r = "", 0.0
    for n in sorted({max(1, len(nw) - 1), len(nw), len(nw) + 1}):
        for i in range(len(low) - n + 1):
            g = " ".join(low[i:i + n])
            r = difflib.SequenceMatcher(None, nj, g).ratio()
            alias = bool(want) and amap.get(g) == want
            if (alias or (abs(len(g) - len(nj)) <= 4 and r >= MIN_HEARD)) and r > best_r:
                best, best_r = " ".join(toks[i:i + n]), r
    return best


def lookalike_flag(canonical: str, name: str, raw_transcript: str) -> str:
    """The twin to ask the doctor about, or "". Curated pair: always. Other pairs: only with evidence in
    ``raw_transcript`` (a twin dictated too, or ``name`` auto-corrected); with none, only curated pairs."""
    ix = _index()
    c = ix["by_low"].get(str(canonical or "").strip().lower())
    ts = twins(c) if c else []
    for t in ts:
        if frozenset((c, t)) in ix["always"]:
            return t
    words = _words(raw_transcript)
    if not ts or not words:
        return ""
    h = heard_as(name, raw_transcript)
    own = (_words(name), _words(c), _words(h))   # a twin's spelling inside our own name or heard text is no evidence
    for t in ts:
        if any(_has(words, ph) and len("".join(ph)) >= MIN_EVIDENCE_LETTERS and not any(_has(w, ph) for w in own)
               for ph in ix["names"].get(t, [])):
            return t
    # a dictated lexicon alias or brand is an exact name, like the generic: not an auto-correction
    return ts[0] if h and ix["exact"].get(" ".join(_words(h))) != c else ""


def lasa_row(status: str, canonical: str, name: str, raw_transcript: str):
    """(status, {"heard", "lookalike"}) for one grounded row; only a verified row becomes look-alike."""
    twin = lookalike_flag(canonical, name, raw_transcript) if status == "verified" else ""
    heard = heard_as(name, raw_transcript) if name else ""
    return (RX_LOOKALIKE if twin else status), {"heard": heard, "lookalike": twin}
