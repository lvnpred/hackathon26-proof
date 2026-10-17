"""Surface forms: what `correct_drugs` writes for a lexicon name. Pure; determinism imports this.

Lexicon entry keys: ``canonical``, ``aliases``, ``brands``, ``forms``, ``strengths``, ``lineage`` and (owner decision (d), I2-a)
``generic_hidden``: a list of that entry's brands that are combination products not modelled yet (Fefol, Autrin, ...). They stay
recognised (spelling, grounding) but the row shows and prints NO generic (`generic_hidden` below) and gets no dose check
(`dosing.ground_extra`). Readers that do not know the key ignore it; build.py merges and checks it byte-stably.

A generic or a misspelling is written as the canonical generic; a brand in its own spelling.
`_alias_map` still gives the generic for every check. Names two generics claim are left out.
"""
import difflib
import re


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def ambiguous_names(entries) -> dict:
    """lower-case name -> sorted tuple of the generics that claim it (two or more)."""
    seen: dict = {}
    for e in entries:
        canon = _clean(e.get("canonical"))
        for a in [canon, *e.get("aliases", []), *e.get("brands", [])] if canon else []:
            if _clean(a):
                seen.setdefault(_clean(a).lower(), set()).add(canon)
    return {k: tuple(sorted(v)) for k, v in seen.items() if len(v) > 1}


def mask_as_dictated(text: str, names, masked: dict) -> str:
    """Hide each spaced or hyphenated phrase of `names` behind a letter-free token, as dictated.

    For the names two generics claim: no later pass of `correct_drugs` may rewrite one word of
    such a phrase ("neo-mercazole" must not become "neo-Omeprazole"). Words may be joined by a
    space or a hyphen. The text as dictated is recorded in `masked` (token -> text) for restoring.
    """
    def _hide(m):
        token = f"\x01{len(masked)}\x01"
        masked[token] = m.group(0)
        return token
    for name in sorted((n for n in names if re.search(r"[\s-]", n)), key=len, reverse=True):
        words = [re.escape(w) for w in re.split(r"[\s-]+", name) if w]
        text = re.sub(r"\b" + r"[\s-]+".join(words) + r"\b", _hide, text, flags=re.I)
    return text


def _generic_of(name: str, match: str) -> str:
    """The generic of a row the lexicon knows: its lexicon match, for a brand AND for a generic-named row (plan I2-a);
    "" without a match. ``name`` stays for the call sites. Shown on screen; printed under a brand (pdf/sheet.py).

    Depends on the name and its `lexicon_match` only, so the server recomputes it for any row
    (correction.preserve_untouched_rx_status); the client need not send it back.
    """
    return "" if generic_hidden(name, match) else (match or "").strip()


_hidden_cache = (None, frozenset())      # (lexicon list, lower-case brands whose entry lists them in ``generic_hidden``)


def _hidden_brands(lex) -> frozenset:
    global _hidden_cache
    if _hidden_cache[0] is not lex:
        _hidden_cache = (lex, frozenset(str(b).strip().lower() for e in lex for b in e.get("generic_hidden", []) if isinstance(b, str)))
    return _hidden_cache[1]


def generic_hidden(name: str, match: str) -> bool:
    """True when ``name`` is (or is one near spelling from) a brand an entry lists in ``generic_hidden``: a combination product
    not modelled yet, so no generic is shown or printed and no dose check runs. A generic name or another brand never is.
    The near-spelling rule is the one `_canonical_lookup` uses (difflib 0.84 over keys of 5+ letters)."""
    from . import determinism as D     # lazy: determinism imports this module
    low = (name or "").strip().lower()
    hidden = _hidden_brands(D.load_lexicon())
    if not match or not low or not hidden:
        return False
    amap = D._alias_map()
    if low in amap:
        return low in hidden
    near = difflib.get_close_matches(low, sorted(k for k in amap if len(k) >= 5), n=1, cutoff=0.84)
    return bool(near) and near[0] in hidden


def surface_map(entries, amap: dict) -> dict:
    """alias_lower -> text to write; a brand maps to its own spelling when `amap` agrees on its generic."""
    out = dict(amap)
    for e in entries:
        canon = _clean(e.get("canonical"))
        for b in e.get("brands", []):
            key = _clean(b).lower()
            if key and amap.get(key) == canon and key != canon.lower():
                out[key] = _clean(b)
    for key in ambiguous_names(entries):
        out.pop(key, None)
    return out
