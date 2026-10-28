"""Medicine-name matching against the loaded lexicon: the alias map, ``correct_drugs`` and the exact / fuzzy lookups.

Split out of ``determinism`` (which re-exports every name here, so imports keep working). Stdlib only, deterministic.
The lexicon is ``determinism.load_lexicon()`` (read through the module, so a test that patches it is honoured).

BLOCKED names (plan PQ-f, clinical safety): a name the clinic's overlay took off the list (a hidden entry's names, a
brand or alias an edit dropped, a name of a clinic row the read path sets aside) is in ``overlay.blocked_of(lex)``.
Such a name is never rewritten and never matched to another drug: it stays as dictated and grades unknown-medicine, the
safe path of any unknown name. A dictated word whose nearest spelling is a blocked name is left alone the same way.
Names compare as ``overlay._claim`` does: case, a trailing ".", space / hyphen / dashes ignored.
"""
import difflib
import re

from . import overlay
from .combo import SEP_CHARS
from .commonwords import WORDS as COMMON_WORDS
from .lexmemo import per_lexicon
from .surface import ambiguous_names, mask_as_dictated

_alias_slot: dict = {}  # per_lexicon: lexicon list -> alias map
_maps_slot: dict = {}   # per_lexicon: lexicon list -> (surface map, ambiguous names)
_sep_slot: dict = {}    # per_lexicon: lexicon list -> alias map keyed with one separator
_block_slot: dict = {}  # per_lexicon: lexicon list -> regex of the blocked multi-word names (or None)
_strip_slot: dict = {}  # per_lexicon: lexicon list -> regex of every blocked name (or None)
_SEP_RE = re.compile(rf"[{SEP_CHARS}]+")
FUZZY_CUTOFF = 0.84


def _D():
    from . import determinism as D       # lazy: determinism imports this module
    return D


def _lex():
    return _D().load_lexicon()


def blocked_names(lex=None) -> frozenset:
    """The names (``overlay._claim`` form) this clinic's list blocks; empty without an overlay."""
    return overlay.blocked_of(_lex() if lex is None else lex)


def is_blocked(name, lex=None) -> bool:
    """True when ``name`` is a name the clinic's overlay took off the list (separator, case and trailing "." alike)."""
    blocked = blocked_names(lex)
    return bool(blocked) and overlay._claim(name) in blocked


def _alias_map(lex=None):
    """alias_lower -> canonical, cached per lexicon list (``lex``, default the loaded one). Callers must not mutate it.

    Deterministic and file-order independent: pass 1 claims canonical names +
    aliases (sorted by canonical), pass 2 claims brands. So brands always
    resolve to their generic (crocin -> Paracetamol), never to a stub entry.
    """
    lex = _lex() if lex is None else lex
    return per_lexicon(_alias_slot, lex, lambda: _build_alias_map(lex))


def _build_alias_map(lex) -> dict:
    m: dict = {}
    entries = sorted(lex, key=lambda e: e.get("canonical", ""))
    for e in entries:
        canon = e.get("canonical", "")
        if not canon:
            continue
        for a in [canon] + e.get("aliases", []):
            key = a.strip().lower()
            if key and key not in m:
                m[key] = canon
    for e in entries:
        canon = e.get("canonical", "")
        if not canon:
            continue
        for a in e.get("brands", []):
            key = a.strip().lower()
            if key and key not in m:
                m[key] = canon
    return m


def _maps():
    """(surface map, ambiguous names), cached per loaded lexicon list."""
    lex = _lex()
    return per_lexicon(_maps_slot, lex, lambda: (_D().surface_map(lex, _alias_map(lex)), ambiguous_names(lex)))


def _block_index(lex):
    """A regex of every multi-word blocked name and, as alternatives that win, every listed multi-word name (longest
    first), or None when no multi-word name is blocked; cached per lexicon list."""
    def build():
        multi = {b for b in blocked_names(lex) if " " in b}
        if not multi:
            return None
        listed = {overlay._claim(k) for k in _alias_map(lex) if _SEP_RE.search(k)}
        sep = rf"[{SEP_CHARS}]+"
        phrases = sorted(multi | listed, key=lambda p: (-len(p), p))
        return re.compile(r"\b(?:" + "|".join(sep.join(re.escape(w) for w in p.split()) for p in phrases) + r")\b", re.I)
    return per_lexicon(_block_slot, lex, build)


def without_blocked(transcript: str, name: str = "", lex=None) -> str:
    """``transcript`` with every blocked name it dictates blanked out, so a row naming another drug is not "heard" inside
    it ("citalopram" inside a dictated "escitalopram" while Escitalopram is hidden). ``name``'s own spelling is kept (a
    row that IS the blocked name, e.g. a name the clinic learned since). Unchanged without blocked names.

    The rule of ``_mask_blocked``: every listed multi-word name is in the same regex, longest first, and a match of one
    is kept, so a blocked "magnesium" inside a dictated "magnesium hydroxide" (a listed drug) is not blanked. Only a
    blocked name standing on its own is."""
    lex = _lex() if lex is None else lex
    blocked = blocked_names(lex)
    if not blocked or not transcript:
        return transcript

    def build():
        sep = rf"[{SEP_CHARS}]+"
        listed = {overlay._claim(k) for k in _alias_map(lex) if _SEP_RE.search(k)}
        alts = sorted(set(blocked) | listed, key=lambda p: (-len(p), p))
        return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(sep.join(re.escape(w) for w in p.split()) for p in alts)
                          + r")\.?(?![A-Za-z0-9])", re.I)
    pat = per_lexicon(_strip_slot, lex, build)
    own = overlay._claim(name)

    def _blank(m):
        c = overlay._claim(m.group(0))
        return " " if c in blocked and c != own else m.group(0)    # a listed longer name, or the row's own name: kept
    return pat.sub(_blank, transcript)


def _mask_blocked(text: str, masked: dict, lex) -> str:
    """Hide each blocked multi-word name as dictated (like ``mask_as_dictated``). A longer listed name matched at the
    same place is left for the later passes, so a blocked "calcium citrate" never eats into a listed longer name."""
    pat = _block_index(lex)
    if pat is None:
        return text
    blocked = blocked_names(lex)

    def _hide(m):
        if overlay._claim(m.group(0)) not in blocked:
            return m.group(0)
        token = f"\x01{len(masked)}\x01"
        masked[token] = m.group(0)
        return token
    return pat.sub(_hide, text)


def _fuzzy(low: str, keys: list, lex) -> str:
    """The nearest of ``keys`` (difflib, FUZZY_CUTOFF) to ``low``, or "" when there is none OR the nearest spelling is
    a blocked name (they compete as stand-ins): a near spelling of a name the clinic removed never moves to a neighbour."""
    blocked = blocked_names(lex)
    pool = sorted(set(keys) | {b for b in blocked if len(b) >= 5}) if blocked else keys
    best = difflib.get_close_matches(low, pool, n=1, cutoff=FUZZY_CUTOFF)
    return "" if not best or best[0] in blocked else best[0]


def correct_drugs(text: str) -> str:
    """Fix STT splits/misspellings against the local lexicon (deterministic). A blocked name stays as dictated."""
    amap, amb = _maps()  # alias -> text to write (generic, or the brand as spelled); ambiguous names
    if not amap:
        return text
    lex = _lex()
    blocked = blocked_names(lex)
    out = text
    # 0) multiword aliases canonicalized (longest first), with canonical
    #    phrases masked BEFORE alias replacement so a shorter alias can never
    #    match inside an already-correct phrase ("magnesium citrate" inside
    #    "Potassium Magnesium Citrate"). Mask tokens are digit-only, invisible
    #    to the [A-Za-z] passes below. Each alias is replaced by the mask token of its text, so a shorter alias
    #    can never match inside a longer one's replacement either (a clinic renames "Potassium Magnesium Citrate":
    #    the old name is an alias now, and "magnesium citrate" would double words inside the new name).
    masked = {}
    token_of = {}    # text -> its mask token

    def _token(text: str) -> str:
        if text not in token_of:
            token_of[text] = f"\x00{len(token_of)}\x00"
            masked[token_of[text]] = text
        return token_of[text]

    def _mask(s: str) -> str:
        for canon in sorted({c for c in amap.values() if " " in c or "-" in c}, key=len, reverse=True):
            pat = re.compile(r"\b" + re.escape(canon) + r"\b", re.I)
            if pat.search(s):
                s = pat.sub(_token(canon), s)
        return s

    def _restore(s: str) -> str:
        for token, canon in masked.items():
            s = s.replace(token, canon)
        return s

    out = mask_as_dictated(out, amb, masked)  # a phrase two generics claim: kept whole
    out = _mask(_mask_blocked(out, masked, lex))  # a phrase the clinic removed: kept as dictated
    for alias in sorted((a for a in amap if " " in a or "-" in a), key=len, reverse=True):
        out = re.sub(r"\b" + re.escape(alias) + r"\b", _token(amap[alias]), out, flags=re.I)

    nospace = {}
    for alias, canon in amap.items():
        key = re.sub(r"[^a-z]", "", alias)
        if len(key) >= 5 and key not in nospace:
            nospace[key] = canon
    # 1) two-word splits: "tam sulosin" -> canonical
    tokens = re.findall(r"[A-Za-z]+", out)
    for i in range(len(tokens) - 1):
        w1, w2 = tokens[i], tokens[i + 1]
        if len(w1) < 2 or len(w2) < 3 or {w1.lower(), w2.lower()} <= COMMON_WORDS:
            continue
        if blocked and (w1.casefold() in blocked or w2.casefold() in blocked):
            continue
        key = (w1 + w2).lower()
        if key in nospace and not _ambiguous_for(key):
            canon = nospace[key]
            out = re.sub(r"\b" + re.escape(w1) + r"\s+" + re.escape(w2) + r"\b",
                         canon, out, count=1, flags=re.I)
    out = _mask(out)  # a hyphenated or spaced brand written by the split must survive pass 2
    # 2) single-word exact alias + fuzzy (cutoff fixed, sorted keys)
    keys = sorted(k for k in amap if len(k) >= 5 and " " not in k)
    for tok in set(re.findall(r"[A-Za-z]{5,}", out)):
        low = tok.lower()
        # removed by the clinic, two generics claim it (or a near spelling), or an ordinary word: leave it as dictated
        if (blocked and low in blocked) or _ambiguous_for(low) or low in COMMON_WORDS:
            continue
        if low in amap and " " not in low:
            if tok != amap[low]:
                out = re.sub(r"\b" + re.escape(tok) + r"\b", amap[low], out, flags=re.I)
            continue
        best = _fuzzy(low, keys, lex)
        if best:
            out = re.sub(r"\b" + re.escape(tok) + r"\b", amap[best], out, flags=re.I)
    return _restore(out)


def _canonical_lookup(name: str) -> str:
    """Resolve a dictated/LLM drug name to the lexicon canonical form.

    Exact alias match first, then fixed-cutoff fuzzy. Returns "" when the
    medicine is not in the list, and for a blocked name or a near spelling of one. Deterministic (sorted keys).
    """
    lex = _lex()
    amap = _alias_map(lex)
    low = (name or "").strip().lower()
    if not low or is_blocked(low, lex):
        return ""
    if low in amap:
        return amap[low]
    best = _fuzzy(low, sorted(k for k in amap if len(k) >= 5), lex)
    return amap[best] if best else ""


def _exact_lookup(name: str) -> str:
    """Canonical for a name that IS a drug-list key (brand, alias or generic), else "" (also for a blocked name).

    No fuzzy matching. Whitespace is collapsed, a trailing "." dropped and case
    ignored; a space and a hyphen count as the same separator.
    """
    low = _SEP_RE.sub(" ", (name or "").strip()).rstrip(".").strip().lower()
    if not low:
        return ""
    lex = _lex()
    if is_blocked(low, lex):
        return ""
    amap = _alias_map(lex)
    if low in amap:
        return amap[low]
    return _sep_map(lex, amap).get(_SEP_RE.sub(" ", low), "")


def _sep_map(lex, amap: dict) -> dict:
    """``amap`` keyed with every separator run as one space (first key wins), cached per lexicon list."""
    def build():
        sep: dict = {}
        for k, v in amap.items():
            sep.setdefault(_SEP_RE.sub(" ", k), v)
        return sep
    return per_lexicon(_sep_slot, lex, build)


def _ambiguous_for(low: str) -> tuple:
    """Generics a dictated name could mean when two claim it (exact or a near spelling); else () (also when blocked)."""
    amb = _maps()[1]
    if low in amb:
        return amb[low]
    if is_blocked(low):
        return ()
    near = difflib.get_close_matches(low, sorted(k for k in amb if len(k) >= 5), n=1, cutoff=FUZZY_CUTOFF)
    return amb[near[0]] if near and low not in _alias_map() else ()
