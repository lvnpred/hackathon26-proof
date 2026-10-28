"""Silence trimming before upload (ACC2). Fail-soft: any problem returns the input object."""
import logging
import os
import shutil
import subprocess

log = logging.getLogger(__name__)

TIMEOUT_S = 20.0
MIN_OUTPUT_BYTES = 400   # an all-silent input yields a ~137-byte header-only Ogg
FILTER = ("silenceremove=start_periods=1:start_duration=0.1:start_threshold=-45dB:start_silence=0.3"
          ":stop_periods=-1:stop_duration=0.3:stop_threshold=-45dB:stop_silence=0.3")
_warned_missing = False


def _ffmpeg() -> str | None:
    return shutil.which(os.getenv("FFMPEG_BIN", "ffmpeg"))


def trim_silence(audio: bytes, filename: str) -> bytes:
    """Ogg/Opus bytes with long pauses removed, or `audio` itself on any failure.
    Pipes only, no temp files. Blocking: call with asyncio.to_thread."""
    global _warned_missing
    if not audio:
        return audio
    exe = _ffmpeg()
    if exe is None:
        if not _warned_missing:
            _warned_missing = True
            log.warning("silence trim skipped: ffmpeg not found")
        return audio
    cmd = [exe, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-vn",
           "-af", FILTER, "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "32k",
           "-f", "ogg", "pipe:1"]
    try:
        done = subprocess.run(cmd, input=audio, capture_output=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        log.warning("silence trim skipped: ffmpeg timed out after %.0fs", TIMEOUT_S)
        return audio
    except OSError as exc:
        log.warning("silence trim skipped: cannot run ffmpeg (%s)", exc)
        return audio
    if done.returncode != 0 or len(done.stdout) < MIN_OUTPUT_BYTES:
        log.warning("silence trim skipped: ffmpeg exit %s, %d bytes out", done.returncode, len(done.stdout))
        return audio
    log.info("silence trim: %s %d -> %d bytes", filename, len(audio), len(done.stdout))
    return done.stdout
