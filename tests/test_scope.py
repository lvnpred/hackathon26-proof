"""Request scope: flag, slug safety, context handling and thread behaviour. Offline."""
import asyncio
import threading

import pytest

from doctor_dictation import scope as S


def test_multi_clinic_flag_defaults_off_and_reads_env_at_call_time(monkeypatch):
    monkeypatch.delenv("MULTI_CLINIC", raising=False)
    assert S.multi_clinic_enabled() is False
    for on in ("1", "true", "YES", "On"):
        monkeypatch.setenv("MULTI_CLINIC", on)
        assert S.multi_clinic_enabled() is True, on
    for off in ("", "0", "no", "false", "banana"):
        monkeypatch.setenv("MULTI_CLINIC", off)
        assert S.multi_clinic_enabled() is False, off


def test_data_root_follows_data_dir_env(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    assert S.data_root() == S.DEFAULT_DATA_DIR
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert S.data_root() == tmp_path.resolve()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", "rel/data")
    assert S.data_root().is_absolute() and S.data_root() == (tmp_path / "rel" / "data").resolve()
    assert S.clinic_dir("rao") == (tmp_path / "rel" / "data" / "clinics" / "rao").resolve()


def test_unsafe_slugs_are_rejected():
    bad = ["", "a", "RAO", "rao\n", "../x", "a/b", "/abs", "-rao", "rao_clinic", "r" * 32, "rao clinic", "räo", None, 7]
    for slug in bad:
        assert S.valid_slug(slug) is False, slug
        with pytest.raises(ValueError):
            S.Scope(slug)
        with pytest.raises(ValueError):
            S.clinic_dir(slug)
    assert S.valid_slug("rao") and S.valid_slug("iyer-2") and S.valid_slug("r" * 31)


def test_use_scope_sets_and_restores_including_nested():
    assert S.current_scope() is None
    outer, inner = S.Scope("rao", 1, "dr.rao", "doctor"), S.Scope("iyer")
    with S.use_scope(outer):
        assert S.require_scope() is outer
        with S.use_scope(inner):
            assert S.require_scope() is inner
            assert inner.username == "system"
        assert S.current_scope() is outer
    assert S.current_scope() is None


def test_require_scope_raises_without_scope():
    with pytest.raises(S.NoScope):
        S.require_scope()
    assert issubclass(S.NoScope, RuntimeError)


def test_scope_survives_to_thread_but_not_a_bare_thread():
    async def go():
        with S.use_scope(S.Scope("rao")):
            via_to_thread = await asyncio.to_thread(S.current_scope)
            box = []
            t = threading.Thread(target=lambda: box.append(S.current_scope()))
            t.start()
            t.join()
            return via_to_thread, box[0]

    via_to_thread, via_bare = asyncio.run(go())
    assert via_to_thread == S.Scope("rao")
    assert via_bare is None
