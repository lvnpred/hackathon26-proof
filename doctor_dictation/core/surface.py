"""Surface forms: what `correct_drugs` writes for a lexicon name. Pure; determinism imports this.

A generic or a misspelling is written as the canonical generic; a brand in its own spelling.
`_alias_map` still gives the generic for every check. Names two generics claim are left out.
"""
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
    """The generic to show on screen when the name is a brand (never printed); else "".

    Depends on the name and its `lexicon_match` only, so the server recomputes it for any row
    (correction.preserve_untouched_rx_status); the client need not send it back.
    """
    return match if match and match.lower() != (name or "").strip().lower() else ""


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
