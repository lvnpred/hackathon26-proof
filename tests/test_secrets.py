"""Secrets/settings tests (P0-2).

Offline, stdlib only. Covers the exact precedence chain and proves no secret
VALUE is ever exposed through the health payload.
"""
import json

import doctor_dictation.config as C
import doctor_dictation.secret_loader as S


# --- precedence: env present (even "") beats the secrets file --------------

def test_env_present_nonempty_wins(monkeypatch, tmp_path):
    f = tmp_path / "secrets.json"
    f.write_text(json.dumps({"MY_KEY": "from-file"}), encoding="utf-8")
    monkeypatch.setenv("MY_KEY", "from-env")
    assert S.load_secret("MY_KEY", path=f) == "from-env"


def test_env_present_empty_beats_file(monkeypatch, tmp_path):
    """The key integration rule: an empty-but-PRESENT env var wins.

    This is what lets the offline determinism tests force 'no secret' even if a
    secrets file exists on the machine.
    """
    f = tmp_path / "secrets.json"
    f.write_text(json.dumps({"MY_KEY": "from-file"}), encoding="utf-8")
    monkeypatch.setenv("MY_KEY", "")
    assert S.load_secret("MY_KEY", path=f) == ""


def test_env_absent_falls_through_to_file(monkeypatch, tmp_path):
    f = tmp_path / "secrets.json"
    f.write_text(json.dumps({"MY_KEY": "from-file"}), encoding="utf-8")
    monkeypatch.delenv("MY_KEY", raising=False)
    assert S.load_secret("MY_KEY", path=f) == "from-file"


def test_env_absent_no_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.delenv("MY_KEY", raising=False)
    assert S.load_secret("MY_KEY", path=tmp_path / "missing.json") == ""


def test_secrets_file_path_env_override(monkeypatch, tmp_path):
    f = tmp_path / "custom.json"
    f.write_text(json.dumps({"MY_KEY": "custom"}), encoding="utf-8")
    monkeypatch.delenv("MY_KEY", raising=False)
    monkeypatch.setenv("SECRETS_FILE", str(f))
    assert S.load_secret("MY_KEY") == "custom"


def test_corrupt_secrets_file_is_ignored(monkeypatch, tmp_path):
    f = tmp_path / "secrets.json"
    f.write_text("{not valid json", encoding="utf-8")
    monkeypatch.delenv("MY_KEY", raising=False)
    assert S.load_secret("MY_KEY", path=f) == ""


# --- presence report (booleans only) ---------------------------------------

def test_secret_presence_booleans(monkeypatch, tmp_path):
    f = tmp_path / "secrets.json"
    f.write_text(json.dumps({"FROM_FILE": "x"}), encoding="utf-8")
    monkeypatch.setenv("FROM_ENV", "y")
    monkeypatch.setenv("EMPTY_ENV", "")
    monkeypatch.delenv("FROM_FILE", raising=False)
    out = S.secret_presence(
        ("FROM_ENV", "EMPTY_ENV", "FROM_FILE", "MISSING"), path=f
    )
    assert out == {"FROM_ENV": True, "EMPTY_ENV": False,
                   "FROM_FILE": True, "MISSING": False}
    assert all(isinstance(v, bool) for v in out.values())


def test_secret_presence_overrides_snapshot():
    # overrides let the health payload reflect the resolved settings snapshot
    # (monkeypatch-friendly) without re-reading env at request time.
    out = S.secret_presence(
        ("A", "B"), overrides={"A": "value", "B": ""}
    )
    assert out == {"A": True, "B": False}


# --- secure_permissions: best effort, honest on Windows --------------------

def test_secure_permissions_never_raises(tmp_path):
    f = tmp_path / "secrets.json"
    f.write_text("{}", encoding="utf-8")
    # Windows cannot express POSIX 0600 -> returns False, never raises.
    assert S.secure_permissions(f) in (True, False)
    assert S.secure_permissions(tmp_path / "nope.json") is False


# --- config.py settings ----------------------------------------------------

def test_build_settings_defaults(monkeypatch):
    for name in ("WHISPER_MODEL", "WHISPER_DEVICE", "WHISPER_COMPUTE_TYPE",
                 "OPENAI_BASE_URL", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL",
                 "LLM_PROVIDER", "LLM_MODEL", "LLM_SEED", "DEEPSEEK_SEED",
                 "STT_ENGINE", "DB_PATH", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SECRETS_FILE", "does-not-exist.json")
    s = C.build_settings()
    assert s.whisper_model == "small.en"
    assert s.whisper_device == "cpu"
    assert s.whisper_compute_type == "int8"
    assert s.openai_base_url == "https://api.openai.com/v1"
    assert s.deepseek_model == "deepseek-chat"
    assert s.deepseek_base_url == "https://api.deepseek.com"
    assert s.llm_provider == "openai"
    assert s.llm_model == "gpt-6-luna"
    assert s.llm_seed == 7
    assert s.deepseek_seed == 7
    assert s.stt_engine == "auto"
    assert s.openai_api_key == ""
    assert s.deepseek_api_key == ""


def test_build_settings_reads_secret_from_file(monkeypatch, tmp_path):
    f = tmp_path / "secrets.json"
    f.write_text(json.dumps({"OPENAI_API_KEY": "sk-file"}), encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SECRETS_FILE", str(f))
    s = C.build_settings()
    assert s.openai_api_key == "sk-file"


def test_build_settings_provider_normalized(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "  DeepSeek ")
    monkeypatch.setenv("STT_ENGINE", " ONNX ")
    s = C.build_settings()
    assert s.llm_provider == "deepseek"
    assert s.stt_engine == "onnx"


def test_get_settings_is_cached(monkeypatch):
    assert C.get_settings() is C.get_settings()


# --- health: presence booleans only, never values --------------------------

def test_health_reports_presence_booleans_and_no_values(monkeypatch):
    from fastapi.testclient import TestClient
    import doctor_dictation.main as M
    from doctor_dictation.config import override_settings

    secret = "sk-super-secret-value-do-not-leak"
    override_settings(monkeypatch, openai_api_key=secret, deepseek_api_key="")
    h = TestClient(M.app).get("/api/health").json()
    assert h["openai_configured"] is True
    assert h["deepseek_configured"] is False
    assert isinstance(h["openai_configured"], bool)
    # No secret VALUE anywhere in the serialized health response.
    assert secret not in json.dumps(h)
