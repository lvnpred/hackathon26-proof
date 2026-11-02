"""Which Count Guard files nothing reaches any more (spec §9 "Archiving", A7).

Walks the import graph from the app entry points: the backend from `backend/app/main.py` plus the
tools the Makefile and eval scripts run, the frontend from `src/main.jsx` plus the demo scripts.
A file under `backend/app` or `frontend/src` that no walk reaches is listed; tests never count as
entry points (a test of an archived file moves with it).

    python scripts/archive_set.py [--keep PATH ...]

`--keep` holds back a freeze leftover (U11): the file stays in place, routed but out of the menu.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

# Backend tools that run outside the server: `make day1|cost|baseline|live-check` and eval scripts.
BACKEND_TOOLS = ("day1.py", "spend.py", "baseline.py", "live_check.py")
JS_SUFFIXES = (".js", ".jsx", ".mjs")
JS_IMPORT = re.compile(
    r"""(?:import|export)\s[^'";]*?from\s*['"]([^'"]+)['"]"""  # import x from "y" / export {x} from "y"
    r"""|import\s*['"]([^'"]+)['"]"""  # import "y"
    r"""|import\(\s*['"]([^'"]+)['"]\s*\)"""  # import("y")
)


def _py_module_path(app_root: Path, dotted: str) -> Path | None:
    """`app.journey.api` -> backend/app/journey/api.py (or the package's __init__.py)."""
    parts = dotted.split(".")
    if parts[0] != "app":
        return None
    base = app_root.joinpath(*parts[1:])
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py")
    if (base / "__init__.py").is_file():
        return base / "__init__.py"
    return None


def _py_imports(path: Path, app_root: Path) -> set[Path]:
    tree = ast.parse(path.read_text(encoding="utf8"), filename=str(path))
    package = _package_of(path, app_root)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                module = ".".join(anchor + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            names.append(module)
            # `from app.journey import nudges` imports a submodule, not only a name.
            names += [f"{module}.{alias.name}" for alias in node.names]
    found = set()
    for name in names:
        hit = _py_module_path(app_root, name)
        if hit is not None:
            found.add(hit)
            found |= _parents(hit, app_root)
    return found


def _package_of(path: Path, app_root: Path) -> str:
    """The package a relative import starts from: the module's folder (for __init__.py, itself)."""
    if app_root.parent not in path.parents:
        return ""  # an eval script: only absolute `app.*` imports count
    return ".".join(path.relative_to(app_root.parent).parts[:-1])


def _parents(path: Path, app_root: Path) -> set[Path]:
    """Importing a module runs every enclosing package's __init__.py."""
    out = set()
    folder = path.parent
    while folder != app_root.parent and app_root in [folder, *folder.parents]:
        init = folder / "__init__.py"
        if init.is_file():
            out.add(init)
        folder = folder.parent
    return out


def _js_resolve(source: Path, spec: str) -> Path | None:
    if not spec.startswith("."):
        return None
    base = (source.parent / spec).resolve()
    for candidate in [base, *(Path(f"{base}{s}") for s in JS_SUFFIXES), *(base / f"index{s}" for s in JS_SUFFIXES)]:
        if candidate.is_file() and candidate.suffix in JS_SUFFIXES:
            return candidate
    return None


def _js_imports(path: Path) -> set[Path]:
    text = path.read_text(encoding="utf8")
    found = set()
    for match in JS_IMPORT.finditer(text):
        hit = _js_resolve(path, next(group for group in match.groups() if group))
        if hit is not None:
            found.add(hit)
    return found


def _walk(roots: list[Path], edges) -> set[Path]:
    seen: set[Path] = set()
    todo = [root.resolve() for root in roots if root.is_file()]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        todo += [hit.resolve() for hit in edges(path) if hit.resolve() not in seen]
    return seen


def _is_test(path: Path) -> bool:
    return path.name.endswith((".test.js", ".test.mjs", ".test.jsx")) or path.name.startswith("test_")


def backend_reached(root: Path) -> set[Path]:
    app_root = (root / "backend" / "app").resolve()
    roots = [app_root / "main.py", *(app_root / name for name in BACKEND_TOOLS)]
    roots += [p for p in (root / "eval").rglob("*.py") if not _is_test(p)] if (root / "eval").is_dir() else []
    return _walk(roots, lambda p: _py_imports(p, app_root) if p.suffix == ".py" else set())


def frontend_reached(root: Path) -> set[Path]:
    front = root / "frontend"
    roots = [front / "src" / "main.jsx"]
    scripts = front / "scripts"
    roots += [p for p in scripts.rglob("*") if p.suffix in JS_SUFFIXES and not _is_test(p)] if scripts.is_dir() else []
    return _walk(roots, _js_imports)


def unreachable(root: Path, keep: tuple[Path, ...] | list[Path] = ()) -> list[Path]:
    """Files under backend/app and frontend/src that no entry point imports, minus `keep`."""
    root = root.resolve()
    reached = backend_reached(root) | frontend_reached(root)
    kept = {(root / k).resolve() if not Path(k).is_absolute() else Path(k).resolve() for k in keep}
    candidates = [p for p in (root / "backend" / "app").rglob("*.py") if "__pycache__" not in p.parts]
    candidates += [p for p in (root / "frontend" / "src").rglob("*") if p.suffix in (".js", ".jsx")]
    out = [p.resolve() for p in candidates if not _is_test(p) and p.resolve() not in reached]
    return sorted(p.relative_to(root) for p in out if p not in kept)


def tests_importing(root: Path, files: list[Path]) -> list[Path]:
    """Frontend tests that import any of `files`: they move to the archive with them."""
    root = root.resolve()
    gone = {(root / f).resolve() for f in files}
    tests = [p for p in (root / "frontend").rglob("*.test.*") if "node_modules" not in p.parts]
    return sorted(t.relative_to(root) for t in tests if _js_imports(t) & gone)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", action="append", default=[], help="a freeze leftover to keep in place")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    args = parser.parse_args(argv)
    root = Path(args.root)
    files = unreachable(root, keep=[Path(k) for k in args.keep])
    for path in files:
        print(path)
    for path in tests_importing(root, files):
        print(f"{path}  (test of an unreachable file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
