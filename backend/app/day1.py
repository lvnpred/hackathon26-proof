"""Day-1 go / no-go from the published API docs. Does not spend credits."""

from __future__ import annotations

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    print("Count Guard day-1 check. No model call is made.")
    print()
    print("SAM 3.1: uploaded video or a still image on POST /v1/responses.")
    print("  A live frame socket is not in the docs. Live mode will chunk frames into a short mp4.")
    print("  Object ids hold inside one response. A new call re-links by label and position and raises R5.")
    print(f"  Key configured: {settings.sam_configured}. Model: {settings.sam_model}.")
    print()
    print("Muse Voice Transcribe: turn-level startMs and endMs. Word-level timestamps are not provided.")
    print("  Turn times cover the 30 second R4 window.")
    print(f"  Key configured: {settings.voice_configured}. Model: {settings.voice_model}.")
    print()
    print("Muse Spark Open: Baseten documents tool calling on chat completions.")
    print("  That is not confirmed until this process makes a call with a key.")
    print(f"  Key configured: {settings.spark_open_configured}. Model: {settings.spark_open_model}.")
    print(f"  Base: {settings.spark_open_base}.")
    print()
    if settings.sam_configured and settings.voice_configured and settings.spark_open_configured:
        print("Keys are present. A paid call still needs an explicit run, not this check.")
    else:
        print("A key is missing. The count rules still run on scripted perception. make eval")


if __name__ == "__main__":
    main()
