# Task 4 report: promotion tools (promote-candidates, promote-apply, ledger)

Status: DONE (uncommitted). Full suite: 1568 passed, 1 skipped, 1 deselected (baseline 1556; +12: the plan's 5 plus 7 extra).

## Files
- Created: `doctor_dictation/promotion.py` (183 lines), `doctor_dictation/core/lexicon/promotion_ledger.json` (`[]` + LF), `tests/test_promotion.py` (12 tests).
- Modified: `doctor_dictation/admin.py` (222 -> 224: import, `promotion.register(sub, COMMANDS)`, docstring line).
- Live `drugs.json`, `imported.json` and every data file untouched. promote-apply ran only against temp copies of the frozen fixture; no clinic DB written (digest test).

## Test first
The plan's 5 tests plus extras written first; failed with `ImportError: cannot import name 'promotion'`. Implementation based on the scratch reference. One change: `apply` catches the `ValueError` that `build.check_source` raises and turns it into `SystemExit` (nothing written yet at that point; pinned by `test_a_refused_source_gate_writes_nothing`).

## Extra tests (7)
read-only URIs and SQL touches only `clinic_formulary` (no patients/documents/users/added_by/write verbs); unreadable clinic -> exit 1, CSV still written, no file created; `--min-clinics` honoured and 0 refused; apply CLI needs reviewer, nothing without `--confirm`, then writes with it; refused source gate writes nothing; removed row with a surviving count never proposed; ledger records key-sorted and row reviewer beats batch reviewer.

## Mutation testing (scratch g4mut, 27 mutants)
Final result: 0 survivors. First pass had 3: removed-name filter (equivalent via confirm_count=0 in `fdb.remove`, so killed with a direct `removed_at` update test), ledger `sort_keys` off, row reviewer override ignored. Killed on the first pass: hash ledger storing names, plain-name key, apply without reviewer, without confirm, reused batch, candidates writing to a DB, rw instead of ro, clinic label leaked, known-name exclusion removed, min-clinics ignored, person-like / reviewed exclusion removed, failed clinic exit 0, CSV not written on failure, decision column prefilled, no-generic merged, failed check merged, checks bypassed, wrong lineage src, ledger unsorted, repo guard off, non-numeric clinics_count, rejects not ledgered, undecided ledgered.

## Concerns
- Review CSV repository guard allows only `doctor_dictation/data/` inside the repo (git-ignored via `.gitignore:37`); other paths outside the repo are allowed. The plan's runbook (`$DATA_DIR/promotion/<batch>/`) matches.
- `read_active` counts any clinic in the directory, including disabled ones, by design (plan).
- Plan text for Task 4 baseline (+17) should read: baseline 1556, now +12 -> 1568.
- A reader who points `DB_PATH` unset in single mode would read the REAL dev DB (read-only); tests always set a temp path.

## Fix round
- Ledger keys are now HMAC-SHA256(PROMOTION_LEDGER_PEPPER, casefolded name). Pepper: env only, 16+ chars, no default, never written; missing/short -> stderr message and exit 2 before any clinic DB is opened or anything is read/written (candidates and apply). Ledger file is now `{"entries": [...], "pepper_check": <8 hex of HMAC(pepper,"dd-promotion-check")>, "version": "dd-promotion-v2"}`, sorted and byte-stable; the committed initial form has `entries: []` and no pepper_check (first apply writes it). A wrong pepper against a ledger with entries or a pepper_check is refused (exit 2, nothing written). Docstring and both CLI helps explain that losing the pepper only means rejected names can be proposed again.
- Reviewed CSV is read with `csv.DictReader(io.StringIO(text, newline=""))` (quoted newline, \x85, \x0b, \x0c stay in one row).
- Candidates re-run `F.clean_name` on every clinic-DB name (failures counted as `invalid-name`); review CSV cells starting with = + - @ tab CR get a leading apostrophe.
- promotion-owned writes (review CSV, ledger) go through temp file + os.replace; test: os.replace failure leaves old CSV and ledger intact, no .tmp left. drugs.json/imported.json writes belong to build.py: left as is (deferred).
- Unreadable clinic: stderr `INCOMPLETE: do not apply (N clinic(s) unreadable)` and `<csv>.INCOMPLETE` marker; promote-apply refuses (exit 2, nothing written) while it exists; a later complete candidate run removes it.
- Tests: 20 in test_promotion.py (+8 new). Mutations (15 scratch mutants: pepper ignored, plain sha256 back, length unchecked, pepper_check not compared/not saved, splitlines reader, clean_name skipped, apostrophe removed, tab prefix dropped, marker ignored/not written, no stderr line, non-atomic write, pepper checked late in candidates and in apply): 1 survivor first (length check, pinned by `test_the_pepper_needs_sixteen_characters`), 0 after.
- Full suite: 1580 passed, 1 skipped, 1 deselected, 1 FAILED: `test_lexicon_import.py::test_a_second_source_appends_...` (`--check` exit 1). Not from this round: build.py (339 -> 343) and lexicon_import.py (189 -> 193) were edited by the parallel review while I worked; it passed at 1568. I did not touch those files.

## Fix round 2
- Pepper now needs 32+ characters (`PEPPER_MIN`); refusal text "PROMOTION_LEDGER_PEPPER is required (32+ characters, keep it outside git)". Documented in `.env.example` (generation command, keep outside git, never a short value, why: the 8-hex check lets anyone test guesses offline), the module docstring and both CLI helps. Tests use a 46-character pepper.
- Refusals: missing reviewer, invalid batch, reused batch each have their own message; every pre-write refusal (also --min-clinics and the review-CSV-inside-repo guard) exits 2 via `die()`. Tests pin messages and codes.
- `apply` re-runs on hand-edited approve rows: name already in the lexicon -> `rejected: in-lexicon`, person-like -> `rejected: person-like`, a name failing `clean_name` -> `rejected: invalid-name` (counted, no ledger entry because there is no name to hash); none is counted as added or merged. Outcome Counter keeps the reason for these.
- INCOMPLETE marker unchanged.
- Mutations (9 scratch): pepper 16 accepted, shared message restored, reused batch exit 1, min-clinics exit 1, repo guard exit 1, in-lexicon exclusion not re-run, person-like not re-run, invalid-name branch removed, reason lost in counter: 0 survivors.
- Tests: test_promotion.py 24 passed with test_file_sizes. Full suite 1692 passed, 1 skipped, 1 deselected on the re-run; the first run had 9 transient failures in `test_ordinary_sentences.py` (the other agent's in-flight test), not in my files. promotion.py 273 lines.
