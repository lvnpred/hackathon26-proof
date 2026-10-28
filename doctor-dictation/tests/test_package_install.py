"""The package is importable from outside the repo root (pip install -e .).

Run:  .venv/bin/python -m pytest tests/test_package_install.py -q
"""
import subprocess
import sys
from pathlib import Path

import doctor_dictation

PACKAGE_DIR = Path(doctor_dictation.__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent


def test_package_imports_from_outside_the_repo_root(tmp_path):
    """-I drops the cwd and PYTHON* env vars, so only the installed package can answer."""
    code = (
        "import doctor_dictation, doctor_dictation.main as m;"
        "print(doctor_dictation.__file__);"
        "print(m.app.title)"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
    )
    assert done.returncode == 0, done.stderr
    printed = done.stdout.splitlines()[0]
    assert Path(printed).resolve() == PACKAGE_DIR / "__init__.py"
    assert (REPO_ROOT / "pyproject.toml").is_file()
