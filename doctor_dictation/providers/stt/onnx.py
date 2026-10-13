"""ONNX Whisper STT engine for Snapdragon X Elite (Adreno GPU / Hexagon NPU).

DEFERRED / NOT NEEDED — no local model is run on this machine; cloud-first STT
plus the faster-whisper fallback covers it. Kept as an import-safe stub so
`STT_ENGINE=onnx` returns 503 rather than crashing. Do not build without a
decision reversal.

Part B / Step 1 scaffold: interface is fixed so `/api/transcribe` can route
here, but model + runtime are NOT bundled. Safe to import anywhere — every
entry point reports unavailable instead of raising ImportError.

Setup (separate ARM64 Python 3.11 venv — QNN EP requirement):
  py -3.11-arm64 -m venv .venv-qnn   (or use existing 3.12-arm64 if your
                                     onnxruntime-qnn wheel supports it)
  .\\.venv-qnn\\Scripts\\python -m pip install -r doctor_dictation\\requirements-onnx.txt
  # install QNN SDK + Hexagon driver >= 30.0.140.0, export Whisper base.en/
  # small.en to ONNX (encoder + decoder) into doctor_dictation/stt_models/<model>/
  # with tokenizer.json + mel config, then set STT_ENGINE=onnx.
"""
from pathlib import Path

from doctor_dictation.providers.stt.base import SttNotImplemented, SttUnavailable

MODEL_DIR = Path(__file__).resolve().parents[2] / "stt_models"
NEEDED_FILES = ("encoder.onnx", "decoder.onnx", "tokenizer.json")


def status():
    """Return (available: bool, detail: str). Never raises."""
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False, "onnxruntime not installed (see doctor_dictation/requirements-onnx.txt)"
    if not MODEL_DIR.is_dir():
        return False, f"model dir missing: {MODEL_DIR} (export Whisper ONNX first)"
    missing = [f for model in sorted(p for p in MODEL_DIR.iterdir() if p.is_dir())
               for f in NEEDED_FILES if not (model / f).exists()]
    if missing:
        return False, f"incomplete ONNX model dir, missing: {missing[:6]}"
    return True, "onnx-whisper ready (greedy decode, temp 0)"


class OnnxStt:
    name = "onnx"

    def __init__(self, settings=None):
        ...

    def available(self) -> bool:
        return status()[0]

    async def transcribe(self, audio, filename, hints=()):
        ok, detail = status()
        if not ok:
            raise SttUnavailable(detail)
        raise SttNotImplemented("ONNX decode loop not implemented yet (Step 1 work item).")
