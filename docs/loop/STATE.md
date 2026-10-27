# Loop state

Dev complete means UC1–UC5 pass on 31 Oct 2026. UC6 stays blocked.
Committed as lvnpred <lvnpred@gmail.com>. Pushed to origin/count-guard on lighterday/hackathon26. GitHub main was not changed.
Questions go in this chat. The hackathon bot is the requested second channel. Its address is not known yet.

| ID | Status | Proof |
| --- | --- | --- |
| UC1 | done | `backend/tests/test_e2e_uc1.py` passed. Guide 6 of 6. PDF and calendar checked. |
| UC2 | done | `backend/tests/test_e2e_uc2.py` passed. Patient B stays empty. |
| UC3 | done | `backend/tests/test_e2e_uc3.py` passed. The sheet uses the camera line. |
| UC4 | done | `backend/tests/test_e2e_uc4.py` passed. Card route is 404. PDF has no advice words. |
| UC5 | done | 41 tests passed. `eval/run_eval.py` exited 0. 3 of 3 planted discrepancies caught. SAM was not called. |
| UC6 | blocked | Real SAM clip and a key. Not part of 31 Oct. |

Updated: UC1–UC5 are done. First commit is eb76d59, then this ledger note. UC6 stays blocked.

## Overnight loop (started 2026-10-27)

The work list is `docs/loop/backlog.md`. One item per turn. The loop needs no input until it stops.

**Gate.** All three must pass at the start and end of every item:

```bash
PYTHONPATH=backend .venv/bin/pytest -q          # baseline: 41 passed
PYTHONPATH=backend .venv/bin/python eval/run_eval.py   # exit 0, 3 of 3 caught
cd frontend && npm run build                     # exit 0
```

**One turn.**

1. If an item agent is still running, wait.
2. Run the gate. If it is red and no item is in progress, stop the loop and report.
3. Take the first item with `Status: open` and `Needs human: no`, P1 before P2 before P3.
4. Copy every file in its `Files:` list to `docs/loop/.snap/<ID>/` (git-ignored). Set `Status: in progress`.
5. Give the item to one fresh subagent: test first, touch only the listed files, no commit, no network, no key, files under 500 lines.
6. Run the gate and the item's `Done when` check.
7. Pass → `Status: done`, plus one proof line. Fail → one retry with the failure output. Fails again → restore the snapshot, `Status: blocked (<reason>)`.
8. A question that changes the product goes in `questions.md`. The item becomes `Needs human: yes`. Do not guess.

**Stop when** no open item is left, three items in a row are blocked, or 30 items have run. Then write a summary here.

**Never:** commit, push, call a paid model, edit `backend/app/core/rules.py` thresholds, or invent detections.

## Overnight loop summary (28 Oct 2026)

Stopped because no item is left that the loop can do alone. 19 of 22 backlog items are done. B2 was finished after Q2 and Q3 were answered (a). Nothing is committed.

Gate at the end: 62 passed (41 at the start), `eval/run_eval.py` exit 0 with 3 of 3 caught, frontend build ok.

| Left | Why |
| --- | --- |
| B4 | Needs `MODEL_API_KEY`, a spend limit and the prop-tray clips (UC6). |
| B14 | Needs `BASETEN_API_KEY` and a model-id choice. |
| B15 | Video, X post, public repo, Q1. |

Open question: Q1 (bot address). Q2 and Q3 closed with (a).

Never checked in a browser: the Live upload buttons, Close errors, the evidence drawer, the OT fact card. The proof for those is the build, greps and curl against a temporary backend.
