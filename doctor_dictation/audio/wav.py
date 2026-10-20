"""Browser audio (webm/ogg) to mono 16 kHz 16-bit WAV, for engines that accept WAV only (Muse)."""
import os
import shutil
import subprocess

TIMEOUT_S = 20.0


class WavConvertError(Exception):
    """ffmpeg ran but could not convert; str(e) is safe to show."""


def ffmpeg_path() -> str | None:
    return shutil.which(os.getenv("FFMPEG_BIN", "ffmpeg"))


def is_wav(audio: bytes) -> bool:
    return audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"


def to_wav16k(audio: bytes, exe: str) -> bytes:
    """Pipes only, no temp files. Blocking: call with asyncio.to_thread.
    WAV input is re-encoded too, so the sample rate and width always match."""
    cmd = [exe, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-vn",
           "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-map_metadata", "-1", "-f", "wav", "pipe:1"]
    try:
        done = subprocess.run(cmd, input=audio, capture_output=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        raise WavConvertError(f"ffmpeg timed out after {TIMEOUT_S:.0f}s") from e
    except OSError as e:
        raise WavConvertError(f"cannot run ffmpeg: {e}"[:300]) from e
    if done.returncode != 0 or not is_wav(done.stdout):
        raise WavConvertError(f"ffmpeg exit {done.returncode}: {done.stderr.decode(errors='replace')[:200]}")
    return done.stdout
