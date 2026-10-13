# Plan E: ElevenLabs Scribe v2 Medical STT Provider

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Add `elevenlabs` as an opt-in cloud STT provider (`scribe_v2_medical`) with fallback to the existing chain.

**Architecture:** One class `ElevenLabsStt` implementing `SttProvider` (`providers/stt/base.py`), registered in `STT_REGISTRY`. Opt-in through `STT_CHAIN=elevenlabs,openai,faster-whisper`; the default chain is unchanged until a benchmark on consented clips shows a gain.

**Tech Stack:** Python 3.12, httpx (already a dependency), pytest. No network in tests.

**Spec:** platform foundation spec section 12 (STT providers) and contracts 4.2. **Status: written 2026-10-13, NOT approved for execution until the user answers the open decisions below. Optional, like C1.**

**Prerequisite:** B1c applied (it is). Run after B2d, before D0a, or earlier if the user asks. Adds about 12 tests.

## Facts from ElevenLabs docs (verify again before coding; not tested against the live API)
- `POST https://api.elevenlabs.io/v1/speech-to-text`, multipart, header `xi-api-key`; regional base URLs exist (US, EU, India, Singapore).
- Fields: `model_id=scribe_v2_medical` (batch only), `file`, optional `language_code`, `keyterms` (up to 1,000, each under 50 characters and at most 5 words, +20% surcharge), `enable_logging=false` = zero retention (Enterprise only). HIPAA-eligible; BAA only for Enterprise.
- 200 body: `text`, `language_code`, `audio_duration_secs`; 422 carries `detail[]`.
- Unverified: price, accent performance, acceptance of browser webm/opus (Task 3 checks with a real key).

## Open decisions (user)
1. Opt-in via `STT_CHAIN` (recommended) or make it the default.
2. Base URL region, and whether PHI may go to ElevenLabs without an Enterprise BAA (until settled: demo audio only).
3. A trial key for the live smoke test.

## Global Constraints
- No file over 500 lines; never commit or push; leave changes uncommitted.
- Never print or store key values; tests stub httpx and use `override_settings`; run with `OPENAI_API_KEY= ELEVENLABS_API_KEY=`.
- Existing status codes and JSON shapes of `/api/transcribe` do not change.

## Review Focus
1. A Scribe outage must fall back to OpenAI/local, not stop the chain (Task 1).
2. The key must never appear in an error body (Task 2).
3. Hints with long or many-word entries must be dropped, not sent (Task 2).

---

### Task 1: Cloud failures fall back (existing defect Scribe would expose)
**Files:** Modify `doctor_dictation/providers/stt/factory.py` (`failure_response`, the line `local = [e for n, e in real if n != "openai"]`); Test `tests/test_stt_factory.py` (or the file holding the `failure_response` tests; `grep -rn failure_response tests`).
- [ ] **Step 1: failing test.** Chain `("elevenlabs", "openai")`, `SttChainError([("elevenlabs", SttError("x")), ("openai", SttUnavailable("no key"))])` must give `502` with `fallback: "browser"`, not `500`. Run: expect it to return 500.
- [ ] **Step 2:** Add `CLOUD = {"openai", "elevenlabs"}` next to `DISPLAY`; change the condition to `n not in CLOUD`. Run the STT tests: all green, the new test passes.
- [ ] **Step 3:** Also assert a chain where elevenlabs fails then openai answers returns the OpenAI transcript through `FallbackStt.transcribe` (fake providers).

### Task 2: Settings and the provider
**Files:** Create `doctor_dictation/providers/stt/elevenlabs.py`, `tests/test_stt_elevenlabs.py`; Modify `doctor_dictation/config.py`, `providers/stt/factory.py`.
**Interfaces:** Produces `Settings.elevenlabs_api_key` (via `load_secret("ELEVENLABS_API_KEY")`), `stt_elevenlabs_model: str = "scribe_v2_medical"` (`STT_ELEVENLABS_MODEL`), `elevenlabs_base_url: str = "https://api.elevenlabs.io"` (`ELEVENLABS_BASE_URL`), `stt_language: str = "en"` (`STT_LANGUAGE`, blank = auto-detect); `ElevenLabsStt(settings)` with `name = "elevenlabs"`; registry entry and `DISPLAY["elevenlabs"] = "elevenlabs-scribe"`.
- [ ] **Step 1: failing tests** (httpx patched at `doctor_dictation.providers.stt.elevenlabs.httpx.AsyncClient`, same style as the OpenAI provider tests):
  1. `test_posts_model_key_header_and_returns_transcript`: asserts URL `<base>/v1/speech-to-text`, header `xi-api-key`, `data["model_id"] == "scribe_v2_medical"`, `Transcript.engine == "elevenlabs-scribe"`, `duration` from `audio_duration_secs`.
  2. `test_no_key_is_unavailable`: `SttUnavailable`, `available() is False`.
  3. `test_http_error_is_stterror_and_key_redacted`: 401 body echoing the key contains `[redacted]` and not the key.
  4. `test_422_detail_is_summarised_and_capped_at_300`.
  5. `test_200_non_json_is_stterror`.
  6. `test_network_exception_is_stterror`.
  7. `test_keyterms_sent_only_when_valid`: hints `["Cefixime", "a b c d e f", "x"*60, "Augmentin 625"]` send only `Cefixime` and `Augmentin 625` as repeated `keyterms` form fields; no hints sends no `keyterms`.
  8. `test_language_code_sent_unless_blank`.
  9. `test_factory_registers_and_unknown_still_raises` and `test_chain_env_selects_elevenlabs_first`.
- [ ] **Step 2: implement**, mirroring `providers/stt/openai.py` line for line: lazy `httpx.AsyncClient(timeout=90)` at call time, `files={"file": (filename, audio, "audio/webm")}`, `data` list of tuples so `keyterms` repeats, redact the key from error bodies, `SttError` for every failure, `SttUnavailable` when no key. Keep the file under 80 lines.
- [ ] **Step 3:** Run `OPENAI_API_KEY= ELEVENLABS_API_KEY= .venv/bin/python -m pytest tests/ -q`: expect N + 12.

### Task 3: Config placeholders, benchmark hook, live check
- [ ] **Step 1:** Add commented placeholders to `.env.example` (`# ELEVENLABS_API_KEY=`, `# STT_CHAIN=elevenlabs,openai,faster-whisper`, `# STT_ELEVENLABS_MODEL=scribe_v2_medical`, `# ELEVENLABS_BASE_URL=`, `# STT_LANGUAGE=en`). Never write the key into `.env` for the user.
- [ ] **Step 2:** `doctor_dictation/bench/run.py`: accept `--engine elevenlabs` by resolving through `make_stt` with a one-provider chain; test with the stub (offline).
- [ ] **Step 3 (only with the user's key):** transcribe one short TTS clip in webm/opus via the route with `STT_CHAIN=elevenlabs`; record accepted or rejected container, latency, and the engine name in `/api/health`. If webm is rejected, add a decode-to-WAV step in this provider only and ledger a Ruling.
- [ ] **Step 4:** Leave uncommitted; ledger deferred items (benchmark comparison needs 50 to 100 consented clips; default chain unchanged).

**Not in scope:** realtime streaming, diarization, entity detection or PHI redaction, webhook mode, changing the default chain.
