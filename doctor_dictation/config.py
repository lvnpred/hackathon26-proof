"""Central app settings (P0-2).

Single source of truth for configuration. Non-secret settings are read from the
environment with the **same defaults ``main.py`` used before this task** (so
behavior is unchanged); the secret settings are resolved through
:mod:`secret_loader` (env-var-present beats the secrets file -- see that module).

Stdlib only. Deliberately no ``pydantic-settings`` / DI framework.

The settings list below was derived by reading ``doctor_dictation/main.py`` (the
``os.getenv`` reads that preceded this task) plus ``DB_PATH`` from
``doctor_dictation/db/__init__.py``. ``db/__init__.py`` keeps its own env read on
purpose (monkeypatch-friendly, avoids churn); ``db_path`` is surfaced here for
completeness.
"""
import dataclasses
import os
import sys
from dataclasses import dataclass

from doctor_dictation.secret_loader import load_secret, secret_presence


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of resolved configuration."""

    # --- STT (non-secret) ---
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    stt_engine: str

    # --- uploads (non-secret) ---
    max_audio_bytes: int
    stt_chain: tuple[str, ...]  # () = derive from stt_engine
    allow_stub_providers: bool

    # --- LLM (non-secret, except the keys) ---
    llm_provider: str
    llm_model: str
    llm_vision_model: str
    llm_seed: int
    deepseek_seed: int
    openai_base_url: str
    deepseek_model: str
    deepseek_base_url: str

    # --- secrets (resolved via secret_loader.load_secret) ---
    openai_api_key: str
    deepseek_api_key: str

    # --- persistence (db/__init__.py still reads DB_PATH directly) ---
    # "" means "unset"; the effective default is doctor_dictation/data/app.db, owned by
    # db/__init__.py (this field intentionally carries only the raw env value).
    db_path: str

    # --- ACC2 accuracy flags (off by default; enable only if the benchmark gains) ---
    stt_use_hints: bool = False
    stt_hint_limit: int = 70
    stt_trim_silence: bool = False

    # --- letterhead templates (B2b) ---
    template_uploads_per_day: int = 10
    template_draft_ttl_hours: int = 24
    template_max_image_bytes: int = 8 * 1024 * 1024
    template_max_pixels: int = 40_000_000

    # --- display (I3): one date locale for the page and the printed sheet; unknown values fall back in core/datefmt.py ---
    date_locale: str = "en-IN"


def _int_env(name: str, default: int) -> int:
    """Parse an int env var; absent/blank/invalid -> ``default``."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    return default if raw is None or not raw.strip() else raw.strip().lower() in ("1", "true", "yes", "on")


def _csv_env(name: str) -> tuple[str, ...]:
    return tuple(p.strip().lower() for p in os.getenv(name, "").split(",") if p.strip())


def build_settings() -> Settings:
    """Build a fresh :class:`Settings` from the current environment."""
    deepseek_seed = _int_env("DEEPSEEK_SEED", 7)
    return Settings(
        whisper_model=os.getenv("WHISPER_MODEL", "small.en"),
        whisper_device=os.getenv("WHISPER_DEVICE", "cpu"),
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        stt_engine=os.getenv("STT_ENGINE", "auto").strip().lower(),
        max_audio_bytes=_int_env("MAX_AUDIO_BYTES", 10 * 1024 * 1024),
        stt_chain=_csv_env("STT_CHAIN"),
        allow_stub_providers=_bool_env("ALLOW_STUB_PROVIDERS"),
        llm_provider=os.getenv("LLM_PROVIDER", "openai").strip().lower(),
        llm_model=os.getenv("LLM_MODEL", "gpt-6-luna"),
        llm_vision_model=os.getenv("LLM_VISION_MODEL", "").strip(),
        # Original: int(os.getenv("LLM_SEED", os.getenv("DEEPSEEK_SEED", "7")))
        llm_seed=_int_env("LLM_SEED", deepseek_seed),
        deepseek_seed=deepseek_seed,
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        openai_api_key=load_secret("OPENAI_API_KEY"),
        deepseek_api_key=load_secret("DEEPSEEK_API_KEY"),
        db_path=os.getenv("DB_PATH", ""),
        stt_use_hints=os.getenv("STT_USE_HINTS", "").strip().lower() in ("1", "true", "yes", "on"),
        stt_hint_limit=_int_env("STT_HINT_LIMIT", 70),
        stt_trim_silence=os.getenv("STT_TRIM_SILENCE", "").strip().lower() in ("1", "true", "yes", "on"),
        template_uploads_per_day=_int_env("TEMPLATE_UPLOADS_PER_DAY", 10),
        template_draft_ttl_hours=_int_env("TEMPLATE_DRAFT_TTL_HOURS", 24),
        template_max_image_bytes=_int_env("TEMPLATE_MAX_IMAGE_BYTES", 8 * 1024 * 1024),
        template_max_pixels=_int_env("TEMPLATE_MAX_PIXELS", 40_000_000),
        date_locale=os.getenv("DATE_LOCALE", "").strip() or "en-IN",
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide settings snapshot (built once, cached)."""
    global _settings
    if _settings is None:
        _settings = build_settings()
    return _settings


def override_settings(monkeypatch, **fields) -> Settings:
    """Test helper: replace the cached settings for the life of `monkeypatch`."""
    new = dataclasses.replace(get_settings(), **fields)
    monkeypatch.setattr(sys.modules[__name__], "_settings", new)
    return new
