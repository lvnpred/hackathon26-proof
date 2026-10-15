"""The browser evidence script (spec 13.1 "Browser", 13.2): it compiles, follows the six demo steps, takes the demo
logins from the seed, and writes only under a git-ignored folder. No browser is started."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "demo_browser.py"


def _assigned(tree, name):
    return next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets))


def test_the_browser_script_compiles_and_writes_only_under_an_ignored_folder():
    src = SCRIPT.read_text(encoding="utf-8")
    compile(src, str(SCRIPT), "exec")
    assert 'EVIDENCE = ROOT / ".superpowers" / "demo-evidence"' in src
    assert ".superpowers/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_the_browser_script_walks_the_six_demo_steps_with_the_seeded_logins():
    src = SCRIPT.read_text(encoding="utf-8")
    steps = _assigned(ast.parse(src), "STEPS")
    assert [s.split("-", 1)[0] for s in steps] == ["1", "2", "3", "4", "5", "6"]
    assert "from doctor_dictation.admin_demo import DOCTORS" in src
    assert "demo-rao-pass" not in src                  # one source for the demo passwords: admin_demo.py


def _script_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("demo_browser", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)           # imports no Playwright: that happens inside main()
    return mod


def test_the_script_refuses_the_default_data_folder_and_single_clinic_data(tmp_path):
    from doctor_dictation import scope
    mod = _script_module()
    assert "default data folder" in mod.check_data_dir(scope.DEFAULT_DATA_DIR)
    assert "default data folder" in mod.check_data_dir(scope.DEFAULT_DATA_DIR / "clinics" / "x")
    assert "not a folder" in mod.check_data_dir(tmp_path / "missing")
    (tmp_path / "app.db").write_bytes(b"")
    assert "single-clinic data (app.db)" in mod.check_data_dir(tmp_path)
    seeded = tmp_path / "seeded"
    (seeded / "clinics").mkdir(parents=True)
    assert mod.check_data_dir(seeded) is None


def test_the_script_only_talks_to_a_loopback_server_unless_told_otherwise():
    mod = _script_module()
    for url in ("http://127.0.0.1:8769", "http://localhost:8765", "http://[::1]:8000"):
        assert mod.check_base(url) is None, url
    for url in ("https://clinic.example.com", "http://10.0.0.5:8000"):
        assert "not a loopback address" in mod.check_base(url), url
        assert mod.check_base(url, allow_remote=True) is None


def test_the_script_cli_exits_2_for_a_refused_folder_or_server(tmp_path, capsys):
    import pytest
    from doctor_dictation import scope
    mod = _script_module()
    for argv in (["--data-dir", str(scope.DEFAULT_DATA_DIR)],
                 ["--data-dir", str(tmp_path), "--base", "http://example.com"]):
        with pytest.raises(SystemExit) as stop:
            mod.main(argv)
        assert stop.value.code == 2
    assert mod.main(["--print-env"]) == 0
    assert "ALLOW_STUB_PROVIDERS" in capsys.readouterr().out


def test_the_script_never_defaults_to_or_writes_under_the_apps_data_folder():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "doctor_dictation/data" not in src and '"data"' not in src
    assert "--data-dir is required" in src                    # no default folder
    assert not [ln for ln in src.splitlines() if ln.startswith(("from playwright", "import playwright"))]   # inside main() only


def test_the_letterhead_pdf_check_expects_both_rao_doctors_and_no_mehta_at_iyer():
    src = SCRIPT.read_text(encoding="utf-8")
    assert 'mehta = ["Dr. S. Mehta"]' in src
    assert '+ (mehta if who == "rao" else [])' in src and '[other] + ([] if who == "rao" else mehta)' in src
