from doctor_dictation.config import build_settings

def test_acc2_flags_default_off_and_parse(monkeypatch):
    for name in ("STT_USE_HINTS", "STT_HINT_LIMIT", "STT_TRIM_SILENCE"):
        monkeypatch.delenv(name, raising=False)
    s = build_settings()
    assert (s.stt_use_hints, s.stt_hint_limit, s.stt_trim_silence) == (False, 70, False)
    monkeypatch.setenv("STT_USE_HINTS", "1")
    monkeypatch.setenv("STT_TRIM_SILENCE", "true")
    monkeypatch.setenv("STT_HINT_LIMIT", "40")
    s = build_settings()
    assert (s.stt_use_hints, s.stt_hint_limit, s.stt_trim_silence) == (True, 40, True)
    monkeypatch.setenv("STT_HINT_LIMIT", "banana")
    assert build_settings().stt_hint_limit == 70
