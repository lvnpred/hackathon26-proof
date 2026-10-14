# Resume point: multi-clinic / multi-doctor build

Last updated 2026-10-14. Spec: `specs/2026-10-14-multi-clinic-multi-doctor-design.md`.

| Plan | File (in `plans/`) | State |
|---|---|---|
| M1 clinic scope + directory | `2026-10-14-m1-clinic-scope-and-directory.md` | Built and reviewed, uncommitted (478 passed, 1 skipped) |
| M2a auth primitives | `2026-10-14-m2a-auth-primitives.md` | BUILT and reviewed, uncommitted (535 passed, 1 skipped; 57 new tests incl. 3 from the final-review fix wave) |
| M2b login over HTTP + UI | `2026-10-14-m2b-login-http-and-ui.md` | BUILT and reviewed, uncommitted (597 passed, 1 skipped). Browser-checked only before the final fix wave; focus rings never checked |
| M3 to M6 | not written | policy wiring and authorship (M3), Team screen (M5), etc. |

Next step: M3 (wire policy.can() into routes, per-doctor authorship, move doctor fields from clinic_profile to the user). Open decision: should logout end the session server-side (bump session_version)? Nothing is committed; the user commits.
Run the suite with `.venv/bin/python -m pytest tests/ -q`.
Open spec s16 items use the plan defaults: 12 h session, 5 fails / 5 min lockout, usernames 3-40 `[A-Za-z0-9._-]`, password 10-200.
