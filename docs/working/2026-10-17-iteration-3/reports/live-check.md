# Live check: Iteration 3 date format (2026-10-18)

Setup: `env -i` with `TZ=Asia/Kolkata`, `MULTI_CLINIC=0`, temp `DB_PATH` (scratchpad `live.db`), `SECRETS_FILE` pointing at a missing file, `OPENAI_API_KEY=` and `DEEPSEEK_API_KEY=` empty, `STT_CHAIN=browser`, port 18431. The app has no dotenv loader (only `os.environ` and `secrets.json`), so the repo `.env` was never read. Server log shows only `/api/format` (engine `fallback-rules+lexicon v1.4.0`), `/api/v1/documents` and GETs. No provider call. Health: `openai_configured:false`, `llm_configured:false`. (Port 8765 was already taken by another process, so 18431 was used.)

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | `/api/health` has `date_locale` and `timezone` | PASS | `"date_locale":"en-IN","timezone":"Asia/Kolkata"` |
| 2 | Sheet date shows `d Mon yyyy` | PASS | `#pDate` text `18 Oct 2026` |
| 3 | Sheet date not editable | PASS | `<span id="pDate" role="textbox" aria-readonly="true" aria-label="Visit date">`; Playwright fill: "element is not editable"; a click then key `x` left the text unchanged |
| 4 | Text dictation, review line, save | PASS (via the page's own `formatTranscript()`; the UI has no transcript text box) | "Review after 1 week" gave `review_date` 2026-10-25, label `(Sun 25 Oct 2026)` |
| 5 | PDF header day equals follow-up base | PASS | `pdftotext`: header `18 Oct 2026 | OP/IP No: OP-20261018-001`, review `Review after 1 week (Sun 25 Oct 2026)` |
| 6 | Reopen shows visit day | PASS | after reopen the sheet shows the document's `visit_date` (see 8 for the changed-day case) |
| 7 | 12-hour time | PASS | Today list `8:36 am`; `Dates.time` gave `3:05 pm` and `4:05 pm` for 09:35Z and 10:35Z; `Dates.dateTime` gave `17 Oct 2026, 3:05 pm` |
| 8 | Re-save on a later day (simulated by `UPDATE documents SET created_at='2026-10-10T05:00:00Z'`) | PASS | GET gave `visit_date` 2026-10-10; reopen showed `10 Oct 2026`; after re-save on 18 Oct the PDF header read `10 Oct 2026`, `review_date` 2026-10-17, label `(Sat 17 Oct 2026)`; `created_at` unchanged |
| 9 | Team page timestamps | NOT DONE | Single mode has no sign-in (`/api/v1/auth/me` and `/api/v1/users` return 404), so the Team page was not opened. `Dates.dateTime` was checked directly (row 7) |

Other observations
- Console shows 4 errors on load: 404 on `/api/v1/auth/me` (twice), `/api/v1/users` and `/favicon.ico`. Expected in single mode; not date related.
- The rules-only path read "three times a day" as dosage `1-0-0`. Not a date issue; not investigated (no LLM was used).
- No screenshot was saved: the Playwright tool can write only inside the repo. Evidence is the text above.
- Server stopped. Port 18431 has no listener (only a browser socket in CLOSE_WAIT remained).
