"""The suite must stay offline: a developer's .env must never put a real provider key into settings."""
import os

from dotenv import find_dotenv, load_dotenv

from doctor_dictation import config


def test_dotenv_keys_do_not_leak_into_settings(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-should-not-leak\nDEEPSEEK_API_KEY=sk-ds-should-not-leak\n")
    monkeypatch.chdir(tmp_path)
    # create_app() calls load_dotenv() (finds the checkout .env); here usecwd points it at the temp .env.
    assert load_dotenv(find_dotenv(usecwd=True))
    assert find_dotenv(usecwd=True) == str(tmp_path / ".env")
    s = config.get_settings()          # exactly how the app reads settings
    assert os.environ["OPENAI_API_KEY"] == ""
    assert s.openai_api_key == "" and s.deepseek_api_key == ""
    assert config.build_settings().openai_api_key == ""
