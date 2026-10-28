"""User rule: no source file over 500 lines. Also: the uvicorn entry point is a FastAPI app.

Run:  .venv/bin/python -m pytest tests/test_file_sizes.py -q
"""
from pathlib import Path

from fastapi import FastAPI

import doctor_dictation
import doctor_dictation.main as main

LIMIT = 500


def test_no_python_file_over_500_lines():
    root = Path(doctor_dictation.__file__).parent
    sizes = {
        str(p.relative_to(root)): len(p.read_text().splitlines())
        for p in root.rglob("*.py")
    }
    too_big = {name: n for name, n in sizes.items() if n > LIMIT}
    assert too_big == {}, f"files over {LIMIT} lines: {too_big}"


def test_main_app_is_a_fastapi_app():
    assert isinstance(main.app, FastAPI)
