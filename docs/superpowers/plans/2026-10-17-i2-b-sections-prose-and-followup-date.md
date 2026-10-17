# I2-b: Brief History First, Dictated Prose and the Follow-up Date Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Summary.** Three owner changes to the sheet. (1) Brief history / Complaints comes FIRST and Diagnosis SECOND, on screen (`frontend/index.html:105-108`) and on paper (`pdf/sheet.py:299-302`). (2) Both sections hold a little dictated prose ("C/o fever with chills for 3 days, associated body aches, no vomiting."), never invented history: a prompt rule, a rules-path split, a 400-character cap and an "unheard words" note. (3) The review line shows a calculated date, `1 week (Sat 24 Oct 2026)`, computed on the server from the visit day and stored as `review_date`. Adds 16 tests: 1694 -> **1710 passed, 1 skipped** alone, **1724** after I2-a.

**Decision needed from the owner.** Confirm index Q5 (keep the section titles, reorder only), Q6 (both sections as paragraphs), Q7 (the visit day is the server-local day; set `TZ=Asia/Kolkata` in the deployment), Q8 (old documents get a date only when re-saved) and Q9 (`1/52` and `kal` are never parsed).

- **Goal:** History before diagnosis everywhere, written as short dictated prose, and an honest follow-up date.
- **Architecture:** The stored shape stays lists of strings (no migration). New pure `core/followup.py` parses the review line and does the date arithmetic; new pure `core/prose.py` caps prose items and lists unheard words. The api layer gets the visit day from one function (`api/visit.py`) and stamps `review_date` on `/api/format` (on a copy, after the cache), `/api/v1/correct` and Save. A new stateless route `POST /api/v1/review-date` lets the page recompute the date while the doctor types. `pdf/sheet.py` reorders the sections, prints them as paragraphs and prints the date. A new `frontend/sections.js` shows the date and the prose notes.
- **Tech Stack:** Python 3 stdlib (`calendar`, `datetime`, `difflib`, `re`) / FastAPI, vanilla JS, pytest, node. No new dependency.
- **Spec:** index `2026-10-17-i2-00-index.md` sections 2 (D5, D6), 4.2, 4.3, 4.4, 4.6, 6 (Q5-Q9).
- **Produces:** `core.followup` (`MAX_REVIEW_CHARS = 200`, `LIMITS`, `parse`, `add`, `review_date`, `date_label`, `stamp`); `core.prose` (`PROSE_FIELDS`, `ITEM_CHARS = 400`, `cap_items`, `unheard`); `api.visit.today()`; `api/review.py`; `frontend/sections.js` (`window.Sections`). Tests: `tests/test_followup.py` (4), `tests/test_followup_routes.py` (4), `tests/test_sections_prose.py` (6), `tests/test_frontend_sections.py` (2).

## Global Constraints
- `core/` pure: "today" is always a parameter (`tests/test_core_purity.py`). No `.py` file over 500 lines (`tests/test_file_sizes.py:12`).
- The date is information only: it never blocks Save and never changes another field. A review line with no single clear duration gets no date. Never guess.
- Old documents (lists of strings, no `review_date`) open, re-save and print with no migration.
- Offline tests, temp `DB_PATH`, blank keys. Test command `.venv/bin/python -m pytest tests/ -q`. No commits.

## Decisions (and why)
1. **Stored shape: keep the lists, allow sentences.** `complaints` and `diagnosis` stay `list[str]`; an item may be a sentence. Why: no migration; the correction merge (`core/correction.py:239-263`), the remove/replace ops by item text (`core/ops.py`) and the 12-item cap (`determinism.py:33`) keep working; an old document is already valid. A single prose string would need a reader for two shapes in the page, the PDF and `merge_form`. The page and the PDF render each item as a paragraph.
2. **The visit day** is `datetime.now().astimezone().date()`, the day the PDF prints on Save (`api/persistence.py:254`) and the OP number uses (`db/opno.py:48`). It lives in ONE function, `api/visit.today()`, so tests inject a date. The container sets no `TZ` (no match in `Dockerfile` or `docker-compose.yml`), so it runs on UTC: Q7 asks the owner to set `TZ=Asia/Kolkata`.
3. **The format cache** keeps the structured form per transcript (`api/format.py:93-99`). The date is stamped on a COPY after the cache read and never stored in it, so the same words on another day get that day's date.
4. **Parser rules.** One duration only: digits or number words (English and Hinglish `ek, do, teen, char, paanch, das, pandrah, ...`), units `day/days/din`, `week/weeks/wk/hafta/hafte`, `month/months/mahina/mahine`, `year/years/yr/saal`; `next week`, `next month`, `next year`, `fortnight`, `tomorrow`. No date for: a range (`5-7 days`, `5 to 7 days`, `5 or 7 days`), two different durations, an event-relative duration (`2 days after the USG`, `1 week of treatment`), `SOS`, `if needed`, `as required`, `kal`, `1/52`, zero, over the limits (366 days, 52 weeks, 24 months, 5 years), or a line over 200 characters.
5. **Month arithmetic** clamps to the month's last day: 31 Jan + 1 month = 28 Feb; 30 Nov 2026 + 3 months = 28 Feb 2027; 29 Feb 2028 + 1 year = 28 Feb 2029. A year is 12 months.
6. **The label** is fixed English, not the server locale (`strftime("%a")` follows `LC_TIME`): `Sat 24 Oct 2026`. The page formats a stored ISO date with the same tables; a parity test pins them.
7. **Prose guardrails.** The prompt says what to write and forbids additions; `prose.cap_items` cuts an item over 400 characters at a word and says so in `warnings`; `prose.unheard` lists the words (4+ letters, not framing words) and numbers of each prose item that the dictation never said (exact, or difflib 0.8 for speech spellings). The page shows them under the section ("Not heard in the dictation: diabetic, 5. Check this line."). Never stored, never blocking. On `/api/v1/correct` only the lists the patch replaced are checked, against the correction's own words.

## Review Focus (inputs most likely to bite)
| Input (visit day) | Expected | Pinned in |
|---|---|---|
| `1 week` (Sat 17 Oct 2026) | `2026-10-24`, `Sat 24 Oct 2026` | Task 1 test 1 |
| `1 week` at month end (31 Oct) | `2026-11-07` | Task 1 test 3 |
| `after 3 months` on 30 Nov 2026 / `1 year` on 29 Feb 2028 | `2027-02-28` / `2029-02-28` (clamped) | Task 1 test 3 |
| Hinglish `ek hafte baad`, `15 din baad`, `do mahine` | 24 Oct, 1 Nov, 17 Dec 2026 | Task 1 test 1 |
| `5-7 days`, `1 week or 10 days`, `2 days after the USG`, `kal`, `1/52` | no date | Task 1 test 2 |
| The same transcript formatted on two days (cache hit) | Each day's own date | Task 2 test 1 |
| A client-sent `review_date: "1999-01-01"` | Ignored; recomputed | Task 2 test 2 |
| A document saved before this change | Opens unchanged, prints without a date, history first | Task 2 test 4, Task 3 test 1 |
| The rules path on the owner's example | History: two sentences; diagnosis `Viral fever`; no demographics, no Rx | Task 4 test 2 |
| An LLM item "Known diabetic for 5 years." not dictated | Note: `diabetic, 5` | Task 4 tests 3, 4 |
| A review edited by hand while an older answer is in flight | The older answer is dropped | Task 5 test 1 |

## File Structure and line budgets
| File | Change | Lines now -> after (budget) |
|---|---|---|
| `core/followup.py`, `core/prose.py` | NEW | about 70, about 50 (<= 90, <= 70) |
| `core/fallback.py` | history/diagnosis split | 202 -> about 230 (<= 250) |
| `api/visit.py`, `api/review.py`, `api/app.py` | NEW, NEW, register | about 8, about 25, +1 |
| `api/format.py`, `api/persistence.py` | prompt, `_answer`, caps, stamps | 220 -> about 240; 421 -> about 425 |
| `pdf/sheet.py` | order, paragraphs, date | about 322 (after I2-a) -> about 335 |
| `frontend/sections.js`; `index.html`, `styles.css`, `app.js` | NEW; order, classes, notes, date span, wiring | about 45; +6, +3, +10 |

### Task 1: The follow-up parser and date arithmetic (pure)
**Files:** Create `doctor_dictation/core/followup.py`, `tests/test_followup.py`.

- [ ] **Step 1: Write the failing tests.**
```python
"""Plan I2-b: the follow-up date from the review line. Pure; the visit day is always passed in."""
from datetime import date

from doctor_dictation.core import followup as F

SAT = date(2026, 10, 17)

def test_one_clear_duration_in_digits_words_or_hinglish_gives_a_date():
    for text, iso in [("1 week", "2026-10-24"), ("after 5 days", "2026-10-22"), ("2 months", "2026-12-17"), ("one week", "2026-10-24"),
                      ("two weeks", "2026-10-31"), ("10 days", "2026-10-27"), ("next month", "2026-11-17"), ("1wk", "2026-10-24"),
                      ("Review after 1 week with reports", "2026-10-24"), ("review after a fortnight", "2026-10-31"), ("ek hafte baad", "2026-10-24"),
                      ("15 din baad", "2026-11-01"), ("do mahine", "2026-12-17"), ("In 2 weeks with repeat USG KUB report", "2026-10-31"),
                      ("come back in 2 days or if worse", "2026-10-19"), ("review in 2 yrs", "2028-10-17")]:
        assert F.review_date(text, SAT) == iso, text
    assert F.parse("Review after 1 week (next week)") == (1, "week")                 # the same duration twice is one

def test_no_duration_a_range_two_durations_or_an_event_gives_no_date():
    for text in ["SOS", "review SOS", "if needed", "as required", "review if fever persists", "", None, "5-7 days", "5 to 7 days", "1 week or 10 days",
                 "after 2 weeks 3 days", "review after 1 month, repeat CBC in 2 weeks", "kal", "1/52", "review on 24/10", "2 days after the USG",
                 "Review a day after the scan", "after 1 week of treatment", "100 weeks", "0 days", "do review", "1 week " + "x" * 200]:
        assert F.parse(text) is None and F.review_date(text, SAT) == "", text
    assert F.review_date("1 week", None) == "" and F.LIMITS == {"day": 366, "week": 52, "month": 24, "year": 5}

def test_months_and_years_clamp_to_the_last_day_of_the_month():
    for visit, n, unit, iso in [(date(2026, 1, 31), 1, "month", "2026-02-28"), (date(2026, 10, 31), 1, "month", "2026-11-30"),
                                (date(2026, 11, 30), 3, "month", "2027-02-28"), (date(2028, 2, 29), 1, "year", "2029-02-28"),
                                (date(2028, 1, 31), 1, "month", "2028-02-29"), (date(2026, 12, 24), 2, "week", "2027-01-07"),
                                (date(2026, 10, 31), 1, "week", "2026-11-07"), (date(2026, 10, 31), 2, "month", "2026-12-31")]:
        assert F.add(visit, n, unit).isoformat() == iso, (visit, n, unit)

def test_the_label_is_fixed_english_and_stamp_sets_review_date_only():
    assert [F.date_label(d) for d in ("2026-10-24", "2027-01-07", "2029-02-28", "", "bad", None)] == ["Sat 24 Oct 2026", "Thu 7 Jan 2027", "Wed 28 Feb 2029", "", "", ""]
    form = {"review": "after 1 week", "review_date": "1999-01-01", "rx": []}
    assert F.stamp(form, SAT) is form and form == {"review": "after 1 week", "review_date": "2026-10-24", "rx": []}
    assert F.stamp({"review": "SOS"}, SAT)["review_date"] == "" and F.stamp({}, SAT)["review_date"] == ""
```
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_followup.py -q`. Expected: 4 FAIL (`ModuleNotFoundError: ... followup`).
- [ ] **Step 3: Create `core/followup.py`** (every case above was measured against this code on a scratch copy):
```python
"""The follow-up date from the review line (plan I2-b). Pure; the visit day is passed in. One clear duration gives a date;
anything unclear gives "": no duration, a range, two different durations, a duration counted from an event, over LIMITS."""
import calendar
import re
from datetime import date, timedelta

MAX_REVIEW_CHARS = 200
LIMITS = {"day": 366, "week": 52, "month": 24, "year": 5}
_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
        "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
        "chhe": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10, "pandrah": 15}
_UNIT = {"day": "day", "days": "day", "din": "day", "week": "week", "weeks": "week", "wk": "week", "wks": "week", "hafta": "week", "hafte": "week",
         "haftey": "week", "month": "month", "months": "month", "mahina": "month", "mahine": "month", "year": "year", "years": "year", "yr": "year",
         "yrs": "year", "saal": "year"}
_ONE = {"next week": (1, "week"), "next month": (1, "month"), "next year": (1, "year"), "fortnight": (2, "week"), "tomorrow": (1, "day")}
_alt = lambda words: "|".join(sorted(map(re.escape, words), key=len, reverse=True))   # noqa: E731
_N, _U = rf"(\d{{1,3}}|{_alt(_NUM)})", f"({_alt(_UNIT)})"
_DUR = re.compile(rf"\b{_N}\s*-?\s*{_U}\b")
_RANGE = re.compile(rf"\b{_N}\s*(?:-|to|or|/)\s*{_N}\s*{_U}\b")
_EVENT = re.compile(rf"\b{_N}\s*-?\s*{_U}\s+(?:after|before|post|of|from)\b")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

def parse(text):
    """(n, "day" | "week" | "month" | "year") for the ONE duration the review line states, else None."""
    t = " ".join(str(text or "").lower().split())
    if not t or len(t) > MAX_REVIEW_CHARS or _RANGE.search(t) or _EVENT.search(t):
        return None
    found = {(int(n) if n.isdigit() else _NUM[n], _UNIT[u]) for n, u in _DUR.findall(t)}
    found |= {v for k, v in _ONE.items() if re.search(rf"\b{k}\b", t)}
    if len(found) != 1:
        return None
    n, unit = found.pop()
    return (n, unit) if 0 < n <= LIMITS[unit] else None

def add(visit: date, n: int, unit: str) -> date:
    """visit + n units; a month or a year that lands past the month's end is clamped to its last day."""
    if unit in ("day", "week"):
        return visit + timedelta(days=n * (7 if unit == "week" else 1))
    y, m = divmod(visit.month - 1 + n * (12 if unit == "year" else 1), 12)
    year, month = visit.year + y, m + 1
    return date(year, month, min(visit.day, calendar.monthrange(year, month)[1]))
```
Add three small functions after `add`: `review_date(text, visit) -> str` (`add(visit, *parse(text)).isoformat()` when `parse` gives a value and `visit` is a `date`, else `""`); `date_label(iso) -> str` (`f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"` for `date.fromisoformat(str(iso or ""))`, `""` on `ValueError`); `stamp(structured, visit) -> dict` (sets `structured["review_date"] = review_date(structured.get("review"), visit)`, replacing any client value, and returns `structured`).
- [ ] **Step 4: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_followup.py tests/test_core_purity.py -q`. Expected: all pass.

### Task 2: The visit day, the stamps and the review-date route
**Files:** Create `doctor_dictation/api/visit.py`, `doctor_dictation/api/review.py`, `tests/test_followup_routes.py`; Modify `api/format.py`, `api/persistence.py`, `api/app.py`, `tests/test_isolation_routes.py` (one `CLASSIFIED` line).

- [ ] **Step 1: Write the failing tests.**
```python
"""Plan I2-b: review_date on /api/format (never cached), /api/v1/correct, Save and the page's route. Offline."""
import json
from datetime import date

from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation import db as dbmod
from doctor_dictation.api import visit
from doctor_dictation.config import override_settings
from doctor_dictation.core.determinism import _FORMAT_CACHE
from doctor_dictation.pdf import build_sheet_html

def test_format_stamps_the_review_date_on_a_copy_so_the_cache_never_keeps_a_day(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    _FORMAT_CACHE.clear()
    monkeypatch.setattr(visit, "today", lambda: date(2026, 10, 17))
    client, body = TestClient(M.app), {"transcript": "patient complains of headache since one day advise rest review after one week"}
    first = client.post("/api/format", json=body).json()
    assert (first["structured"]["review"], first["structured"]["review_date"]) == ("Review after 1 week", "2026-10-24")
    monkeypatch.setattr(visit, "today", lambda: date(2026, 10, 31))                 # the same words on another day: a cache hit
    again = client.post("/api/format", json=body).json()
    assert again["cached"] is True and again["structured"]["review_date"] == "2026-11-07"
    assert all("review_date" not in v["structured"] for v in _FORMAT_CACHE.values())

def test_correct_recomputes_and_save_stores_the_review_date_and_ignores_a_sent_one(tmp_path, monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "f.db"))
    monkeypatch.setattr(visit, "today", lambda: date(2026, 10, 31))
    client = TestClient(M.app)
    form = {"patientName": "Anita", "opNo": "OP-5", "review": "after 2 months", "review_date": "1999-01-01", "rx": []}
    out = client.post("/api/v1/correct", json={"transcript": "", "current_form": form}).json()
    assert out["structured"]["review_date"] == "2026-12-31"                         # 31 Oct + 2 months
    r = client.post("/api/v1/documents", json={"structured": form, "confirmed_rows": []})
    assert r.status_code == 200, r.text
    conn = dbmod.get_conn(tmp_path / "f.db")
    saved = json.loads(dbmod.get_document(conn, r.json()["document_id"])["structured_json"])
    conn.close()
    assert (saved["review"], saved["review_date"]) == ("after 2 months", "2026-12-31")

def test_the_review_date_route_answers_the_page(monkeypatch):
    monkeypatch.setattr(visit, "today", lambda: date(2026, 10, 17))
    c = TestClient(M.app)
    assert c.post("/api/v1/review-date", json={"review": "1 week"}).json() == {"review_date": "2026-10-24", "label": "Sat 24 Oct 2026"}
    assert c.post("/api/v1/review-date", json={"review": "SOS"}).json() == {"review_date": "", "label": ""}
    assert c.post("/api/v1/review-date", json={}).json() == {"review_date": "", "label": ""}
    assert [c.post("/api/v1/review-date", json={"review": v}).status_code for v in ("x" * 1001, 7, None, ["1 week"])] == [400] * 4

def test_a_document_saved_before_this_change_opens_and_prints_as_before(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "o.db"))
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "Old", "40 / M", None))
    old = {"patientName": "Old", "diagnosis": ["Gastritis"], "complaints": ["epigastric pain", "nausea"], "review": "after 1 week", "rx": []}
    doc = dbmod.save_document(conn, eid, "sha-old", old)
    conn.close()
    got = TestClient(M.app).get(f"/api/v1/documents/{doc}").json()["structured"]
    assert got == old                                                              # no migration, no new key
    html = build_sheet_html(got, {"date": "2026-10-01"})
    assert "<div>after 1 week</div>" in html and 'class="rev-date"' not in html    # no date until it is re-saved (Q8)
```
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_followup_routes.py -q`. Expected: 4 FAIL (`ImportError: cannot import name 'visit'`).
- [ ] **Step 3: `api/visit.py`**: one function `today() -> date: return datetime.now().astimezone().date()`, with a docstring that names the two other users of that day (`persistence.py:254`, `db/opno.py:48`) and the UTC container (Q7).
- [ ] **Step 4: `api/review.py`.** `router = APIRouter()`, `MAX_CHARS = 1000` (a boundary cap; the parser itself reads 200), `class ReviewDateRequest(BaseModel): review: Any = ""`, and:
```python
@router.post("/api/v1/review-date")
def review_date_route(req: ReviewDateRequest):
    """The follow-up date for a review line typed on the page (plan I2-b). Stateless: no database, no clinic data."""
    if not isinstance(req.review, str) or len(req.review) > MAX_CHARS:
        return JSONResponse(status_code=400, content={"error": f"review must be text of at most {MAX_CHARS} characters"})
    iso = review_date(req.review, visit.today())
    return {"review_date": iso, "label": date_label(iso)}
```
Register it: `api/app.py:18` imports `review`; `:80` adds it to the module tuple. Add to `CLASSIFIED` in `tests/test_isolation_routes.py` (`:165-196`): `"POST /api/v1/review-date": "stateless: no database, no clinic data (plan I2-b)",`.
- [ ] **Step 5: `api/format.py`.** Import `from doctor_dictation.api import visit` and `from doctor_dictation.core import followup`. Add `_answer` and use it in all four `return` bodies (`:96-99`, `:109-112`, `:158-161`, `:168-171`), passing the other keys through unchanged (for example `return _answer(hit["structured"], normalized, raw, engine=hit["engine"], ..., cached=True, transcript_sha256=key)`):
```python
def _answer(structured, normalized, raw, **rest):
    """The response: the visit's review date stamped on a COPY, so the cache never holds a day (plan I2-b)."""
    return {"structured": followup.stamp(dict(structured), visit.today()), **rest}
```
In `correct` (`:213-220`), after `flag_unsure_rows`: `followup.stamp(structured, visit.today())`. Task 4 adds the prose check and the caps.
- [ ] **Step 6: `api/persistence.py`.** Import `visit` and `followup`. Before `conn = dbmod.get_conn()` (`:207`): `day = visit.today()` and `followup.stamp(validated, day)`; at `:254` pass `day` instead of `datetime.now().astimezone().date()`. The stored document and the PDF both carry the date.
- [ ] **Step 7: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_followup_routes.py tests/test_isolation_routes.py tests/test_formulary_routes.py tests/test_document_pdf.py tests/test_determinism.py tests/test_correction.py -q`. Expected: all pass (`review.py` grounds nothing, so `test_only_known_api_modules_call_the_grounding_functions` is unaffected).

### Task 3: History first, both as paragraphs, the date on paper and on screen
**Files:** Modify `pdf/sheet.py`, `frontend/index.html`, `frontend/styles.css`; Create `tests/test_sections_prose.py` (tests 1-2 here, 3-6 in Task 4).

- [ ] **Step 1: Write the failing tests.**
```python
"""Plan I2-b: Brief history first, both sections as dictated prose; the prompt, the rules path and the unheard check."""
from pathlib import Path

from doctor_dictation.pdf import build_sheet_html

FRONT = Path(__file__).resolve().parents[1] / "frontend"
META = {"date": "2026-10-17", "opNo": "OP-1", "patientName": "Ravi"}

def test_the_sheet_prints_brief_history_first_then_diagnosis_as_paragraphs_with_the_review_date():
    s = {"complaints": ["C/o fever with chills for 3 days, associated body aches, no vomiting.", "No h/o similar episodes."],
         "diagnosis": ["Viral fever"], "review": "1 week", "review_date": "2026-10-24"}
    html = build_sheet_html(s, META)
    assert html.index("Chief Complaints &amp; Brief History") < html.index("Diagnosis / Clinical Impression") < html.index("Investigations Advised")
    assert ('<div class="prose"><p>C/o fever with chills for 3 days, associated body aches, no vomiting.</p>'
            "<p>No h/o similar episodes.</p></div>") in html and '<div class="prose"><p>Viral fever</p></div>' in html
    assert '<div>1 week <span class="rev-date">(Sat 24 Oct 2026)</span></div>' in html
    empty = build_sheet_html({"review_date": "2026-10-24"}, META)
    assert '<div class="prose"><p>—</p></div>' in empty and "<div>—</div>" in empty and 'class="rev-date"' not in empty   # no review, no date
    old = build_sheet_html({"complaints": ["epigastric pain"], "diagnosis": ["Gastritis"]}, META)   # a document saved before I2-b
    assert old.index("epigastric pain") < old.index("Gastritis")
    assert "<li>CBC</li>" in build_sheet_html({"investigations": ["CBC"]}, META)          # the other sections keep bullets
    assert "<p>&lt;b&gt;x&lt;/b&gt;</p>" in build_sheet_html({"complaints": ["<b>x</b>"]}, META)

def test_the_screen_shows_brief_history_first_and_both_as_prose():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert html.index('id="pCc"') < html.index('id="pDx"') < html.index('id="pIx"')
    assert 'id="pCc" class="editable-list prose-list"' in html and 'id="pDx" class="editable-list prose-list"' in html
    assert all(f'id="{i}"' in html for i in ("pRevDate", "pCcNote", "pDxNote")) and "sections.js?v=1" in html
    assert "ul.editable-list.prose-list { list-style:none; padding-left:3px; }" in (FRONT / "styles.css").read_text(encoding="utf-8")
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    assert 'base.complaints = readList("pCc")' in app and 'base.diagnosis = readList("pDx")' in app    # the stored shape is unchanged
```
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_sections_prose.py -q`. Expected: 2 FAIL.
- [ ] **Step 3: `pdf/sheet.py`.** Import `from doctor_dictation.core.followup import date_label`. Beside `_list_items` (`:19-23`) add `_prose_items(values)`: one `<p>{_esc(v)}</p>` per non-empty item, else `<p>—</p>`. Replace the review line (`:258`):
```python
    label = date_label(s.get("review_date")) if str(s.get("review") or "").strip() else ""
    review = (_esc(s.get("review")) + (f' <span class="rev-date">({_esc(label)})</span>' if label else "")) or "—"
```
Swap the two section blocks (`:299-302`) so `Chief Complaints &amp; Brief History` comes first, each as `<div class="prose">{_prose_items(...)}</div>`; add `  .prose p {{ margin: 0 0 4px; }}` and `  .rev-date {{ color: #333; }}` to the `<style>` block.
- [ ] **Step 4: `frontend/index.html`, `styles.css`.** Move the `pCc` title and list above the `pDx` pair (`:105-108`); both lists get `class="editable-list prose-list"`; after each list add `<p id="pCcNote" class="prose-note no-print" role="note" hidden></p>` (and `pDxNote`). Wrap the review: `<div class="rev-line"><div id="pRev" class="editable" contenteditable="true"></div><span id="pRevDate" class="rev-date" aria-live="polite"></span></div>`. Add `<script src="sections.js?v=1"></script>` before `app.js`; bump `styles.css?v=11` and `app.js` by one. `styles.css`: `ul.editable-list.prose-list { list-style:none; padding-left:3px; }`, `.rev-line { display:flex; flex-wrap:wrap; gap:6px; align-items:baseline; } .rev-date { color:var(--muted); }`, `.prose-note { margin:2px 0 6px; font-size:12px; color:#7d5200; }`.
- [ ] **Step 5: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_sections_prose.py tests/test_pdf_sheet.py tests/test_pdf.py tests/test_letterhead_print.py tests/test_frontend_polish.py tests/test_frontend_steps.py -q`. Expected: all pass (2 new so far).

### Task 4: The prompt, the rules path and the prose guardrails
**Files:** Create `doctor_dictation/core/prose.py`; Modify `api/format.py` (prompt, caps, prose check), `core/fallback.py`; append to `tests/test_sections_prose.py`.

- [ ] **Step 1: Append the failing tests.**
```python
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core import prose
from doctor_dictation.core.determinism import _FORMAT_CACHE, normalize_transcript
from doctor_dictation.core.fallback import fallback_format
from test_determinism import _stub_llm

EX = ("Patient Ravi Kumar 34 year old male. c/o fever with chills for three days, associated body aches, no vomiting. No h/o similar episodes. "
      "Diagnosis viral fever. Tab Crocin 650 mg thrice daily after food for 3 days. Advice drink plenty of water. Review after 1 week.")

def test_the_prompt_asks_for_dictated_prose_and_forbids_invented_history():
    from doctor_dictation.api.format import SYSTEM_PROMPT
    assert "never add a symptom, duration, negative finding, past history or diagnosis" in SYSTEM_PROMPT
    assert "1 to 3 short sentences" in SYSTEM_PROMPT and "at most 400 characters" in SYSTEM_PROMPT
    schema = SYSTEM_PROMPT[SYSTEM_PROMPT.index("{\n"):]
    assert schema.index('"complaints"') < schema.index('"diagnosis"') < schema.index('"investigations"')
    assert "exactly as dictated, including brand names" in SYSTEM_PROMPT                     # the I1-b rule stays

def test_the_rules_path_keeps_history_and_diagnosis_apart_and_adds_no_word():
    out = fallback_format(normalize_transcript(EX))
    assert out["complaints"] == ["C/o fever with chills for 3 days, associated body aches, no vomiting", "No h/o similar episodes"]
    assert out["diagnosis"] == ["Viral fever"] and out["review"] == "Review after 1 week"
    assert fallback_format(normalize_transcript("patient has fever since three days please have paracetamol twice a day"))["complaints"] == ["Patient has fever since 3 days"]
    assert fallback_format(normalize_transcript("gastritis with vomiting tablet panto 40 mg once daily before food"))["diagnosis"] == ["Gastritis"]
    assert prose.unheard(out, EX, normalize_transcript(EX)) == []

def test_unheard_words_and_numbers_are_listed_never_rewritten():
    said = "c/o fever with chills for three days, associated body aches, no vomiting. diagnosis viral fever."
    form = {"complaints": ["C/o fever with chils for 3 days, no vomiting.", "Known diabetic for 5 years."],
            "diagnosis": ["Viral fever", "Acute febrile illness, likely viral"]}
    assert prose.unheard(form, said, normalize_transcript(said)) == [{"field": "complaints", "index": 1, "words": ["diabetic", "5"]},
                                                                     {"field": "diagnosis", "index": 1, "words": ["acute", "febrile", "illness", "likely"]}]
    assert form["complaints"][1] == "Known diabetic for 5 years."                             # information only
    long = {"complaints": ["word " * 120], "diagnosis": ["Viral fever"]}
    assert prose.cap_items(long) == ["complaints[0]: shortened from 600 to 400 characters"] and len(long["complaints"][0]) == 400

def test_format_returns_the_prose_check_caps_long_items_and_never_stores_the_check(monkeypatch):
    _FORMAT_CACHE.clear()
    _stub_llm(monkeypatch, [{"complaints": ["C/o fever with chills for 3 days.", "Known diabetic for 5 years."],
                             "diagnosis": ["C/o fever " + "with chills " * 60], "rx": []}])
    j = TestClient(M.app).post("/api/format", json={"transcript": "c/o fever with chills for three days"}).json()
    assert j["prose_check"] == [{"field": "complaints", "index": 1, "words": ["diabetic", "5"]}]
    assert len(j["structured"]["diagnosis"][0]) <= prose.ITEM_CHARS and j["structured"]["diagnosis"][0].endswith("…")
    assert any(w.startswith("diagnosis[0]: shortened from") for w in j["warnings"]) and "prose_check" not in j["structured"]
```
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_sections_prose.py -q`. Expected: 4 FAIL (`ImportError: cannot import name 'prose'`).
- [ ] **Step 3: Create `core/prose.py`** (measured on the examples above with a scratch copy):
```python
"""Prose sections (plan I2-b): Brief history and Diagnosis are short dictated sentences. Pure: cap the items, and list the
words of an item the dictation never said (information for the doctor; nothing is rewritten)."""
import difflib
import re

PROSE_FIELDS = ("complaints", "diagnosis")
ITEM_CHARS, MIN_WORD = 400, 4
FRAME = frozenset("""about after along also associated before case clinical complaint complaints days diagnosis during episode episodes from history
impression known months noted over patient presented presents reports similar since than that there this under week weeks which with years year month
day""".split())                       # framing words a summary adds without new facts

def _words(text):
    return re.findall(r"[a-z]+|\d+(?:\.\d+)?", str(text or "").lower())

def unheard(structured: dict, *transcripts) -> list:
    """[{"field", "index", "words"}]: words (4+ letters, not FRAME) and numbers of each prose item not in the dictation."""
    heard = {w for t in transcripts for w in _words(t)}
    pool, out = sorted(w for w in heard if not w[0].isdigit()), []
    for field in PROSE_FIELDS:
        for i, item in enumerate(structured.get(field) or []):
            missing = []
            for w in _words(item):
                number = w[0].isdigit()
                if w in heard or w in FRAME or w in missing or (not number and len(w) < MIN_WORD):
                    continue
                if not number and difflib.get_close_matches(w, pool, n=1, cutoff=0.8):
                    continue                                        # a speech spelling ("chils") of a dictated word
                missing.append(w)
            if missing:
                out.append({"field": field, "index": i, "words": missing})
    return out
```
`cap_items(structured) -> list` (mutates): for each prose field coerce the items to `str`; an item over `ITEM_CHARS` becomes `text[:ITEM_CHARS].rsplit(" ", 1)[0].rstrip(" ,;") + "…"` and adds the warning `f"{field}[{i}]: shortened from {len(text)} to {len(new)} characters"`.
- [ ] **Step 4: The prompt and the route** (`api/format.py:44-62`). Rule 1 becomes `1. Extract the Brief history (complaints), Diagnosis, Investigations Advised and Medications.` Insert before the JSON rule (renumbered 8):
```text
7. complaints: the brief history as 1 to 3 short sentences, the way a doctor writes it, for example "C/o fever with chills for 3 days, associated body aches, no vomiting." and "No h/o similar episodes.". diagnosis: 1 or 2 short phrases or sentences. Restate ONLY what was dictated: never add a symptom, duration, negative finding, past history or diagnosis the doctor did not say. If nothing was dictated, use []. Each item at most 400 characters.
```
In the schema put `"complaints": ["short sentence of the dictated history"]` BEFORE `"diagnosis": ["short phrase or sentence"]`. Import `prose`. In the three non-cached paths add `warnings += prose.cap_items(structured)` right after each `_validate(...)`, before `cache_put`. `_answer` stamps the copy `s` and returns `{"structured": s, "prose_check": prose.unheard(s, raw, normalized), **rest}`. `correct` returns `"prose_check": prose.unheard({f: patch2.get(f) or [] for f in prose.PROSE_FIELDS}, text, normalized)`: only the lists the patch replaced (`merge_form` replaces a whole list, `core/correction.py:251-255`), against the correction's own words.
- [ ] **Step 5: The rules path** (`core/fallback.py:120-129`). Add at module level, and in `fallback_format` set `out["complaints"], dictated = _history_and_diagnosis(text)`; the keyword diagnosis loop runs only `if not dictated`, else `out["diagnosis"] = dictated`:
```python
_CUT = re.compile(r"\b(?:prescribe[sd]?|tablet|tab|capsule|cap|syrup|syr|injection|inj|please have|please take|advi[cs]e|review|follow[\s-]?up|come back)\b", re.I)
_DX = re.compile(r"^(?:provisional |final |clinical )?(?:diagnosis|impression)\b[\s:,-]*(?:is |of |as )?", re.I)
_DEMO = re.compile(r"^.*?\b\d{1,3}\s*(?:years?|yrs?)(?:\s*old)?(?:\s*(?:male|female|man|woman|boy|girl))?\b[\s,]*(?:having|has|with|c/o|complains? of)?\s*", re.I)
_DOSE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu)\b", re.I)
LIST_DX = 3

def _history_and_diagnosis(text: str):
    """(history items, dictated diagnosis items): each sentence up to its first Rx, advice or review word or drug name,
    without the demographics; "diagnosis X" sentences go to the diagnosis. Dictated words only (plan I2-b)."""
    amap, hist, dx = _maps()[0], [], []
    for s in (p.strip() for p in re.split(r"(?<!\d)\.(?!\d)|[|;]", text) if p.strip()):
        m = _DX.match(s)
        if m:
            rest = s[m.end():].strip(" ,:-")
            dx += [rest[:1].upper() + rest[1:]] if rest else []
            continue
        cut = _CUT.search(s)
        end = cut.start() if cut else len(s)
        end = next((w.start() for w in re.finditer(r"[A-Za-z]{4,}", s[:end]) if w.group(0).lower() in amap), end)
        s = _DEMO.sub("", s[:end]).strip(" ,;:-")
        if s and not _DOSE.search(s):
            hist.append(s[:1].upper() + s[1:])
    return hist[:4], dx[:LIST_DX]
```
Measured on a scratch copy over the 8 golden transcripts and the owner's example: `tests/golden.json` expectations hold (the ureteric case uses the seeded branch); the owner's example gives exactly the two history sentences and `Viral fever`.
- [ ] **Step 6: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_sections_prose.py tests/test_determinism.py tests/test_brand_as_dictated.py tests/test_ordinary_sentences.py tests/test_core_purity.py -q`. Expected: all pass (`test_sections_prose.py`: 6 passed).

### Task 5: The page: the date beside the review and the prose notes
**Files:** Create `frontend/sections.js`, `tests/test_frontend_sections.py`; Modify `frontend/app.js`.

- [ ] **Step 1: Write the failing tests.**
```python
"""Plan I2-b, page: frontend/sections.js under node with a tiny fake DOM (elements by id, text, hidden)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from doctor_dictation.core.followup import date_label

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FAKE = """const els = {}; ["pRevDate", "pCcNote", "pDxNote"].forEach((id) => { els[id] = { id, textContent: "", hidden: true }; });
globalThis.document = { getElementById: (id) => els[id] || null }; globalThis.window = globalThis;
const posts = []; const tick = () => new Promise((r) => setTimeout(r, 0));"""

def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    js = FAKE + "require(process.argv[1]); Sections.init({ post: (u, b) => new Promise((res) => posts.push({ u, b, res })), waitMs: 0 });" \
        + "(async () => {" + body + "})().catch((e) => { console.error(e.stack); process.exit(1); });"
    out = subprocess.run([node, "-e", js, str(FRONT / "sections.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)

def test_the_page_label_matches_the_server_and_a_stale_answer_is_dropped():
    isos = ["2026-10-24", "2027-01-07", "2029-02-28", "2028-02-29", "", "bad"]
    r = _run("""const labels = %s.map(Sections.dateLabel);
      Sections.showDate("2026-10-24"); const shown = els.pRevDate.textContent;
      Sections.onReviewInput("1 week"); await tick(); Sections.onReviewInput("2 weeks"); await tick();
      posts[1].res({ review_date: "2026-10-31" }); await tick(); posts[0].res({ review_date: "2026-10-24" }); await tick();
      console.log(JSON.stringify({ labels, shown, sent: posts.map((p) => [p.u, p.b.review]), now: els.pRevDate.textContent }));""" % json.dumps(isos))
    assert r["labels"] == [date_label(i) for i in isos]                         # one format, server and page
    assert r["shown"] == "(Sat 24 Oct 2026)" and r["now"] == "(Sat 31 Oct 2026)"   # the older answer lost the race
    assert r["sent"] == [["/api/v1/review-date", "1 week"], ["/api/v1/review-date", "2 weeks"]]

def test_prose_notes_are_text_only_and_an_edit_clears_its_section():
    r = _run("""Sections.showProseCheck([{ field: "complaints", index: 1, words: ["diabetic", "<b>5</b>"] }, { field: "x", index: 0, words: ["y"] }]);
      const shown = [els.pCcNote.textContent, els.pCcNote.hidden, els.pDxNote.hidden];
      Sections.clearProse("complaints"); const cleared = [els.pCcNote.textContent, els.pCcNote.hidden];
      Sections.showProseCheck(undefined);
      console.log(JSON.stringify({ shown, cleared, none: [els.pCcNote.hidden, els.pDxNote.hidden] }));""")
    assert r["shown"] == ["Not heard in the dictation: diabetic, <b>5</b>. Check this line.", False, True]
    assert r["cleared"] == ["", True] and r["none"] == [True, True]
```
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_frontend_sections.py -q`. Expected: 2 FAIL (`Cannot find module .../sections.js`).
- [ ] **Step 3: Create `frontend/sections.js`** (`window.Sections = { init, dateLabel, showDate, onReviewInput, showProseCheck, clearProse }`, an IIFE like `rxstate.js`; `init(hooks)` keeps `post` and `waitMs` (default 400); `NOTE = { complaints: "pCcNote", diagnosis: "pDxNote" }`):
```js
  function dateLabel(iso) {                       // the same text as core/followup.date_label
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
    if (!m) return "";
    const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    if (d.getUTCMonth() !== +m[2] - 1) return "";
    return DAYS[(d.getUTCDay() + 6) % 7] + " " + d.getUTCDate() + " " + MONTHS[d.getUTCMonth()] + " " + d.getUTCFullYear();
  }
  function showDate(iso) { const n = $("pRevDate"); if (n) n.textContent = dateLabel(iso) ? "(" + dateLabel(iso) + ")" : ""; }
  function onReviewInput(text) {                   // the doctor typed: ask the server again; only the newest answer shows
    const tok = ++seq; if (timer) clearTimeout(timer); showDate("");
    timer = setTimeout(() => { H.post(URL, { review: String(text || "").slice(0, 1000) }, 10000)
      .then((j) => { if (tok === seq) showDate(j && j.review_date); }).catch(() => {}); }, H.waitMs);
  }
```
`DAYS` starts at Monday and `MONTHS` at January, as in `core/followup.py`. `clearProse(field)` empties and hides `NOTE[field]`; `showProseCheck(list)` clears both notes, then for each entry with a known field and a non-empty `words` list sets `textContent = "Not heard in the dictation: " + words.map(String).join(", ") + ". Check this line."` and shows it (text only).
- [ ] **Step 4: Wire `frontend/app.js`.** (a) `renderSheet` (`:895`): after `setText($("pRev"), ...)` add `Sections.showDate(s.review_date || "");`. (b) `formatTranscript` and `applyCorrection` (`:529`, `:556`): after `renderSheet(state.structured)` add `Sections.showProseCheck(j.prose_check);`. (c) After the `sheetEl` listeners (`:811-813`): `$("pRev").addEventListener("input", () => Sections.onReviewInput(text($("pRev"))));`. (d) In `fixLists` (`:807-810`): `if (ul && ul.id === "pCc") Sections.clearProse("complaints"); if (ul && ul.id === "pDx") Sections.clearProse("diagnosis");`. (e) `newPatient` (`:1194`): `Sections.showDate(""); Sections.showProseCheck([]);`. (f) The init block (`:1211`): `Sections.init({ post: postJson });`.
- [ ] **Step 5: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_frontend_sections.py tests/test_sections_prose.py tests/test_frontend_steps.py tests/test_frontend_rxspell.py -q`. Expected: all pass.

### Task 6: Mutations, whole suite, live browser check
- [ ] **Step 1: Mutations** (apply alone, run the named file, see a failure, revert):

| # | Mutation | Must fail |
|---|---|---|
| M1 | drop `_RANGE` / `_EVENT` from `parse` | `test_followup.py` 2 |
| M2 | `min(visit.day, ...)` -> `visit.day` | `test_followup.py` 3 (ValueError) |
| M3 | `date_label` with `strftime("%a %d %b %Y")` | `test_followup.py` 4 (`07 Jan`) |
| M4 | stamp the cached dict in place / save trusts a client `review_date` | `test_followup_routes.py` 1 / 2 |
| M5 | sheet keeps Diagnosis first / `<li>` for history | `test_sections_prose.py` 1 |
| M6 | fallback keeps the demographics sentence / drops `_DX` | `test_sections_prose.py` 4 |
| M7 | `unheard` skips numbers / ignores `FRAME` / no `cap_items` before `cache_put` | `test_sections_prose.py` 5 / 6 |
| M8 | `onReviewInput` without the `tok === seq` check | `test_frontend_sections.py` 1 |

- [ ] **Step 2: Whole suite.** Run: `.venv/bin/python -m pytest tests/ -q`. Expected: **1710 passed, 1 skipped** alone (1694 + 16), or **1724** after I2-a.
- [ ] **Step 3: Live browser check** (a separate server on 8801, temp `DB_PATH`, blank keys, stub speech, started as in I2-a Task 5 Step 4 with `STUB_TRANSCRIPT` = the `EX` text; never port 8000, which uses real providers). Check: History is above Diagnosis with two sentences as paragraphs; Diagnosis reads `Viral fever`; the review shows `Review after 1 week (<today + 7>)`. Type `2 months` into the review: the date changes after a moment; type `SOS`: it disappears. Save, reopen from Today, Print: the PDF has the same order and the date. 390 px: the date wraps under the review; no page scroll. Stop the server, `lsof -i :8801` empty, delete the scratch folder. Commit nothing; no secrets.
- [ ] **Step 4: Leave uncommitted.** Changed files: the File Structure table and the five test files.

## Regression list (must stay green)
Save gate and zero medicines (`tests/test_safety.py`; Task 2 test 2 saves `rx: []`); the list merge (`tests/test_correction.py:40-52`, `test_correction_ops.py`); the golden pipeline (`tests/test_determinism.py:78-100`); PDF layout and letterhead (`test_pdf_sheet.py`, `test_pdf_layout.py`, `test_letterhead_print.py`); route classification (`test_isolation_routes.py:200-213`); Spell it (`test_frontend_rxspell*.py`).

## Self-Review
- D5: Task 3 (order, paragraphs, screen), Task 4 (prompt, rules path, guardrails, caps). D6: Tasks 1-2 (server), 3 (paper), 5 (screen, recompute on edit). Old documents: Task 2 test 4, Task 3 test 1. Time zone: Decision 2 and Q7.
- Test count: 4 + 4 + 2 + 4 + 2 = 16. Edited, not added: one `CLASSIFIED` line.
- Out of scope: the `TZ` deployment change (Q7); event-relative dates; a calendar picker; reminders; renaming the section titles (Q5).

**Decision needed:** the owner's yes on Q5-Q9 (index section 6); then run Task 1.
