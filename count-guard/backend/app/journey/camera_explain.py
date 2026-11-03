"""The drafted explanation of a camera case's discrepancies (spec §6.4, §6.7, CG-26) and its count sheet (CG-27).

Which writer drafts it: Spark Open when BASETEN_API_KEY is set (and SPARK_LIVE is not turned off), else Muse Spark
1.3 through the Meta key when the spark switch is live, else the fixed template sentences labelled Prepared. A call
that fails also falls back to the template, labelled Prepared. The explanation is advice text: it never writes a
swab count, and the count sheet records counts and evidence only.
"""

from __future__ import annotations

import dataclasses
import re
import time
from pathlib import Path

import httpx

from app.adapters.spark import SparkAdapter
from app.agent.reconciler import explain_case
from app.config import Settings
from app.core.ledger import open_discrepancies
from app.journey import switches
from app.journey.live import call_of
from app.journey.evidence_payload import evidence_of
from app.report.count_sheet import write_count_sheet

_EVIDENCE = re.compile(r"\s*Evidence [^.]*(?:\.|$)")
_LIVE_WORD = {"spark": "muse-spark-1.3", "spark-open": "muse-spark-open"}  # the source words live.mode_of knows
_FAILED = (httpx.HTTPError, RuntimeError, ValueError, KeyError, TypeError)


def _spark13(settings: Settings):
    """Spark 1.3 answers the reconciler's prompt as text (no tool loop): the summary already carries the figures."""
    adapter = SparkAdapter(settings)

    def complete(messages: list[dict], tools: list[dict]) -> dict:
        prompt = "\n\n".join(str(m.get("content") or "") for m in messages if m.get("content"))
        return {"role": "assistant", "content": adapter.write(prompt)}

    return complete


def _writer(settings: Settings) -> str:
    if settings.spark_open_configured and settings.spark_live is not False:
        return "spark-open"
    return "spark" if switches.is_live(settings, "spark") else "prepared"


def staff_text(narrative: str) -> str:
    """The explanation as staff read it: evidence ids stay in the count sheet and the Inspector."""
    return " ".join(_EVIDENCE.sub("", narrative or "").split()) or "The camera case is closed."


def explain(store, settings: Settings, case_id: str) -> dict:
    """{narrative, text, source ("spark" | "prepared"), model, trace, calls, why}. Never a count.

    `calls` is the writer's one call: live with its own source word, or failed when it raised or its sentences did
    not pass the check (the template then stands in, and `source` stays "prepared" as the page labels it)."""
    no_open = dataclasses.replace(settings, baseten_api_key="")  # the reconciler then uses only what is passed in
    writer = _writer(settings)
    out, why, ms = None, "", None
    if writer != "prepared":
        start = time.monotonic()
        try:
            if writer == "spark-open":
                out = explain_case(store, settings, case_id)
            else:
                out = explain_case(store, no_open, case_id, complete=_spark13(settings))
                out["model"] = out["model"].replace(settings.spark_open_model, settings.spark_model)
        except _FAILED as exc:
            out, why = None, f"model call failed ({type(exc).__name__})"
        ms = round((time.monotonic() - start) * 1000)
        if out is not None and out["model"] == "template":
            why = "model reply not usable"
    if out is None or out["model"] == "template":
        out = explain_case(store, no_open, case_id)
        source = "prepared"
    else:
        source = "spark"
    calls = [] if writer == "prepared" else [call_of(writer, settings, _LIVE_WORD[writer] if source == "spark" else "failed", ms)]
    return {"narrative": out["narrative"], "text": staff_text(out["narrative"]), "source": source,
            "model": out["model"], "trace": out["trace"], "calls": calls, "why": why}


def evidence(explained: dict, case_id: str) -> dict:
    """The explanation's evidence (§4.2): the case it read, the writer's call (live or failed, with why), the text
    staff see. No writer configured: no model was used, the template wrote it."""
    calls = explained["calls"]
    live_reply = bool(calls) and explained["source"] == "spark"
    used = {"text": explained["text"], "fallback": None if live_reply else "template", "why": explained["why"]}
    return evidence_of("camera.explain", inputs={"case_id": case_id}, reply=explained["narrative"] if live_reply else None,
                       used=used, calls=calls)


def write_sheet(store, settings: Settings, case_id: str, explained: dict, ledger: list[dict]) -> Path:
    """The count-sheet PDF in the data dir (never the repo), saved as the case's report."""
    path = settings.report_dir / case_id / "count-sheet.pdf"
    write_count_sheet(
        path,
        case=store.get_case(case_id),
        ledger=ledger,
        discrepancies=open_discrepancies(store.events(case_id)),
        narrative=explained["narrative"],
        model=explained["model"],
        trace=explained["trace"],
    )
    store.save_report(case_id, explained["narrative"], str(path), explained["model"])
    if explained["source"] != "prepared":
        store.log_model_call(explained["model"], "app/journey/camera_explain.py", "camera discrepancy explanation", case_id)
    return path
