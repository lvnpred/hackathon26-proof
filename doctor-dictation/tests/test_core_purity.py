"""`doctor_dictation.core` stays pure: stdlib only, no I/O layers.

Parses every module's source with `ast`, so imports inside functions (lazy
imports) are caught as well as top-level ones.

Run:  .venv/bin/python -m pytest tests/test_core_purity.py -q
"""
import ast
import sys
from pathlib import Path

import doctor_dictation.core as core_pkg
import doctor_dictation.core.determinism as determinism
import doctor_dictation.api.format as format_api
from doctor_dictation.core import fallback

CORE_DIR = Path(core_pkg.__file__).resolve().parent
FORBIDDEN = (
    "fastapi",
    "httpx",
    "sqlite3",
    "doctor_dictation.providers",
    "doctor_dictation.db",
    "doctor_dictation.api",
    "doctor_dictation.pdf",
)
DYNAMIC_IMPORTERS = {"__import__", "import_module"}


def _imported_names(source: str) -> list[str]:
    """Absolute dotted names imported anywhere in `source`; relative imports are skipped."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
            names += [f"{node.module}.{a.name}" for a in node.names]
        elif isinstance(node, ast.Call):
            fn = node.func
            called = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if called in DYNAMIC_IMPORTERS:
                names.append(f"<dynamic import via {called}>")
    return names


def _violations(source: str) -> list[str]:
    bad = []
    for name in _imported_names(source):
        if name.startswith("<dynamic"):
            bad.append(name)
        elif any(name == f or name.startswith(f + ".") for f in FORBIDDEN):
            bad.append(name)
        elif name.split(".")[0] not in sys.stdlib_module_names and not name.startswith("doctor_dictation.core"):
            bad.append(name)
    return bad


def _core_sources() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(CORE_DIR.glob("*.py"))}


def test_core_modules_import_no_io_layer_and_only_stdlib():
    sources = _core_sources()
    assert {"determinism.py", "correction.py", "safety.py", "fallback.py"} <= set(sources)
    found = {name: _violations(src) for name, src in sources.items()}
    assert {k: v for k, v in found.items() if v} == {}


def test_checker_catches_lazy_forbidden_and_non_stdlib_imports():
    lazy = "def f():\n    import httpx\n    from doctor_dictation.db import connect\n"
    assert _violations(lazy) == ["httpx", "doctor_dictation.db", "doctor_dictation.db.connect"]
    assert _violations("import json\nfrom pathlib import Path\nfrom . import sibling\n") == []
    assert _violations("import requests\n") == ["requests"]
    assert _violations("import importlib\nimportlib.import_module('sqlite3')\n") == [
        "<dynamic import via import_module>"
    ]


def test_lexicon_lives_inside_core_and_loads():
    assert determinism.LEXICON_PATH == CORE_DIR / "lexicon" / "drugs.json"
    assert determinism.LEXICON_PATH.is_file()
    assert determinism.lexicon_size() >= 300


def test_format_route_uses_the_core_fallback_format():
    assert format_api.fallback_format is fallback.fallback_format
    assert fallback.fallback_format("").get("rx") == []
