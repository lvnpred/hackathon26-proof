"""STT benchmark: word error rate, drug-name recall and cost, per provider.

    python -m doctor_dictation.bench.run --manifest tests/stt_bench/manifest.json
        --providers openai,faster-whisper [--hints] [--report out.json]

Manifest: JSON list of {"audio": "clips/a.webm", "reference": "exact text"}, optional
"seconds"; relative paths resolve against the manifest's folder (see
tests/stt_bench/manifest.example.json). Drug names scored: lexicon canonical names
and brands found in each reference.

REAL DATA ONLY: numbers mean something only for 50-100 real, consented,
de-identified dictations. Synthetic or text-to-speech audio is for testing this
harness, never for choosing a provider. Clips, manifest.json and reports/ are
git-ignored; keep them out of git.

Each provider is built alone (stt_chain=(name,)), never as a chain; "stub" is
allowed because you named it (STUB_TRANSCRIPT sets its text). --hints sends the
same list the app sends (core.hints.build_hints); --trim applies the app's silence trim. Mean WER is per-clip. Clip length: manifest "seconds",
else the WAV header, else unknown (browser webm has none: set "seconds"); unknown
makes seconds and cost "n/a". Exit 0 when the run completes, 2 for a bad manifest.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import wave
from dataclasses import replace
from pathlib import Path

from doctor_dictation.bench.manifest import Clip, ManifestError, load_manifest
from doctor_dictation.bench.metrics import drug_recall, wer
from doctor_dictation.audio.trim import trim_silence
from doctor_dictation.config import get_settings
from doctor_dictation.core.determinism import load_lexicon
from doctor_dictation.core.hints import build_hints
from doctor_dictation.providers.stt.factory import make_stt

# USD per audio minute, list prices NOT CHECKED AGAINST A BILL: confirm before quoting.
# openai = whisper-1; groq = whisper-large-v3 at $0.111/hour (console.groq.com/docs/models,
# 2026-10-19; turbo is $0.04/hour). Groq bills at least 10 s per request. assemblyai =
# universal-3-5-pro $0.21 + keyterms $0.05 per hour (assemblyai.com/pricing, 2026-10-19);
# Medical Mode adds $0.15/hour and universal-2 is $0.15 base: adjust when benchmarking those.
# muse = $0.18/hour, no add-ons (dev.meta.ai pricing, 2026-10-19). Missing shows "n/a".
PRICE_PER_MINUTE: dict[str, float] = {"openai": 0.006, "groq": 0.111 / 60, "assemblyai": 0.26 / 60,
                                      "muse": 0.18 / 60,
                                      "faster-whisper": 0.0, "onnx": 0.0, "stub": 0.0}


def audio_seconds(clip: Clip) -> float | None:
    if clip.seconds is not None:
        return clip.seconds
    try:
        with wave.open(str(clip.audio), "rb") as w:
            return w.getnframes() / w.getframerate()
    except (wave.Error, EOFError, OSError, ZeroDivisionError):  # corrupt header: length unknown
        return None


async def score_provider(name: str, clips: list[Clip], hints: list[str], trim: bool = False) -> dict:
    row = {"provider": name, "clips": len(clips), "failed": 0, "status": "ok", "mean_wer": None,
           "drug_found": 0, "drug_expected": 0, "seconds": None, "cost_usd": None, "results": []}
    try:
        base = get_settings()  # a one-name chain: this provider alone, never a fallback
        provider = make_stt(replace(base, stt_chain=(name,),
                                    allow_stub_providers=base.allow_stub_providers or name == "stub"))
        if not provider.available():
            raise RuntimeError("not available (not installed or no key)")
    except Exception as exc:  # unknown name, stub not allowed, missing key
        row["status"] = f"unavailable: {str(exc)[:120]}"
        return row
    names = [n for e in load_lexicon() for n in [e.get("canonical", ""), *e.get("brands", [])] if n]
    wers, secs = [], []
    for clip in clips:
        item = {"audio": str(clip.audio)}
        row["results"].append(item)
        try:
            data, fname = clip.audio.read_bytes(), clip.audio.name
            if trim:  # exactly what the app does when STT_TRIM_SILENCE is on
                trimmed = await asyncio.to_thread(trim_silence, data, fname)
                if trimmed is not data:
                    data, fname = trimmed, Path(fname).stem + ".ogg"
            text = (await provider.transcribe(data, fname, hints)).text
        except Exception as exc:  # one bad clip must not end the run
            row["failed"] += 1
            item["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            continue
        found, expected = drug_recall(clip.reference, text, names)
        item.update(wer=wer(clip.reference, text), drug_found=found, drug_expected=expected, transcript=text)
        wers.append(item["wer"])
        row["drug_found"] += found
        row["drug_expected"] += expected
        secs.append(audio_seconds(clip))
    if wers:
        row["mean_wer"] = sum(wers) / len(wers)
    if secs and None not in secs:
        row["seconds"] = sum(secs)
        if name in PRICE_PER_MINUTE:
            row["cost_usd"] = row["seconds"] / 60 * PRICE_PER_MINUTE[name]
    return row


def render_table(rows: list[dict]) -> str:
    na = lambda v, f: "n/a" if v is None else format(v, f)
    lines = ["provider | clips ok | mean WER | drug recall | audio sec | est. cost USD"]
    for r in rows:
        if r["status"] != "ok":
            lines.append(f"{r['provider']} | {r['status']} | - | - | - | -")
            continue
        lines.append(f"{r['provider']} | {r['clips'] - r['failed']}/{r['clips']} | {na(r['mean_wer'], '.3f')} | "
                     f"{r['drug_found']}/{r['drug_expected']} | {na(r['seconds'], '.1f')} | {na(r['cost_usd'], '.4f')}")
    lines.append("prices: PRICE_PER_MINUTE in doctor_dictation/bench/run.py (third-party, confirm)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m doctor_dictation.bench.run")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--providers", required=True, help="comma list, e.g. openai,stub")
    parser.add_argument("--hints", action="store_true", help="send the same vocabulary hint list the app sends")
    parser.add_argument("--trim", action="store_true", help="trim silence like STT_TRIM_SILENCE (needs ffmpeg)")
    parser.add_argument("--report", help="also write full results as JSON to this path")
    args = parser.parse_args(argv)
    names = [p.strip() for p in args.providers.split(",") if p.strip()]
    try:
        clips = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 2
    hints = build_hints() if args.hints else []

    async def _all() -> list[dict]:
        return [await score_provider(n, clips, hints, args.trim) for n in names]

    rows = asyncio.run(_all())
    print(render_table(rows))
    if args.report:
        Path(args.report).write_text(json.dumps({"manifest": args.manifest, "hints": args.hints, "trim": args.trim,
                                                 "price_per_minute": PRICE_PER_MINUTE,
                                                 "providers": rows}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    from dotenv import load_dotenv  # a real key is only loaded when run as a CLI

    load_dotenv()
    sys.exit(main())
