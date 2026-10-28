"""The shared .env reads the same in both apps: within one file the last line wins."""

from __future__ import annotations

import os

from app.config import load_dotenv


def test_last_line_for_a_key_wins_within_one_file(tmp_path, monkeypatch):
    monkeypatch.delenv("CG_TEST_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("CG_TEST_KEY=\n# CG_TEST_KEY=comment\nCG_TEST_KEY='second'\n", encoding="utf-8")
    load_dotenv(env)
    assert os.environ["CG_TEST_KEY"] == "second"


def test_a_variable_already_set_is_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("CG_TEST_KEY", "shell")
    env = tmp_path / ".env"
    env.write_text("CG_TEST_KEY=file\n", encoding="utf-8")
    load_dotenv(env)
    assert os.environ["CG_TEST_KEY"] == "shell"
