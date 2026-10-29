"""The doctor's prescription, imported from Doctor Dictation or the synthetic demo.

Doctor Dictation stays its own app (option A). This module only reads its saved
document JSON over HTTP. No Doctor Dictation code is copied here.
"""

from __future__ import annotations

import copy

import httpx

from app.morning.lexicon import ground

ROW_FIELDS = ("form", "name", "strength", "dose", "timing", "duration", "instructions")

# Synthetic OPD visit for R. Kumar, 58 M. Shaped like a Doctor Dictation document.
DEMO_DOCUMENT = {
    "document_id": None,
    "structured": {
        "patientName": "R. Kumar (synthetic)",
        "ageSex": "58 M",
        "diagnosis": ["Right inguinal hernia, for elective repair", "Hypertension"],
        "rx": [
            {"form": "Tab.", "name": "Metoprolol", "strength": "25 mg", "dose": "1-0-1",
             "timing": "After food", "duration": "30 days", "instructions": ""},
            {"form": "Tab.", "name": "Amlodipine", "strength": "5 mg", "dose": "1-0-0",
             "timing": "After food", "duration": "30 days", "instructions": ""},
            {"form": "Tab.", "name": "Pantoprazole", "strength": "40 mg", "dose": "1-0-0",
             "timing": "Before food", "duration": "14 days", "instructions": ""},
            {"form": "Tab.", "name": "Paracetamol", "strength": "650 mg", "dose": "SOS",
             "timing": "As needed for pain", "duration": "", "instructions": "Max 3 times daily"},
        ],
        "advice": ["Nil by mouth from midnight before the operation"],
        "review": "Admission on the day of surgery",
    },
    "author": {"doctor_name": "Dr. A. Rao (synthetic)"},
}

IYER_DOCUMENT = {
    "document_id": None,
    "structured": {
        "patientName": "S. Iyer (synthetic)",
        "ageSex": "64 F",
        "diagnosis": ["Hypertension"],
        "rx": [
            {"form": "Tab.", "name": "Pantoprazole", "strength": "40 mg", "dose": "1-0-0",
             "timing": "Before food", "duration": "14 days", "instructions": ""},
            {"form": "Tab.", "name": "Atorvastatin", "strength": "10 mg", "dose": "0-0-1",
             "timing": "After food", "duration": "30 days", "instructions": ""},
            {"form": "Tab.", "name": "Paracetamol", "strength": "500 mg", "dose": "SOS",
             "timing": "As needed for pain", "duration": "", "instructions": "Max 3 times daily"},
        ],
        "advice": [],
        "review": "",
    },
    "author": {"doctor_name": "Dr. A. Rao (synthetic)"},
}


def document_for(label: str) -> dict:
    """The demo prescription for one episode: it carries the patient's own name (own record only).

    Kumar's hernia diagnosis, advice and review are his alone; any other patient keeps the medicine rows only.
    """
    document = copy.deepcopy(DEMO_DOCUMENT)
    structured = document["structured"]
    structured["patientName"] = label
    if "R. Kumar" not in label:
        structured["diagnosis"] = ["Hypertension"]
        structured["advice"] = []
        structured["review"] = ""
    return document


def key_of(name: str) -> str:
    """One matching key per medicine: the grounded generic, else the lower-cased name."""
    found = ground(name)
    return found["generic"] or " ".join(name.lower().split())


def from_document(document: dict, *, source: str) -> dict:
    """Doctor Dictation's GET /api/v1/documents/{id} body -> an rx.ordered payload."""
    structured = document.get("structured") or {}
    rows = []
    for raw in structured.get("rx") or []:
        row = {field: str(raw.get(field) or "").strip() for field in ROW_FIELDS}
        if not row["name"]:
            continue
        row["key"] = key_of(row["name"])
        rows.append(row)
    author = document.get("author") or {}
    return {
        "source": source,
        "document_id": document.get("document_id"),
        "patient": structured.get("patientName") or "",
        "diagnosis": list(structured.get("diagnosis") or []),
        "rows": rows,
        "advice": list(structured.get("advice") or []),
        "review": structured.get("review") or "",
        "by": author.get("doctor_name") or "Doctor (Doctor Dictation)",
    }


def fetch_document(base_url: str, document_id: int, *, timeout: float = 10.0) -> dict:
    """Read one saved prescription from a running Doctor Dictation."""
    url = f"{base_url.rstrip('/')}/api/v1/documents/{int(document_id)}"
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url)
    if response.status_code == 404:
        raise LookupError(f"Doctor Dictation has no document {document_id}")
    response.raise_for_status()
    return response.json()
