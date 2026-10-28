"""The government generics list at run time (plan I2-d): a pure reader of core/lexicon/generics.json, loaded once.

It only informs: ``schedule_of`` never changes a row's name, status or the Save gate. A missing or broken file means
no marks. The file is written offline by core/lexicon/generics_sync.py; correct_drugs never reads it.

The file is read ONCE per process. After a sync or a promote, RESTART the server (a sync or promote run in the same process
calls ``reload()`` itself)."""
import json
from pathlib import Path

GENERICS_PATH = Path(__file__).resolve().parent / "lexicon" / "generics.json"
RANK = {"H": 1, "H1": 2, "X": 3}
_cache = None

def _load():
    global _cache
    if _cache is None:
        try:
            data = json.loads(GENERICS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        marks = {}
        for e in data.get("entries") if isinstance(data.get("entries"), list) else []:
            lex = str(e.get("lexicon") or "").casefold() if isinstance(e, dict) else ""
            lists = e.get("lists") if lex and isinstance(e.get("lists"), dict) else {}
            for m in lists.values():
                s = m.get("schedule", "") if isinstance(m, dict) else ""
                if s in RANK and RANK[s] > RANK.get(marks.get(lex, ""), 0):
                    marks[lex] = s                                   # the strictest mark over every list
        _cache = (str(data.get("version") or ""), marks)
    return _cache

def schedule_of(canonical) -> str:
    """"H", "H1", "X" or "" for a lexicon canonical (a brand row passes its lexicon_match)."""
    return _load()[1].get(str(canonical or "").casefold(), "")

def generics_version() -> str:
    return _load()[0]

def reset():
    """Forget the loaded file (tests, and a deploy that replaces it)."""
    global _cache
    _cache = None

def reload():
    """Forget the loaded file and read it again now (a sync or promote in this process; a running server still needs a restart)."""
    reset()
    _load()
