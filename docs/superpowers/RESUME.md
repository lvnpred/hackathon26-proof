# Resume point: multi-clinic / multi-doctor build

Last updated 2026-10-14. Spec: `specs/2026-10-14-multi-clinic-multi-doctor-design.md`.

| Plan | File (in `plans/`) | State |
|---|---|---|
| M1 clinic scope + directory | `2026-10-14-m1-clinic-scope-and-directory.md` | Built and reviewed, uncommitted (478 passed, 1 skipped) |
| M2a auth primitives | `2026-10-14-m2a-auth-primitives.md` | BUILT and reviewed, uncommitted (535 passed, 1 skipped; 57 new tests incl. 3 from the final-review fix wave) |
| M2b login over HTTP + UI | `2026-10-14-m2b-login-http-and-ui.md` | BUILT and reviewed, uncommitted (597 passed, 1 skipped). Browser-checked only before the final fix wave; focus rings never checked |
| M2c logout ends only that session | `2026-10-14-m2c-logout-single-session.md` | BUILT, reviewed, uncommitted |
| M3 authorship + profile split | `2026-10-14-m3-authorship-and-profile-split.md` | BUILT, reviewed, uncommitted (655 passed) |
| M4 letterhead scope + OP prefix | `2026-10-14-m4-letterhead-scope-and-op-prefix.md` | BUILT and reviewed, uncommitted (734 passed). Browser-checked for Profile/letterhead items 1-5,7,8 before the fix rounds; PDFs from saved prescriptions and single mode never browser-checked |
| M5 Team screen | `2026-10-14-m5-team-screen.md` | BUILT and reviewed, uncommitted (793 passed). Team UI browser-checked for most flows (not: self/last-user messages, second clinic, single mode, Tab, clipboard fallback, styling) |
| M6 isolation suite + demo | `2026-10-14-m6-isolation-suite-and-demo.md` | BUILT and reviewed, uncommitted (891 passed, 1 skipped). Browser demo run saved under .superpowers/demo-evidence/ (git-ignored); mic/STT/Save UI step used an API fallback |

Next step: all plans (M1-M6, M2c) are built and reviewed. M1-M2b are committed as ae5864c on local `main` (not pushed); M2c, M3, M4, M5, M6 are uncommitted in the working tree. Open items: commit/push decision; rehearse real dictation + real printing by hand; one dry run of `adopt-existing` on a COPY of the real data folder.
Run the suite with `.venv/bin/python -m pytest tests/ -q`.
Open spec s16 items use the plan defaults: 12 h session, 5 fails / 5 min lockout, usernames 3-40 `[A-Za-z0-9._-]`, password 10-200.
