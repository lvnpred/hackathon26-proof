"""The drafted explanation of a camera case's discrepancies (spec §6.4, §6.7, CG-26) and its count sheet (CG-27).

Which writer drafts it: Spark Open when BASETEN_API_KEY is set (and SPARK_LIVE is not turned off), else Muse Spark
1.3 through the Meta key when the spark switch is live, else the fixed template sentences labelled Prepared. A call
that fails also falls back to the template, labelled Prepared. The explanation is advice text: it never writes a
swab count, and the count sheet records counts and evidence only.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import httpx

from app.adapters.spark import SparkAdapter
from app.agent.reconciler import explain_case
from app.config import Settings
from app.core.ledger import open_discrepancies
from app.journey import switches
from app.report.count_sheet import write_count_sheet

_EVIDENCE = re.compile(r"\s*Evidence [^.]*(?:\.|$)")
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
    """{narrative, text, source ("spark" | "prepared"), model, trace}. Never a count."""
    no_open = dataclasses.replace(settings, baseten_api_key="")  # the reconciler then uses only what is passed in
    writer = _writer(settings)
    out = None
    if writer != "prepared":
        try:
            if writer == "spark-open":
                out = explain_case(store, settings, case_id)
            else:
                out = explain_case(store, no_open, case_id, complete=_spark13(settings))
                out["model"] = out["model"].replace(settings.spark_open_model, settings.spark_model)
        except _FAILED:
            out = None
    if out is None or out["model"] == "template":
        out = explain_case(store, no_open, case_id)
        source = "prepared"
    else:
        source = "spark"
    return {"narrative": out["narrative"], "text": staff_text(out["narrative"]), "source": source,
            "model": out["model"], "trace": out["trace"]}


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
