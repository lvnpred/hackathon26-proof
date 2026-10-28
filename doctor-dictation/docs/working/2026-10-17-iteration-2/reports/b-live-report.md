# I2-b Task 6 live browser check

Date of run: Sat 17 Oct 2026 (server-local day, IST). Server on 127.0.0.1:8803, temp DB, STT_ENGINE=stub, LLM_PROVIDER=stub, blank keys.
/api/health before any step: stt_engine stub, openai_configured false, deepseek_configured false, llm_provider stub (llm_configured true only because the stub counts as a provider).
Method note: the stub LLM returns an empty draft, so the sheets were seeded in-process (repo fallback_format + validate_structured + followup.stamp + prose.unheard, no network) and rendered through the page's real renderSheet / Sections.showProseCheck. Save, review-date route calls and PDF fetches were the page's / app's real routes. The page was driven with Playwright; every request went to 127.0.0.1:8803 (95 requests listed, none elsewhere).
Nothing under doctor_dictation/data/ was opened. No code changed, no commit, no stash (git status: 25 modified files before and after).

## Results

| # | Result | Observed |
|---|---|---|
| 1 | PASS | Titles in order: CHIEF COMPLAINTS & BRIEF HISTORY, DIAGNOSIS / CLINICAL IMPRESSION, INVESTIGATIONS ADVISED, Rx (MEDICATIONS), DIETARY & GENERAL ADVICE, REVIEW / FOLLOW-UP. Titles unchanged. Both lists render as paragraphs (list-style none, one line per sentence, screen-only x delete button at the right). Screenshots taken at 1440 and 390 (removed at cleanup). |
| 2 | PASS | Rules path on the owner transcript: complaints = ["Fever with chills for 3 days, body aches, no vomiting", "No history of similar episodes"]; diagnosis = ["Viral fever"]; no patient/age sentence, no diagnosis sentence; patientName Ravi Kumar, ageSex 34 / M; review "Review after 1 week", review_date 2026-10-24; prose_check []. |
| 3 | PASS | Today Sat 17 Oct 2026. "Review after 1 week" shows (Sat 24 Oct 2026): +7 days, 17 Oct is a Saturday, correct. "2 months" shows (Thu 17 Dec 2026): correct (61 days, Sat+5 = Thu). "next month" shows (Tue 17 Nov 2026): correct. No date for: SOS, if fever persists, Review after 1 week or SOS, 1.5 months, once a week, for 5 days then review. |
| 4 | PASS | Typing clears the date at once (read back empty right after the last keystroke). The route restores it about 420 ms after the last keystroke (400 ms debounce), one call per typing burst. With the route aborted (net::ERR_FAILED) and with a 500 reply: review text untouched, date stays empty, no visible error. A delayed stale answer (the empty-text call held 1.5 s) did not overwrite the newer date. |
| 5 | PASS | Hand edit of history ("..., mild headache"), Save: status "Saved - document 1", GET /api/v1/documents/1 holds the edited text and review_date 2026-10-24. Reopened from the Today list: text, date kept. Unheard-words flag (fed with the server's prose.unheard output for an invented sentence): amber small line directly under the Complaints list, "Not heard in the dictation: photophobia, neck, stiffness. Check this line." Screen only (hidden in print). It does not name which line, only the words. Typing in that list clears it at once. Save with the flag visible was not blocked. The flag is not stored: after reopening, it is gone. |
| 6 | PASS | Saved document PDF via GET /api/v1/documents/1/pdf (pdftotext -layout): CHIEF COMPLAINTS & BRIEF HISTORY (two lines, no bullets) then DIAGNOSIS / CLINICAL IMPRESSION, then investigations, Rx, advice; REVIEW / FOLLOW-UP "Review after 1 week (Sat 24 Oct 2026)". Rx header: #, Medicine, Dosage, Timing, Duration, Instructions (six columns, aligned). |
| 7 | PASS with a caveat | A POST /api/v1/documents with the old shape (lists of strings, review "1 week", no review_date) is stamped by the new Save: the stored document gets review_date 2026-10-24 and its PDF prints "1 week (Sat 24 Oct 2026)". That is by design (Save stamps), but it means an old-shape POST cannot reproduce a pre-feature document. To make a true old document I removed review_date from the stored JSON in the TEMP DB (json_remove, my own temp file) and cleared its pdf_path. Result: opens in the new order, review "1 week" with no date, on-demand PDF prints "1 week" with no date, no JS pageerror. |
| 8 | PASS | Hostile text in complaints, diagnosis and review (saved, reopened, and typed live): rendered as literal text (innerHTML shows &lt;img ...&gt;), 0 img elements in the sheet, window.__x undefined. PDF also prints it as literal text. |
| 9 | PASS | scrollWidth equals clientWidth at 1440, 1024, 768 and 390: no horizontal page scroll. History and review boxes readable (16 px), no clipped content. Date label: beside the review at 1440, wraps under the review text at 1024, 768 and 390 for a long review line. Print media emulation: x buttons, the unheard-words note and all .no-print nodes are display none; the date stays; no bullets. |
| 10 | PASS (order) / NOTE (ring) | Tab order: patient fields, history lines, diagnosis, investigations, Rx cells, advice, review box, then out of the sheet. Each list line is followed by its x button (outline solid 2px red). The editable lines and review box get only the pale-blue background (rule `[contenteditable]:focus`, styles.css:114, present at HEAD) and NO accent outline: `outline:none` (styles.css:121, 124). So no accent focus ring on the new prose lines. Pre-existing pattern, not new in I2-b. |
| 11 | PASS | Console errors: only 404s on /api/v1/auth/me, /api/v1/users, /favicon.ico, plus the failures I injected on purpose (aborted and 500 review-date calls). No pageerror. |

## Defects
None blocking.

## Concerns
1. Focus ring (step 10): history, diagnosis and review lines show only a tint on keyboard focus, no accent ring. Same as the rest of the sheet before I2-b. Owner decision if wanted.
2. The unheard-words note names the words but not the line; with two history lines it is ambiguous which to check (index is available in the response, not shown).
3. Rules path with "Tab Paracetamol 500 SOS for 5 days": the sheet row has strength "" and duration "" (strength 500 and 5 days not extracted; dose SOS only). Outside I2-b scope but visible in the owner example.
4. Print emulation at a 390 px viewport: scrollWidth 405 (Rx table width in print rules); fine at 1024 and screen mode. Real print uses the paper width, so low risk.
5. Empty Investigations and Advice show a "•  —" placeholder on screen and "—" in the PDF (pre-existing).
6. Old documents re-saved from the app get a date at that re-save (Save stamps with the save day). Expected, but a re-saved old document will date from the re-save day, not the original visit day.
7. Race and debounce proven only on the page with a held response; typed bursts produce one call each.

## Cleanup
Server stopped, `lsof -i :8803` empty, browser closed, .playwright-mcp removed from the repo root, temp DB dir and scratch files removed.
