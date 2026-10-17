"""Structuring endpoints: /api/format (extract, ground, repair) and /api/v1/correct."""
import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from doctor_dictation.api import authorship, visit
from doctor_dictation.api.formulary import use_clinic_layer
from doctor_dictation.config import get_settings
from doctor_dictation.core import followup, formulary, prose
from doctor_dictation.core.ops import apply_ops
from doctor_dictation.core.correction import (
    extract_correction,
    flag_unsure_rows,
    match_by_generic,
    merge_form,
    preserve_untouched_rx_status,
    resolve_blank_names,
    strip_grounding_markers,
)
from doctor_dictation.core.determinism import (
    FORMAT_LLM_CAP,
    build_repair_message,
    cache_get,
    cache_put,
    ground_rx,
    lexicon_version,
    loop_should_continue,
    normalize_transcript,
    open_issues,
    transcript_sha,
    validate_structured,
)
from doctor_dictation.core.fallback import fallback_format, unparsed_notes
from doctor_dictation.providers.llm.factory import make_llm
from doctor_dictation.scope import current_scope

router = APIRouter()

SYSTEM_PROMPT = """You are a DETERMINISTIC clinical extraction engine. Same input must always produce the same output.
Take the raw dictated clinical text and format it into a standardized outpatient prescription and consultation summary.

STRICT RULES:
1. Extract the Brief history (complaints), Diagnosis, Investigations Advised and Medications.
2. Allowed dose codes ONLY: "1-0-0", "1-0-1", "1-1-1", "0-0-1", "SOS". Map: once daily/OD -> 1-0-0; twice daily/BD -> 1-0-1; thrice daily/TDS -> 1-1-1; at bedtime/HS -> 0-0-1; as needed/for pain -> SOS. Never output OD/BD/TDS/HS text.
3. Allowed timing ONLY: "After food", "Before food", "At bedtime", or "". Map "after meal" -> After food, "empty stomach" -> Before food, "at night" -> At bedtime.
4. Copy drug strength VERBATIM from the transcript (e.g. "0.4 mg"). If no strength dictated, use "". Never invent strengths, durations, or drugs. Write each medicine name exactly as dictated, including brand names; never replace a brand with its generic. If a field is missing, return empty string or empty array, never hallucinate.
5. If the doctor dictates patient demographics (e.g. "patient Rahul Sharma, 45 year old male"), extract patientName and ageSex (format "45 / M"). If an OP/registration number is dictated, copy it VERBATIM into opNo (e.g. "OP 1234" -> "OP 1234"); use "" if not dictated. Otherwise return empty strings.
6. Duration format: "<N> days/weeks/months" with digits (e.g. "14 days"). Map "two weeks" -> "14 days".
7. complaints: the brief history as 1 to 3 short sentences, the way a doctor writes it, for example "C/o fever with chills for 3 days, associated body aches, no vomiting." and "No h/o similar episodes.". diagnosis: 1 or 2 short phrases or sentences. Restate ONLY what was dictated: never add a symptom, duration, negative finding, past history or diagnosis the doctor did not say. If nothing was dictated, use []. Each item at most 400 characters.
8. Return ONLY valid JSON matching this exact schema, no markdown, no extra text. EXAMPLE input: "right flank pain and burning micturition since 2 days. 5 mm lower ureteric calculus. tablet Tamsulosin 0.4 mg once daily at bedtime after food for 2 weeks, tablet Paracetamol 650 mg as needed for pain." -> rx doses "0-0-1" and "SOS", timings "After food" and "":
{
  "patientName": "string (empty if not dictated)",
  "ageSex": "string like '45 / M' (empty if not dictated)",
  "opNo": "string, OP/registration number copied verbatim (empty if not dictated)",
  "complaints": ["short sentence of the dictated history"],
  "diagnosis": ["short phrase or sentence"],
  "investigations": ["string"],
  "rx": [{"form": "Tab.|Cap.|Syr.|Inj.", "name": "string", "strength": "string", "dose": "1-0-0|1-0-1|1-1-1|0-0-1|SOS", "timing": "After food|Before food|At bedtime|empty", "duration": "e.g. 14 days", "instructions": "string"}],
  "advice": ["string"],
  "review": "string"
}"""


class FormatRequest(BaseModel):
    transcript: str = ""


async def _validate(data, transcript, raw=""):
    """validate_structured in a worker thread: ~10 ms of CPU must not stall the loop."""
    return await asyncio.to_thread(validate_structured, data, transcript, raw)


async def _normalize(text):
    """normalize_transcript in a worker thread (a difflib pass per token, the costliest step)."""
    return await asyncio.to_thread(normalize_transcript, text)


async def _ground(rows, transcript):
    """ground_rx in a worker thread, for the same reason."""
    return await asyncio.to_thread(ground_rx, rows, transcript)


def _answer(structured, normalized, raw, **rest):
    """The response: the visit's review date stamped on a COPY, so the cache never holds a day, and the unheard-words
    check of the prose sections (information only, never stored; plan I2-b)."""
    s = followup.stamp(dict(structured), visit.today())
    return {"structured": s, "prose_check": prose.unheard(s, raw, normalized), "normalized_transcript": normalized, **rest}


@router.post("/api/format", dependencies=[Depends(use_clinic_layer)])
async def format_transcript(req: FormatRequest):
    raw = (req.transcript or "").strip()
    if not raw:
        return JSONResponse(status_code=400, content={"error": "Empty transcript"})
    # P1: deterministic normalization (numbers + lexicon) before any engine.
    normalized = await _normalize(raw)
    key = transcript_sha(normalized)
    sc = current_scope()
    ckey = f"{sc.clinic_slug if sc else ''}:{formulary.active_layer().version}:{key}:{transcript_sha(raw)[:16]}"   # per clinic, learned list, raw wording
    hit = cache_get(ckey)
    if hit is not None:
        return _answer(hit["structured"], normalized, raw, engine=hit["engine"], warnings=hit.get("warnings", []),
                       grounding=hit.get("grounding", {"rounds": 0, "open_issues": [], "llm_calls": 0}),
                       cached=True, transcript_sha256=key)
    llm = make_llm(get_settings())
    if llm is None:
        drafted = fallback_format(normalized)
        structured, warnings = await _validate(drafted, normalized, raw)
        warnings += prose.cap_items(structured) + unparsed_notes(normalized, drafted["rx"])
        engine = (f"fallback-rules+lexicon v{lexicon_version()} "
                  f"(set OPENAI_API_KEY for default LLM, or DEEPSEEK_API_KEY with LLM_PROVIDER=deepseek)")
        grounding = {"rounds": 0, "open_issues": open_issues(structured),
                     "llm_calls": 0}
        cache_put(ckey, {"structured": structured, "engine": engine,
                        "warnings": warnings, "grounding": grounding})
        return _answer(structured, normalized, raw, engine=engine, warnings=warnings, grounding=grounding,
                       cached=False, transcript_sha256=key)
    base_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Raw Dictated Audio Transcript:\n\"\"\"\n{normalized}\n\"\"\""},
    ]

    # Agent loop: extract -> ground -> targeted repair (best draft wins).
    best = None  # (open_issue_count, draft_dict)
    llm_calls = 0
    prev_open = None
    last_err = ""
    messages = list(base_messages)
    try:
        while True:
            draft, err = await llm.complete_json(messages)
            if not isinstance(draft, dict):
                last_err = err or "empty LLM draft"
                break
            llm_calls += 1
            _, issues = await _ground(draft.get("rx") or [], normalized)
            n_open = len(issues)
            if best is None or n_open < best[0]:
                best = (n_open, draft)
            print(f"format loop call={llm_calls} open_issues={n_open} sha={key[:12]}",
                  flush=True)
            if n_open == 0 or llm_calls >= FORMAT_LLM_CAP:
                break
            if prev_open is not None and not loop_should_continue(
                prev_open, n_open, llm_calls
            ):
                break  # no strict progress — finalize best draft
            prev_open = n_open
            messages = list(base_messages) + [
                {"role": "user", "content": await asyncio.to_thread(build_repair_message, issues, normalized)}
            ]
    except Exception as e:
        last_err = str(e)
    if best is not None:
        structured, warnings = await _validate(best[1], normalized, raw)
        warnings += prose.cap_items(structured)
        repairs = max(0, llm_calls - 1)
        engine = (f"{llm.name}:{llm.model}+lexicon v{lexicon_version()}"
                  f"+loop{repairs}")
        grounding = {"rounds": repairs, "open_issues": open_issues(structured),
                     "llm_calls": llm_calls}
        cache_put(ckey, {"structured": structured, "engine": engine,
                        "warnings": warnings, "grounding": grounding})
        return _answer(structured, normalized, raw, engine=engine, warnings=warnings, grounding=grounding,
                       cached=False, transcript_sha256=key)
    # Graceful fallback so demo never blocks (still validated + cached)
    drafted = fallback_format(normalized)
    structured, warnings = await _validate(drafted, normalized, raw)
    warnings += prose.cap_items(structured) + unparsed_notes(normalized, drafted["rx"])
    engine = f"fallback-after-error v{lexicon_version()}: {last_err}".strip()[:300]
    grounding = {"rounds": 0, "open_issues": open_issues(structured), "llm_calls": llm_calls}
    cache_put(ckey, {"structured": structured, "engine": engine,
                    "warnings": warnings, "grounding": grounding})
    return _answer(structured, normalized, raw, engine=engine, warnings=warnings, grounding=grounding,
                   cached=False, transcript_sha256=key)


class CorrectRequest(BaseModel):
    transcript: str = ""
    current_form: dict = {}
    document_id: int | None = None   # the saved prescription being corrected; None for an unsaved draft


@router.post("/api/v1/correct", dependencies=[Depends(use_clinic_layer)])
async def correct(req: CorrectRequest, request: Request):
    """Merge a spoken correction into the current form, then re-ground it.

    `extract_correction` returns the *patch* the correction states; offline
    (no LLM configured) or an empty dictation that patch is `{}`, so an empty
    correction never wipes the form. The merge is re-validated so the rx
    `status` pills are recomputed for the changed rows, while rows the patch
    does not name keep their prior verification state.

    Correcting a saved prescription (``document_id``) needs ``document.edit``: only its author (403 otherwise).
    """
    if req.document_id is not None:
        denied = await asyncio.to_thread(authorship.check_document, request, "document.edit", req.document_id)
        if denied is not None:
            return denied
    current = req.current_form if isinstance(req.current_form, dict) else {}
    text = (req.transcript or "").strip()
    normalized = await _normalize(text) if text else ""
    llm = make_llm(get_settings())
    patch = {}
    llm_calls = 0
    engine = f"rules+lexicon v{lexicon_version()}"
    if llm is not None and normalized:
        try:
            patch = await extract_correction(normalized, current, llm.complete_json)
            llm_calls = 1
            engine = f"{llm.name}:{llm.model}+lexicon v{lexicon_version()}"
        except Exception as e:
            engine = f"rules-after-error v{lexicon_version()}: {e}".strip()[:300]
    current2, patch2, ops_notes, touched = apply_ops(current, patch)
    patch2, merge_warnings = resolve_blank_names(current2, patch2)
    patch2, same_notes, unsure = await asyncio.to_thread(match_by_generic, current2, patch2)  # brand <-> generic
    structured, _warnings = await _validate(
        strip_grounding_markers(merge_form(current2, patch2)), normalized, text)
    preserve_untouched_rx_status(current, patch2, structured, extra_named=touched)
    flag_unsure_rows(structured, unsure)  # appended, not placed: the doctor must confirm it
    followup.stamp(structured, visit.today())  # the date follows the corrected review line
    grounding = {"rounds": 0, "open_issues": open_issues(structured),
                 "llm_calls": llm_calls}
    return {"structured": structured, "grounding": grounding, "engine": engine,
            "prose_check": prose.unheard({f: patch2.get(f) for f in prose.PROSE_FIELDS}, text, normalized),   # only the lists the patch replaced
            "warnings": ops_notes + merge_warnings + same_notes}
