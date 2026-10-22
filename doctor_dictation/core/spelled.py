"""Spelled words: what the doctor spells letter by letter wins over the words heard before it. Pure; stdlib only.

"tablet Cello dial, spelled S-I-L-O-D-A-L, 8 mg" -> "tablet Silodal, 8 mg". The letters are joined into one word,
and the 1-3 spoken words just before them are replaced when the doctor said a cue word ("spelled", "spelling",
"that is") or when those words sound like the spelled one (similarity >= SIMILAR). A replacement made only
because the words sounded alike ("alike") is shown on its medicine row with an Undo (``tag_rows``); a cue word
needs no question. ``mask``/``unmask`` keep the spelled word away from the lexicon correction, which would
otherwise rewrite a spelled brand to the nearest listed name ("Tamsulin" -> "Tamsulosin").
"""
import difflib
import re

SIMILAR = 0.5           # how alike the spoken words must be to the spelled word for a replacement without a cue
MAX_SPOKEN_WORDS = 3    # the spoken name the letters replace: at most this many words
MIN_LONE_LETTERS = 4    # letters with nothing to replace are joined only from this many ("B, C, D" stays as dictated)

# 3+ single letters separated by spaces, hyphens, commas or full stops: "S-I-L-O-D-A-L", "U S G", "T. A. M."
_RUN = re.compile(r"\b[A-Za-z](?:(?:\s*[-.,]\s*|\s+)[A-Za-z]\b){2,}\.?")
_CUE = re.compile(r"(?:,\s*)?\b(?:spelled as|spelt as|spelling is|spelled|spelt|spelling|that is)\b\s*[:,-]?\s*$", re.I)
_FORMS = {"tablet", "tab", "tabs", "capsule", "cap", "caps", "syrup", "syr", "injection", "inj", "drops", "ointment", "cream"}
_STOP = _FORMS | {"and", "then", "also", "advised", "advise", "with", "for", "of", "the", "a", "an", "to", "is", "start",
                  "give", "continue", "stop", "plus"}
_WORD_AT_END = re.compile(r"[A-Za-z][A-Za-z'-]*$")


def _letters(text: str) -> str:
    return "".join(re.findall(r"[A-Za-z]", text)).lower()


def _join(run: str) -> str:
    """The spelled word: short ones read as abbreviations (USG, KFT), longer ones as names (Silodal)."""
    word = "".join(re.findall(r"[A-Za-z]", run))
    return word.upper() if len(word) <= 4 else word.capitalize()


def similarity(spoken: str, word: str) -> float:
    """How alike the spoken words and the spelled word are, letters only (0..1)."""
    a, b = _letters(spoken), _letters(word)
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _spans(head: str) -> list:
    """[(start, spoken words)] for the last 1..MAX_SPOKEN_WORDS words of ``head``, nearest first. Stops at a form
    word, a connector ("and"), a number or any punctuation between words, so a span never crosses into the
    previous medicine or sentence."""
    rest, out = head.rstrip(" ,"), []
    for _ in range(MAX_SPOKEN_WORDS):
        m = _WORD_AT_END.search(rest)
        if not m or m.group().lower() in _STOP:
            break
        out.append((m.start(), head[m.start():len(head.rstrip(" ,"))]))
        rest = rest[:m.start()]
        if not re.search(r"[ \t]$", rest):
            break                                   # punctuation or the start of the text: no earlier word belongs
        rest = rest.rstrip(" \t")
    return out


def _best(spans: list, word: str):
    """The span most like ``word``; a longer span wins a near tie (within 0.05), so "Cello dial" beats "dial"."""
    best = None
    for start, spoken in spans:
        score = similarity(spoken, word)
        if best is None or score > best[2] + 0.05 or (score >= best[2] - 0.05 and len(spoken) > len(best[1])):
            best = (start, spoken, score)
    return best


def apply(text: str):
    """(text with each spelled word joined and the spoken words it replaces removed, [{spelled, heard, why}]).

    ``why`` is "cue" (the doctor said "spelled"), "alike" (no cue; the spoken words sound like it) or "" (nothing
    replaced: the letters are only joined). ``heard`` is the spoken text that was replaced ("" when none).
    """
    text = text or ""
    out, found, pos = [], [], 0
    for m in _RUN.finditer(text):
        run = m.group()
        word = _join(run)
        stop = "." if run.endswith(".") and "." not in run[:-1] else ""   # "S-I-L-O-D-A-L." still ends its sentence
        before = text[pos:m.start()]
        cue = _CUE.search(before)
        head = before[:cue.start()] if cue else before
        best = _best(_spans(head), word)
        if best and (cue or best[2] >= SIMILAR):
            out.append(head[:best[0]] + word + stop)
            found.append({"spelled": word, "heard": best[1], "why": "cue" if cue else "alike"})
        elif cue or len(word) >= MIN_LONE_LETTERS:
            out.append((head.rstrip(" ,") + " " if cue else before) + word + stop)
            found.append({"spelled": word, "heard": "", "why": ""})
        else:
            out.append(before + run)                # "B, C, D" or "U S G" with nothing to replace: as dictated
        pos = m.end()
    out.append(text[pos:])
    return "".join(out), found


def mask(text: str, found: list):
    """(text with every spelled word swapped for a token no lexicon pass can match, {token: word})."""
    tokens = {}
    for i, word in enumerate(sorted({f["spelled"] for f in found}, key=len, reverse=True)):
        token = f"\x01{i}\x01"
        text, n = re.subn(r"\b" + re.escape(word) + r"\b", token, text)
        if n:
            tokens[token] = word
    return text, tokens


def unmask(text: str, tokens: dict) -> str:
    for token, word in tokens.items():
        text = text.replace(token, word)
    return text


def found_in(text: str) -> list:
    """The replacements ``apply`` makes in ``text`` (the same whitespace tidy as normalize_transcript)."""
    return apply(re.sub(r"\s+", " ", (text or "").strip()))[1]


def tag_rows(rows, found: list):
    """Copies of ``rows``: a row named exactly as a word replaced only because it sounded alike gets
    ``spelled_heard`` (the spoken text), which the page shows with an Undo. Other rows are returned unchanged."""
    heard = {f["spelled"].casefold(): f["heard"] for f in found
             if f["why"] == "alike" and f["heard"] and _letters(f["heard"]) != _letters(f["spelled"])}   # same word: nothing to undo
    if not heard or not isinstance(rows, list):
        return rows
    out = []
    for row in rows:
        name = str(row.get("name") or "").strip().strip(".").casefold() if isinstance(row, dict) else ""
        out.append({**row, "spelled_heard": heard[name]} if name in heard else row)
    return out
