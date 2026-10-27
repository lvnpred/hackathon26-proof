"""Explain open discrepancies. Retry once. Then use the fixed sentence."""

from __future__ import annotations

import json

from app.adapters.spark_open import SparkOpenAdapter
from app.agent.tools import dispatch, schemas
from app.agent.verifier import check_sentence, template_sentence
from app.config import Settings
from app.core.ledger import ledger_rows, open_discrepancies
from app.store import Store

SYSTEM = (
    "You write one plain sentence per count discrepancy for a research demo. "
    "You do not give medical advice. Never say recommend, should, must, X-ray, "
    "re-explore, probably, inside the patient, order, treatment, dose, or drug. "
    "Use the tools to read the ledger, the track, the frames, and the transcript. "
    "Every number must match the tool result. Cite evidence ids from the tools. "
    "When you are finished, reply with JSON only: "
    '{"sentences":[{"discrepancy_id":"...","text":"...","evidence_ids":["..."],'
    '"claims":{"expected":0,"observed":0}}]}'
)


def explain_case(store: Store, settings: Settings, case_id: str, complete=None) -> dict:
    events = store.events(case_id)
    rows = open_discrepancies(events)
    ledger = ledger_rows(events)
    if not rows:
        text = _clean_narrative(ledger)
        return {
            "narrative": text,
            "sentences": [],
            "model": "template",
            "trace": [],
            "banner": "Research demo. Not for clinical use.",
        }
    if complete is None and not settings.spark_open_configured:
        return _from_templates(rows, ledger, model="template")
    adapter = SparkOpenAdapter(settings, complete=complete)
    trace: list[dict] = []
    sentences = _run_model(store, case_id, adapter, rows, trace)
    verified = _verify_or_template(store, case_id, sentences, rows)
    if any(item["source"] == "template" for item in verified) and complete is not None or settings.spark_open_configured:
        # One retry, with the verifier errors attached.
        failures = [item for item in verified if item["source"] == "template" and item.get("errors")]
        if failures:
            retry_trace: list[dict] = []
            retried = _run_model(store, case_id, adapter, rows, retry_trace, failures=failures)
            trace.extend(retry_trace)
            verified = _verify_or_template(store, case_id, retried, rows, allow_retry=False)
    narrative = " ".join(item["text"] for item in verified)
    model = settings.spark_open_model if any(item["source"] == "muse-spark-open" for item in verified) else "template"
    if any(item["source"] == "muse-spark-open" for item in verified) and any(item["source"] == "template" for item in verified):
        model = f"{settings.spark_open_model}+template"
    return {
        "narrative": narrative,
        "sentences": verified,
        "model": model,
        "trace": trace,
        "banner": "Research demo. Not for clinical use.",
    }


def _run_model(store, case_id, adapter, rows, trace, failures=None) -> list[dict]:
    summary = [
        {
            "id": row["id"],
            "rule_id": row["rule_id"],
            "kind": row["kind"],
            "item_type": row["item_type"],
            "track_id": row.get("track_id"),
            "expected": row.get("expected"),
            "observed": row.get("observed"),
            "figures": row.get("figures"),
            "evidence": row.get("evidence"),
            "status": row["status"],
        }
        for row in rows
    ]
    user = "Discrepancies:\n" + json.dumps(summary)
    if failures:
        user += "\nThe previous sentences failed the check:\n" + json.dumps(failures)
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ]
    tool_defs = schemas()
    for _ in range(4):
        message = adapter.complete(messages, tool_defs)
        tool_calls = message.get("tool_calls") or []
        messages.append(message)
        if not tool_calls:
            return _parse_final(message.get("content") or "")
        for call in tool_calls:
            name = call.get("function", {}).get("name")
            raw_args = call.get("function", {}).get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}
            result = dispatch(store, case_id, name, args)
            trace.append({"tool": name, "arguments": args, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": json.dumps(result),
                }
            )
    return []


def _parse_final(content: str) -> list[dict]:
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end < start:
        return []
    try:
        payload = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return []
    sentences = payload.get("sentences") if isinstance(payload, dict) else None
    if not isinstance(sentences, list):
        return []
    return sentences


def _verify_or_template(store, case_id, sentences, rows, allow_retry: bool = True) -> list[dict]:
    known = store.known_evidence_ids(case_id)
    by_id = {row["id"]: row for row in rows}
    incoming = {item.get("discrepancy_id"): item for item in sentences if isinstance(item, dict)}
    verified = []
    for row in rows:
        candidate = incoming.get(row["id"])
        if candidate:
            evidence_ids = list(candidate.get("evidence_ids") or [])
            claims = candidate.get("claims") or {}
            errors = check_sentence(
                candidate.get("text") or "",
                evidence_ids=evidence_ids,
                known_ids=known,
                figures=row.get("figures") or {},
                claims=claims,
                track_id=row.get("track_id"),
            )
            if not errors:
                verified.append(
                    {
                        "discrepancy_id": row["id"],
                        "text": candidate["text"],
                        "evidence_ids": evidence_ids,
                        "claims": claims,
                        "source": "muse-spark-open",
                    }
                )
                continue
            if allow_retry:
                fallback = template_sentence(row)
                fallback["errors"] = errors
                verified.append(fallback)
                continue
        fallback = template_sentence(row)
        template_errors = check_sentence(
            fallback["text"],
            evidence_ids=fallback["evidence_ids"],
            known_ids=known | set(fallback["evidence_ids"]),
            figures=row.get("figures") or {},
            claims=fallback["claims"],
            track_id=row.get("track_id"),
        )
        if template_errors:
            fallback["text"] = f"{row['rule_id']} {row['item_type']}: ledger record {row['id']}."
            fallback["errors"] = template_errors
        verified.append(fallback)
    return verified


def _from_templates(rows, ledger, model: str) -> dict:
    sentences = [template_sentence(row) for row in rows]
    return {
        "narrative": " ".join(item["text"] for item in sentences),
        "sentences": sentences,
        "model": model,
        "trace": [{"tool": "get_ledger", "arguments": {}, "result": {"ledger": ledger}}],
        "banner": "Research demo. Not for clinical use.",
    }


def _clean_narrative(ledger: list[dict]) -> str:
    if not ledger:
        return "No items were recorded."
    parts = []
    for row in ledger:
        parts.append(
            f"{row['item_type']}: opened {row['opened']}, "
            f"in the bucket {row['bucket']}, on the tray {row['tray']}."
        )
    return " ".join(parts) + " No open discrepancies."
