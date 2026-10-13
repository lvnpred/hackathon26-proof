# Doctor Dictation — Platform Foundation Design

**Date:** 2026-10-13 · **Status:** Draft for review · **Scope:** build phases B0–B1 in detail, deployment phase D0 (demo) in detail, D1–D2 as outlines.

---

## 1. Summary (read this first)

Doctor Dictation turns a doctor's voice into an editable prescription. It works today
(122 tests pass), but it has a confirmed correction bug, a likely weak point in
speech-to-text, no login, and state kept on local disk. This spec fixes those, restructures the code so
speech and language providers are swappable, and defines the smallest safe first
deployment: a **demo with fake patients only**. It grows later to one real clinic (D1)
and then many clinics (D2).

### Decisions

| # | Decision | Why | Revisit when |
|---|---|---|---|
| 1 | **Stay on Python** (no Go/TypeScript rewrite) | Request time is ~99.9% waiting on OpenAI; the app's own logic costs ~10 ms. Limits are shared state and OpenAI, not the language. | CPU-heavy work moves in-process |
| 2 | Restructure into a **pip-installable package** with a **provider factory** for STT, LLM and storage | Providers are tangled in `main.py` (1,058 lines); a new provider should be one file | — |
| 3 | The LLM interface **supports tool calls from day one** | Lets the doctor-assistant features come later without reworking every provider | — |
| 4 | **Keep the verify gate.** AI only proposes; the doctor confirms. | Patient safety; already built | Never relax without a clinical review |
| 5 | **Accuracy first** with techniques 1, 2, 3, 6 (§5) | Medicines are the weak point | After the benchmark |
| 6 | **Knowledge graph, relational first**, every link labelled `observed`, `vetted` or `proposed`. **Apache AGE optional.** | Deterministic suggestions from the doctor's own history; LLM ideas stay separate | Multi-hop queries are needed |
| 7 | **No patient identity in the graph** (pseudonymous IDs only) | Tenant isolation inside a graph is easy to get wrong | — |
| 8 | **No streaming, no LoRA/fine-tuning, no self-hosted GPU STT yet** | Cost and complexity not yet justified | See §10 triggers |
| 9 | First deployment = **one container + volume + HTTPS + shared login** | Smallest safe demo | D1 |
| 10 | **Server-side PDF on the doctor's own letterhead** (template tool, §7A) | Doctors need prescriptions that match their existing pad | — |
| 11 | Template = **a vision LLM recreates the pad once per clinic** as a validated A4 layout; the clinic reviews and accepts; the LLM is never used at print time | Simplest path: no straighten, no drag boxes, no A4 fitting | Clinics often reject the copy's fidelity |

### Phases

| Phase | What | Gate to leave |
|---|---|---|
| **B0** | Fix confirmed bugs, tests first | New tests green; all 122 existing tests green |
| **B1** | Package restructure + provider factory, no behaviour change | 122 tests green + new provider tests |
| **B2** | Server PDF + LLM-built letterhead template (§7A) | Example layouts render correctly; renderer chosen by spike |
| **D0** | First deployment (demo, fake patients only) | B2 done and load test (§8.4) passes |
| D1 | One real clinic | Outline only (§9) |
| D2 | Many clinics | Outline only (§9) |

### How the discussion changed the first deployment (D0)

| Decision | Effect on D0 |
|---|---|
| Stay on Python | One Python container; no new language toolchain |
| Provider factory | Cloud STT and cloud LLM are config lines in `.env`; swapping providers needs no redeploy of code |
| Graph optional / relational first | **No graph database in D0.** Suggestions start from SQL counts. One fewer service to host. |
| No patient identity in graph | Nothing extra to protect in D0 |
| Accuracy techniques | Adds a vocabulary hint, silence trimming and an upload cap to the request path |
| **PDF rendering** | Each save launches headless Chromium (`pdf.py:195`). Server PDFs are required in D0, so the renderer is chosen by a short spike (§7A.5) and should not launch a browser per save |
| Event-loop blocking | Run validation off the event loop and set workers = cores (§8.3) |

**Decision needed from you:** approve this revision (new §7A, changed §8.2), or name the sections to change (§11 lists open questions). D0 is now larger; §7A.7 shows how it is sequenced.

---

## 2. Problem statement (confirmed in the running app, 2026-10-13)

1. **Correction adds a blank medicine row.** Current form has an Ascoril row; the doctor says
   "strength is 5 ml for the Ascoril and the duration is 7 days". Result: the Ascoril row is
   unchanged and a new row `{name: "", strength: "5 ml", duration: "7 days"}` is appended.
   Two causes: the correction prompt gives the model no schema or "always name the medicine"
   rule, and the merge appends any patch row whose name does not match, including a blank name.
   The same correction also returned `ageSex: "32/Female"` where the format path gives `"45 / M"`.
2. **Cloud speech-to-text gets no vocabulary hint.** The OpenAI call sends only `model` and
   `language`; the local engine has an `initial_prompt`. Brand names are likely to be misheard.
   *(Likely cause, not yet measured on real audio.)*
3. **Validation runs on the event loop** inside async routes, ~10 ms each; under load one request delays the others on that worker.
4. **State is on local disk:** SQLite, PDFs, and an in-process format cache (a plain dict, per worker).
5. **No authentication** on any `/api/v1/*` endpoint, and CORS allows every origin.
6. **Each save launches a Chromium browser** to build the PDF. I had not counted this in earlier CPU estimates (which covered only normalize + validate, ~10 ms).
7. **Training data does not accumulate:** the database stores only a hash of the transcript.
8. **PDFs cannot use a doctor's own letterhead.** The sheet is a fixed built-in layout (`build_sheet_html`), so a clinic cannot make prescriptions look like its existing pad.

---

## 3. Target architecture

```
doctor_dictation/                 # pip-installable (pyproject.toml); renamed from backend/, flat layout
  core/        determinism (+ lexicon/), correction, safety, fallback    # pure, no I/O
  providers/
    stt/       base.py (Protocol) · openai.py · local.py · onnx.py · browser.py · factory.py
    llm/       base.py (Protocol, tools- and image-capable) · openai_compat.py · factory.py
  db/          the sqlite store and migrations (unchanged name; repository Protocol deferred to D1)
  pdf/         layout vocabulary · sheet builder · PdfRenderer (pooled Chromium)
  api/         thin FastAPI routers — no business logic
  bench/       STT benchmark harness
  knowledge/   (later) provenance-labelled links, optional Apache AGE adapter
tests/         the existing tests move with the code they cover
```

Deviations from the first draft of this spec (decided while writing the plans): the package is a flat rename of `backend/` to `doctor_dictation/` at the repo root (no `src/` move, so the frontend, data and secrets paths keep working); the repository `Protocol` for storage is deferred to D1, when Postgres arrives, because a second implementation does not exist yet.

**Rules**
- `core/` imports nothing from `providers/`, `store/` or `api/`.
- The current try/except dual-import blocks in `main.py` (lines 17-90) are removed; one package import path only.
- No file over 500 lines.

### 3.1 Provider interfaces

```python
class SttProvider(Protocol):
    name: str
    async def transcribe(self, audio: bytes, filename: str, hints: list[str]) -> Transcript: ...

class LlmProvider(Protocol):
    name: str
    async def complete_json(self, messages: list[dict]) -> JsonResult: ...
    async def complete(self, messages: list[dict], tools: list[Tool] | None = None) -> Completion: ...
```

`messages` may include **image parts** (needed by the template tool, §7A). `hints` is passed to **every** STT provider, so vocabulary biasing is a property of the
interface and not of one engine. `complete(..., tools=...)` exists now (decision 3) even
though only `complete_json` is used in B1.

### 3.2 Factory and fallback

```python
STT_REGISTRY = {"openai": OpenAiStt, "faster-whisper": LocalWhisperStt, "browser": BrowserStt}

def make_stt(s: Settings) -> SttProvider:
    chain = [STT_REGISTRY[n](s) for n in s.stt_chain]        # e.g. ["openai", "faster-whisper"]
    return FallbackStt(chain)
```

- `stt_chain` and `llm_provider` come from `.env` / settings; adding a provider = one file + one registry line.
- `FallbackStt` replaces the if-chain in the transcribe route and the duplicate decision in `active_stt_engine()`, so `/api/health` and the route cannot disagree.
- Candidates for later benchmarking: `openai` (whisper-1), `openai-mini` (gpt-4o-mini-transcribe), `faster-whisper`, **MedASR** (Google, open weights, Jan 2026).

---

## 4. Bug fixes — phase B0 (tests first)

| Fix | Change | Test that must fail first |
|---|---|---|
| Blank-name rows | In the merge, a patch row with a blank name is never appended. If exactly one existing row is missing the stated field, fill it; otherwise drop the row and surface "could not tell which medicine". | Ascoril repro above: result has exactly 1 row; strength and duration are filled |
| Correction prompt | Give it the same schema and dose/timing rules as the format prompt, plus "every rx row must include the medicine name" | `ageSex` format matches `"N / M"` after a correction |
| Validation off the loop | `asyncio.to_thread(validate_structured, …)` at the two async call sites | Concurrent-requests test: loop is not blocked >5 ms by validation |
| Upload cap | Reject audio over a configured size with a clear 413 | Oversize upload returns 413 |

Every fix: write the failing test, watch it fail, then fix. No bundled refactoring.

---

## 5. Accuracy work

### 5.1 Technique 1 — vocabulary hint
Send a `prompt` to the cloud Whisper call built from `hints` (about 70 words fit the ~224-token limit). Hints come from: the doctor's most-used medicines (once §6 exists) plus the most common lexicon entries. **Risk:** the research found prompt biasing can raise errors on common words, so it ships only if the benchmark (5.4) shows a net gain.

### 5.2 Technique 2 — candidates, then the LLM chooses
For each medicine not matched exactly in the lexicon:
1. Generate sound-alike candidates (existing `difflib` plus a phonetic code such as Double Metaphone).
2. Add the top 3 to the existing repair message sent in the grounding loop.
3. The LLM picks one or answers "none". On "none" the row stays `unknown-medicine` and the doctor decides. **Never auto-accept.**

Also grow the lexicon beyond the current 444 entries. Source for Indian brand names: **not yet evaluated** (open question §11).

### 5.3 Technique 3 — trim silence
Run silence removal before upload with ~300 ms padding so words are not clipped. Record seconds removed per request. Expected saving depends on how much of each recording is pauses; **unmeasured**.

### 5.4 Technique 6 — benchmark harness (built first)
`tests/stt_bench/`: 50–100 real, consented, de-identified dictations with correct text. Report word error rate, **drug-name recall** and cost per minute for each provider through the factory. Synthetic (text-to-speech) audio is not acceptable as the main test set: it does not reflect real speech.

**Acceptance:** each technique 1, 2 and 3 is kept only if the benchmark shows it improves drug-name recall without a worse overall error rate.

---

## 6. Knowledge layer (graph) — relational first

Plain-English: a notebook of what each doctor actually prescribes, plus a separate pencil list of AI ideas.

```
Doctor ─prescribed(n=212, usual dose 1-1-1)→ Paracetamol 650   [observed]
Viral URTI ─co-prescribed(n=88)→ Cetirizine                     [observed]
Paracetamol ─interacts_with→ …                                  [vetted source]
Cetirizine ─alternative_to→ Levocetirizine                      [proposed, unverified]
```

- **`observed`** links are counts from the doctor's own finalized prescriptions: fully deterministic.
- **`vetted`** links (interactions, allergies) come only from a trusted medical source, never from an LLM.
- **`proposed`** links come from the LLM and appear in a separate "AI suggests" lane that always needs confirmation.
- Cold start (new doctor, no history): fall back to the general lexicon plus flagged proposals.

**Storage:** relational tables first (edges with `source` and `count`), built from finalized documents. A `GraphStore` interface exists with an **optional Apache AGE adapter** (openCypher inside PostgreSQL). Postgres remains the source of truth; the graph is rebuildable.

**Privacy rule:** the graph holds pseudonymous IDs only. Names and OP numbers stay in the relational database.

**Evaluation spike (separate, throwaway):** run the same five queries on Neo4j Community, Memgraph and Apache AGE (ArcadeDB optional) and compare results, memory, restart time and driver friction. Output is a recommendation; no code kept.

---

## 7. AI-native hook (design only, not built)

The correction endpoint is already a one-tool assistant. The factory keeps `complete(messages, tools)` so a later assistant can call tools such as: look up the patient's last encounter by OP number, check allergies against a vetted source, draft a letter. Rule: **no tool acts without the doctor's confirmation.** Example: "same as last time for Rahul Sharma but stop the Azithromycin" → assistant proposes a diff against the last encounter; the doctor confirms.

Out of scope here: building these features, any diagnosis or dosage suggestion, and anything that might change regulatory classification (not researched; see §11).

---

## 7A. Letterhead template (built once per clinic by a vision LLM) and server-side PDF

Plain English: the clinic uploads one image of its blank prescription pad. A vision LLM **recreates** it as a clean A4 layout and reads the doctor and clinic details off it. The clinic sees the recreated page, edits any text that was misread, and accepts. From then on every PDF prints on that layout. The LLM is used **only at setup**; printing never calls it.

*Interpretation to confirm:* "create a copy" means a recreated layout (text, lines, logo, blank area), not a pixel-exact reproduction and not an image-generation model.

### 7A.1 Workflow
1. **Upload** one image of the blank pad (scan or phone photo, any size or shape).
2. **Clean** the file: accept JPEG, PNG and HEIC (iPhone photos), checked by content, not file name; cap size and pixels; fix rotation; strip metadata (phone photos carry GPS).
3. **Recreate:** the vision LLM returns a layout description (§7A.2) and the profile details it can read.
4. **Review:** the clinic sees page 1 rendered with a sample prescription in the blank area, plus an editable list of every text line (the profile). It can fix text, **accept**, or **re-upload**.
5. **Accept:** the layout and profile are saved as the clinic's active template. One-time per clinic; re-upload is allowed at any time.

Rules: a draft never prints until accepted; an accepted template stays active until a newer one is accepted; if the clinic never accepts one, PDFs use the **built-in layout with details printed from the profile** (§7A.6). That fallback is today's behaviour.

### 7A.2 What the LLM returns (constrained, never raw HTML)
The model returns JSON in a small fixed vocabulary; the server validates it and renders it with its own code.

```json
{
  "header": [
    {"type": "logo", "crop": [0.05, 0.02, 0.20, 0.10], "align": "left"},
    {"type": "text", "field": "doctor_name", "role": "title", "align": "center", "color": "#1a3c6e"},
    {"type": "text", "field": "qualifications", "role": "small", "align": "center"},
    {"type": "rule", "color": "#1a3c6e", "thickness": "thin"}
  ],
  "footer": [{"type": "text", "field": "address", "role": "small", "align": "center"}],
  "body": {"top": 0.22, "bottom": 0.92},
  "profile": {"doctor_name": "…", "qualifications": "…", "reg_no": "…",
              "clinic_name": "…", "address": "…", "phone": "…"}
}
```

- Block types: `text`, `logo`, `rule`. Text is either a **profile field reference** or a short literal (for a tagline).
- Roles come from a fixed set (`title`, `subtitle`, `normal`, `small`) mapped to fonts the app embeds; colours must be hex; positions are expressed only as alignment and order; `crop` and `body` are fractions of the image height or width.
- `body.top` and `body.bottom` define the **blank printable area**; it is the page between header and footer.
- The profile fields are the six the app already stores (doctor name, qualifications, registration number, clinic name, address, phone).
- Anything unreadable or handwritten is left out and flagged for the clinic to fill in.

### 7A.3 Review screen (kept deliberately small)
Rendered page-1 preview (same renderer as real PDFs, so what is shown is what prints), an input for each text line, and three actions: **Accept**, **Re-upload**, **Use built-in layout instead**. No drag boxes, no straighten, no fit modes. If the blank area is wrong, the clinic re-uploads; manual adjustment is deferred (§10).

### 7A.4 Data and interface (names illustrative)
- `templates` table: id, clinic, layout JSON, logo crop image (small), status (`draft`, `active`, `archived`), created-at. D0: one active per clinic; D1: per doctor.
- Endpoints: upload (creates a draft and calls the LLM), preview, accept, discard, get active. All behind the D0 login; each action is written to `audit_log`.
- The LLM provider interface accepts **image input** (§3.1). Whether the configured model accepts images is unverified; a separate setting can name a vision-capable model for this task only.
- Frontend: one new panel next to Profile, vanilla JS like the rest of the UI.

### 7A.5 Renderer decision
**Default: the existing headless Chromium path, but pooled** (one long-lived browser owned by a worker thread, instead of a launch per save), behind a small `PdfRenderer` interface so another engine can replace it. Reason: it already works, and it renders Indian-language text through the system fonts. Alternatives (an HTML-to-PDF library such as WeasyPrint, or a drawing library such as ReportLab) stay an optional later spike if memory use or image size becomes a problem. This replaces the earlier plan to run a comparison spike first.

### 7A.6 PDF behaviour rules
- Header and footer print on **page 1 only**. The body flows in the blank area and, if it overflows, continues on page 2 onward as continuation pages with standard margins and **one small identifier line: patient name, OP number, date and page number** (decided 2026-10-13, so a separated page cannot be mistaken for another patient's).
- A minimum font size applies; below it text moves to the next page instead of shrinking.
- No active template: use the built-in layout with the profile details.
- Rendering stays fail-soft: a failure never blocks Save; browser print remains the last resort.
- All dictated values stay HTML-escaped as today.

### 7A.7 Sequencing inside B2 (each step shippable)
1. Server PDF on the built-in layout via the chosen renderer.
2. Layout vocabulary, validator and renderer, tested with fixed example layouts.
3. Upload, clean, vision-LLM call (stubbed in tests) producing a draft layout and profile.
4. Review screen: preview, edit lines, accept, re-upload.
5. Active template used at save, with the built-in layout as fallback.

Tests: validator rejects unknown block types, out-of-range fractions, non-hex colours and overlong text; the renderer is checked against recorded example layouts; the LLM call is stubbed. The existing 122 tests stay green.

### 7A.8 Security and privacy
- **LLM output is untrusted:** only schema-validated JSON is used, text is escaped, raw HTML from the model is never rendered. Text inside the image that tries to instruct the model cannot change anything beyond the allowed fields.
- The upload screen states the image must be a **blank** pad; a used prescription may contain a patient's name. The image is sent to the LLM provider.
- Cap upload size and pixels, strip metadata, never serve images from a public path. Drafts and their images expire if not accepted within a set time; the original is deleted once the template is accepted.
- Limit uploads per clinic per day, since each upload costs one LLM call.
- **Fidelity limit:** the copy is an approximation. Watermarks, background art and elaborate borders are not reproduced. If clinics reject copies often, the documented upgrade path is the image-as-background approach (§10).

---

## 8. First deployment (D0) — demo, fake patients only

### 8.1 Shape
One container running the FastAPI app (it already serves the frontend), a persistent volume for SQLite, PDFs and template images, HTTPS in front. No graph database and no Postgres. The PDF renderer is chosen in §7A.5.

### 8.2 Decisions for D0

| Item | D0 choice | Reason |
|---|---|---|
| **PDF** | **Server-side PDF with the doctor's template (§7A).** Browser print stays as the fail-soft fallback (`main.py:962-982`; not yet exercised end-to-end). | Doctors need prescriptions on their own pad; Chromium per save is too heavy, so the renderer comes from the §7A.5 spike |
| **Auth** | App middleware requiring HTTP Basic credentials from environment variables; constant-time compare; off in tests | Smallest thing that keeps the public out; the schema already has a `users` table for D1 |
| **CORS** | Restrict to the app's own origin (replace the allow-all) | Open CORS plus open endpoints is unsafe |
| **Banner** | Persistent "Demo — fake patients only" banner | Prevents real data entering |
| **Secrets** | Environment variables on the host; never in the image | `.env` is gitignored but must not be baked in |
| **Workers** | Worker count = CPU cores (`uvicorn` workers) | Event loop is single-threaded per process |
| **STT/LLM** | Cloud (OpenAI) | No GPU, no local model in the image |
| **HTTPS** | Required | Browsers allow the microphone only on secure origins |
| **Storage** | One volume holding the SQLite file, PDFs and template logo crops; single instance | SQLite has one writer |
| **Image** | Python 3.12 slim, `backend` deps plus the imaging and PDF libraries chosen in §7A.5; no `faster-whisper` | Keeps the image small; the renderer may add system libraries or a browser |

### 8.3 Concurrency settings
Wrap validation in `asyncio.to_thread`; cap upload size; set `uvicorn` workers to cores. The in-process format cache is per worker, which is acceptable for a demo and **must move to a shared store before D1**.

### 8.4 Exit gate — load test
A scripted test of simultaneous dictations **including saves that render a PDF on a custom template** (STT and LLM stubbed) must show: no 5xx, p95 under a threshold agreed before the test, memory stable. The test measures the app, not OpenAI.

### 8.5 Estimated cost (demo scale)
Hosting is small (roughly $5–20/month for one small host plus volume). OpenAI usage dominates and scales with use. **Hosting platform is not chosen** (§11).

---

## 9. Later deployment phases (outline only)

**D1 — one real clinic.** Per-user login on the existing `users` table, access audit on the existing `audit_log`, **Postgres** replacing SQLite, object storage for PDFs, shared cache, backups, per-doctor templates, object storage for template logos and PDFs, consent-based storage of transcripts, and a data-flow review (audio and text go to OpenAI).

**D2 — many clinics.** `tenant_id` throughout, isolation tests, per-tenant provider settings (the factory already takes settings), quotas, reassessing self-hosted STT (§10).

---

## 10. Deliberately deferred, with triggers

| Item | Why deferred | Revisit when |
|---|---|---|
| Streaming transcription | You asked to avoid it; costs about 3× per minute (third-party figure) | A latency complaint |
| LoRA / MedGemma fine-tune | No stored training data; MedGemma license terms not confirmed for commercial use | After the benchmark and a few thousand approved examples |
| Fine-tune or encoder keyword spotting for Whisper | Needs self-hosted weights; research is on general English, not drug names | After self-hosting |
| Self-hosted faster-whisper on GPU | Estimated break-even ~2,500 doctors vs the API, assuming $5k/month operations (my guess) | Volume reaches that range |
| MedASR | Vendor-reported results, US radiology-leaning | Added as a benchmark candidate in 5.4 |
| Go / TypeScript rewrite | No measured benefit | CPU-bound work moves in-process |
| Image-as-background template (straighten, Fit/Fill, drag box, auto-detected box) | Exact look of the pad, but a larger tool; replaced by the simpler LLM-built copy | Clinics often reject the copy's fidelity |
| Manual adjustment of the blank area | Re-upload covers it | The LLM misjudges the area often |
| Per-doctor templates | One template per clinic is enough for the demo | D1 |

---

## 11. Risks and open questions

1. **LLM price** for the configured model is unknown; the cost model uses a placeholder of about $0.008 per dictation. Replace with the real figure.
2. **Dictations per doctor per day** and audio minutes per dictation drive every cost number (assumed 20/day, 1 minute).
3. **Hosting platform** for D0 is open (container host with volume vs a VPS vs serverless containers); to be compared before the plan.
4. **Indian drug-name source** for growing the lexicon is not chosen.
5. **Licenses** (GPLv3, BSL, MedGemma terms, SSPL) were summarised from secondary sources; read the originals and take a legal view before relying on them.
6. **Regulation:** whether suggestion features change medical-device classification was not researched.
7. **Speech accuracy on Indian-accented clinical speech** is unmeasured; the benchmark answers it.
8. **Fallback print path** (no server PDF) has not been exercised end-to-end.
9. **Training data:** storing transcripts needs consent and a retention decision.
10. **PDF renderer:** default decided in §7A.5 (pooled Chromium); an alternative is an optional later spike.
11. **Fonts:** names or advice may contain Indian-language scripts; the renderer must embed suitable fonts (not yet tested).
12. **Vision support:** verified 2026-10-13: `gpt-6-luna` returned "Red" for a solid red test image, so it accepts images. `LLM_VISION_MODEL` (already in `.env`, blank) can stay blank unless a different model is preferred for this task.
13. **Copy fidelity** on real pads is unknown; the review screen and the fallback layout limit the harm, and the check is a handful of real pads in the spike.
14. **Decided (2026-10-13):** HEIC photos are accepted in D0 (adds an image-decoder dependency); the original upload is deleted on accept; unaccepted drafts expire; uploads are rate-limited per clinic; page 2 onward has no header or footer apart from the identifier line (item 15).
15. **Decided (2026-10-13), patient safety:** pages 2 onward carry one small identifier line (patient name, OP number, date, page number); see §7A.6.

---

## 12. Implementation plans

Written one per sub-project, in this order, under `docs/superpowers/plans/`. The index and the shared interface contracts are in `2026-10-13-00-index-and-contracts.md`.

| Plan | Delivers |
|---|---|
| B0a, B0b | Correction fixes; event-loop offload, upload cap, UI warnings |
| B1a–B1e | Package rename, `core/` split, STT providers and factory, LLM providers and factory, API routers |
| ACC1–ACC3 | Benchmark harness; vocabulary hint and silence trim; phonetic candidates for the LLM |
| B2a, B2b1–B2b4, B2c, B2d | Pooled PDF renderer and layout vocabulary; template backend (four parts); template UI; stop using an accepted letterhead |
| C1 (optional) | MedASR provider as a benchmark candidate: licence gate first, needs real clips |
| D0a–D0b | Demo login and hardening; container, proxy, load test and runbook |

Not planned yet: the knowledge layer (§6) and everything in §9 and §10.

---

## Appendix A — Code references

| Claim | Location |
|---|---|
| Dual-import blocks to remove | `backend/main.py:17-90` |
| LLM provider if/else | `backend/main.py:428-444` |
| STT if-chain | `backend/main.py:544-638` |
| Duplicate STT decision | `backend/main.py:153-176` |
| Cloud STT call without a prompt | `backend/main.py:529` |
| Local STT `initial_prompt` | `backend/main.py` `STT_DECODE` (~line 120) |
| Grounding and repair loop | `backend/main.py:689-703` |
| Validation inside async routes | `backend/main.py:708`, `backend/main.py:767` |
| Correction merge appends unmatched rows | `backend/correction.py:72-81` |
| Correction prompt | `backend/correction.py:28-34` |
| Audio read fully into memory | `backend/main.py:549` |
| Open endpoints / CORS allow-all | `backend/main.py:775`, `backend/main.py:221` |
| PDF fail-soft on save | `backend/main.py:962-982` |
| Chromium launched per render | `backend/pdf.py:195` |
| Format cache is a dict | `backend/determinism.py:51` |
| Fixed built-in sheet layout | `backend/pdf.py` (`build_sheet_html`) |
| SQLite path and PDFs on disk | `backend/db/__init__.py:27`, `backend/db/__init__.py:45` |
| Only transcript hash stored | `backend/db/__init__.py:334`, `backend/db/migrations/001_init.sql` (`transcript_sha`) |
| `users` and `audit_log` tables exist | `backend/db/migrations/001_init.sql` |
| Baseline | 122 tests pass in ~1 s |

## Appendix B — Evidence and its quality

| Topic | Source type | Caveat |
|---|---|---|
| CPU per request ~10.4 ms | Measured here (normalize + validate only) | Excludes PDF render and network |
| Whisper price $0.006/min; mini ~$0.003/min | Third-party summaries | Confirm on OpenAI's page |
| Lambda, VPS, GPU prices | Third-party trackers | Disagree with each other in places |
| Prompt biasing helps rare words, hurts common words | arXiv 2502.11572 (read in full) | General English, not drug names |
| Fine-tuned biasing: rare-word error 18.0% → 11.2% | Same paper | Needs model weights |
| MedSpeak WER 7.72% → 2.99% (average) | arXiv 2602.00981 (read in full) | Synthetic speech; needs fine-tuned 8B model |
| KWS-Whisper | arXiv abstract only | Chinese test sets; method details unconfirmed |
| MedASR | Press and vendor reports | Vendor-reported figures |
| Graph database facts | Vendor pages and aggregators | License texts not read |
| Kuzu archived Oct 2025 | Secondary sources | Single EU-record report for the acquisition |
| Vision-LLM layout recreation and the layout vocabulary | My own design; nothing tested | Fidelity on real pads and the configured model's image support are unverified |
