"""Runtime settings. API keys stay in the environment or an ignored .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# The hackathon26 workspace holds the .env shared with Doctor Dictation.
WORKSPACE_ROOT = REPO_ROOT.parent
BANNER = "Research demo. Not for clinical use."

SAM_CONCEPTS = (
    "lap sponge",
    "gauze swab",
    "surgical forceps",
    "scissors",
    "needle holder",
)


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines. Does not override variables already set.

    Within one file the last line for a key wins, as python-dotenv does for Doctor Dictation,
    so the shared .env means the same thing to both apps.
    """
    env_path = path or REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    found: dict[str, str] = {}
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        found[key.strip()] = value.strip().strip("'\"")
    for key, value in found.items():
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    meta_api_key: str
    meta_base: str
    sam_model: str
    voice_model: str
    spark_model: str
    baseten_api_key: str
    spark_open_base: str
    spark_open_model: str
    low_confidence: float
    unannounced_window_ms: int
    lost_after_frames: int
    sam_fps: int
    # Doctor Dictation, read over HTTP for the prescription (option A: no shared code).
    dd_base: str = "http://127.0.0.1:8000"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "countguard.db"

    @property
    def frame_dir(self) -> Path:
        return self.data_dir / "frames"

    @property
    def report_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def sam_configured(self) -> bool:
        return bool(self.meta_api_key)

    @property
    def voice_configured(self) -> bool:
        return bool(self.meta_api_key)

    @property
    def spark_open_configured(self) -> bool:
        return bool(self.baseten_api_key)

    @property
    def spark_configured(self) -> bool:
        return bool(self.meta_api_key)


def get_settings() -> Settings:
    load_dotenv()
    load_dotenv(WORKSPACE_ROOT / ".env")
    data = Path(os.environ.get("COUNT_GUARD_DATA", REPO_ROOT / "data"))
    data.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=data,
        meta_api_key=os.environ.get("MODEL_API_KEY", os.environ.get("META_API_KEY", "")),
        meta_base=os.environ.get("META_API_BASE", "https://api.meta.ai/v1").rstrip("/"),
        sam_model=os.environ.get("SAM_MODEL", "sam-3.1"),
        voice_model=os.environ.get("VOICE_MODEL", "muse-voice-transcribe-1.0"),
        spark_model=os.environ.get("SPARK_MODEL", "muse-spark-1.3"),
        baseten_api_key=os.environ.get("BASETEN_API_KEY", ""),
        spark_open_base=os.environ.get("SPARK_OPEN_BASE", "https://inference.baseten.co/v1").rstrip("/"),
        spark_open_model=os.environ.get(
            "SPARK_OPEN_MODEL", "meta-models/muse-spark-open-1026"
        ),
        low_confidence=float(os.environ.get("LOW_CONFIDENCE_THRESHOLD", "0.45")),
        unannounced_window_ms=int(os.environ.get("UNANNOUNCED_WINDOW_MS", "30000")),
        lost_after_frames=int(os.environ.get("LOST_AFTER_FRAMES", "4")),
        sam_fps=int(os.environ.get("SAM_FPS", "2")),
        dd_base=os.environ.get(
            "DD_BASE_URL", f"http://127.0.0.1:{os.environ.get('DD_PORT', '8000')}"
        ).rstrip("/"),
    )
