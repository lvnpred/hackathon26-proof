# Count Guard operations agent, option C (design)

Owner decision, 31 Oct: "go ahead with option C spec". Owner accepted the §10 calls as written ("sure write the plan"). This spec turns option C from `2026-10-30-count-guard-ai-native-clinic-options.md` into a buildable design. Work items use option D's format, so a later move to several agents needs no data change.

## Summary (one page)

**What it is.** One AI agent runs the ward's operations between human taps. It does the safe, non-clinical step itself, tells the owner, and keeps an undo. For every clinical step it prepares a draft that a named person approves with one tap. It never prescribes, changes a dose, advises a patient, clears a count or discharges.

**How it decides.** The behaviour comes from three plain-code parts. The model has only a narrow job.

```
event written / clock tick
        │
        ▼
 Watcher (rules)  ──►  work item  ──►  Planner (rules pick the action; model only drafts text)
                                              │
                                              ▼
                                   Policy gate (level table)
                     ┌───────────┬────────────┬────────────┬───────────┐
                    L3          L2           L1          Never
                 do + log   do + undo 10m  proposal     drop + log
                     └───────────┴─────┬──────┴────────────┘
                                       ▼
                         ordinary events in the store, "by: AI"
```

**What changes on screen.**
1. An "AI is handling" strip on every chart and on My patients.
2. An "AI did this" feed with **Undo** and **Why**.
3. Proposal cards with **Approve / Edit / Reject** in the owner's inbox.
4. An "AI: running / paused" chip with a kill switch in the demo dock.

**Day one at L2 (act with undo), my call:**
- acknowledge and schedule signed orders;
- obs-overdue nudges;
- routing a patient question to the free doctor;
- filing camera and photo reads.

**Demo, my call:** no new beat. The agent acts inside the existing beats, for example "AI acknowledged Dr. A. Rao's orders · Undo" at 09:02. The 58/58/58 s timing stays. A one-hour time-lapse is a later option (§9).

**Cost:** 11 days. That is the 10 d from the options doc plus 1 d for the D-format work items.

**Decisions for the owner** (§10): the day-one L2 list, the 10-minute undo window and whether to add the time-lapse.

---

## 1. Why

Today a person drives every step: the doctor dictates, the nurse acknowledges, the nurse records, the doctor answers. The AI transcribes, reads and counts only when asked. Option C flips the default: **the AI does the next step unless the step needs a human, and then it prepares the step so the human only decides.**

## 2. Goals, non-goals, anti-goals

**Goals**
- G1. The ward visibly moves between taps: orders get acknowledged, reads get filed and questions reach a doctor without a nurse clicking.
- G2. Every AI action is an ordinary event that is attributed, explained and reversible where allowed.
- G3. The demo stays offline and deterministic: no key, no live call, same output every run.

**Non-goals**
- Multi-agent negotiation (option D). Only the work-item *format* is borrowed.
- Learning or auto-raising levels. Levels change only by config with an audit line.
- New clinical logic. The agent reuses `allowed_moves`, `nudges`, `tasks` and `ask` rules as they are.

**Anti-goals (a failure even if it works)**
- Any AI sentence that advises, or any number not on the ledger. The no-advice regex and the verifier apply.
- An AI action that a person cannot see, explain or undo.
- Approval fatigue: more than 3 proposal cards waiting per role at once in the demo.

## 3. The autonomy ladder

The level, not the model, decides what happens. The levels sit in one table, `backend/app/ops/policy.py`, keyed by action kind.

| Action kind | Level | Undo | Notes |
|---|---|---|---|
| `transcribe`, `read_photo`, `count_camera` | L3 | n/a | already automatic; only labelled "by AI" |
| `nudge_obs_overdue` | L3 | n/a | reuses `nudges.doses_vs_orders` and `obs_vs_limits` |
| `ack_order` | L2 | 10 min | calls `tasks.acknowledge_order` |
| `assign_task` | L2 | 10 min | picks the nurse with the fewest due tasks |
| `route_question` | L2 | 10 min | to the doctor whose status is Available, else the named doctor |
| `file_read` | L2 | 10 min | saves a camera or photo read as the recorded value |
| `draft_answer` | L1 | — | patient question → draft for the doctor, citing rows |
| `propose_move` | L1 | — | e.g. "Send to theatre", only when `allowed_moves` lists it and its `needs` are empty |
| `draft_discharge` | L1 | — | the doctor still signs |
| `prescribe`, `change_dose`, `advise_patient`, `clear_count`, `discharge` | Never | — | refused in the API, not only hidden in the UI |

Rules:
- A kill switch (`ops.paused`) drops every action to L0. The agent still shows work items but does nothing.
- Changing a level writes `ops.policy_changed` with who, from and to.

## 4. Parts

### 4.1 Work item (option D's format)

```json
{
  "id": "wi_01…",
  "episode_id": "…",
  "kind": "ack_order",
  "reason": "order.signed 09:02 not acknowledged",
  "inputs": ["<event id of order.signed>"],
  "owner_role": "nurse",
  "status": "open | doing | done | proposed | dropped | undone",
  "lease": {"holder": "ops-agent", "until_ms": 0},
  "level": "L2",
  "created_by_rule": "orders_unacknowledged"
}
```

- Work items are events: `work.opened`, `work.done`, `work.proposed`, `work.dropped` and `work.undone`. The store stays the single source of truth.
- `lease` is unused while there is one agent (always `ops-agent`). It is in the format so option D can add agents later without migrating data.

### 4.2 Watcher (rules decide *that* something needs doing)

New file `backend/app/ops/watch.py`: `watch(events, at_ms) -> list[WorkItem]`. It is pure and holds one rule per row below. It hooks in where `raise_nudges` already runs: after every write in `_act` (`count-guard/backend/app/journey/api.py:197`) and on `/tick` (`count-guard/backend/app/journey/api.py:324`).

| Rule | Fires when | Work kind |
|---|---|---|
| `orders_unacknowledged` | `order.signed` with no `order.acknowledged` and the state is in `ACK_STATES` | `ack_order` |
| `task_unassigned` | a `task.created` with no assignee | `assign_task` |
| `obs_overdue` | an existing nudge rule fires | `nudge_obs_overdue` |
| `question_waiting` | a patient question with no route | `route_question`, then `draft_answer` |
| `read_unfiled` | a camera or photo read with no saved value | `file_read` |
| `move_ready` | `allowed_moves` lists a move whose `needs` is empty | `propose_move` |

Each rule fires at most once per input event, so it is idempotent like `rules.fresh`.

### 4.3 Planner (rules pick the action; the model only drafts text)

New file `backend/app/ops/plan.py`: `plan(item, events) -> Action`.
- **Who and what** are plain code: the nurse with the fewest due tasks, the Available doctor, the move from `allowed_moves`.
- **Text** (the draft answer or the proposal sentence) comes from a template first. With a key, Spark Open may reword it through the existing path, `handover.reword` (`count-guard/backend/app/journey/handover.py:94`). The result is then checked by `handover.checked` and the verifier (`count-guard/backend/app/agent/verifier.py:17`). Any failure falls back to the template.
- Offline, the demo always uses the template, so runs are deterministic (G3).

### 4.4 Policy gate and actions

New file `backend/app/ops/gate.py`: `apply(store, item, action, at_ms)`.

| Level | What it writes |
|---|---|
| L3 | the action's own events, plus `work.done` |
| L2 | the action's events, plus `work.done` with `undo_until_ms` |
| L1 | `work.proposed` with the draft and its cited rows; nothing else |
| Never | `work.dropped` with the reason |

- Every event the agent writes carries `by: "AI (on behalf of Ward 4)"`, `level`, `reason`, `model` (or `"rules"`) and `inputs`.
- The existing timeline, audit view and provenance chips show these events with no new concepts.

### 4.5 Undo, approve, kill switch (API)

New routes in `backend/app/ops/api.py` under `/journey/episodes/{id}/ops/…`. Every new path joins the Vite proxy allow-list, and the existing care test enforces that.

| Route | Effect |
|---|---|
| `POST work/{wi}/undo` | Inside the window only. Writes `work.undone` and supersedes the action's events through `supersedes_id`. Outside the window: 409 "The undo window has closed." |
| `POST work/{wi}/approve` | Writes the clinical event with the human as author, plus `work.done`. Re-checks `check_move` first. |
| `POST work/{wi}/reject` | `work.dropped` with the human's note |
| `POST /journey/ops/pause`, `/resume` | site-wide kill switch |

Inputs are validated at the boundary: a work id must belong to this episode and be in the right status.

## 5. Screens

- **Chart, under the next-action card:** "AI is handling · 2". The list reads, for example, "Acknowledged Dr. A. Rao's orders · 09:02 · Undo (8 min)". Proposals show "Needs you · 1" with the card.
- **Proposal card:**
  - the draft sentence;
  - "From: <cited lines>";
  - **Approve / Edit / Reject**.
  An approval writes the human as author.
- **"AI did this" feed:** on `/ai`, below the model cards. It shows every L2 and L3 action with **Why**, which expands the work item's reason and inputs, and with **Undo** while the window is open.
- **Demo dock:** an "AI: running" chip and a pause switch.
- **Patient lens:** the patient sees "Your question went to Dr. A. Rao" and never sees work items or levels.

## 6. One morning under this design (demo clock)

| Time | Event | Agent | Level |
|---|---|---|---|
| 09:02 | Dr. A. Rao signs orders | acknowledges them, schedules the tasks, assigns Nurse Asha | L2 |
| 09:11 | obs 1 min late | nudges Nurse Asha | L3 |
| 09:12 | monitor photo read 118/76 | files the obs, closes the task | L2 |
| 09:16 | theatre move is ready | proposal "Send to theatre: open hernia repair" for Dr. A. Rao | L1 |
| 09:20 | camera counts 14 of 15 | raises the count alert; **cannot** clear it | L3 alert, clear = Never |
| Day 3 | patient asks "Is swelling normal?" | routes it to Dr. A. Rao and drafts an answer quoting the discharge card | L2 + L1 |

## 7. Constraints

- `make demo-check MODEL_API_KEY=` stays green, with the same 32 beats and 58/58/58 s. Where a beat's human click becomes an AI action, the beat expects the AI line instead, and the beats, steps and video script change together.
- Never call live models in tests. Files stay under 500 lines. The no-advice regex applies to every template.
- Each new rule, gate path and route gets a test, including:
  - the Never actions refused in the API;
  - an undo after the window;
  - an approve of a move that is no longer allowed.

## 8. Evaluation before raising any level

- A replay harness, `eval/replay_ops.py`, runs recorded demo days through the watcher and gate and reports two numbers:
  - proposal precision (approved ÷ proposed);
  - undo rate (undone ÷ L2 actions).
- An action kind may go up a level only with precision ≥ 0.9 and undo rate ≤ 0.05 over 3 replay days. This is my threshold; adjust it as you like.

## 9. Later (not in this build)

- **Time-lapse beat.** One simulated hour at 4× speed: the agent handles items while staff only approve. It needs its own 20 s beat, so the total would go from 200 s to 220 s.
- **Option D.** Separate agents (front desk, nurse aide, pharmacist, theatre safety) take leases on the same work items.

## 10. Decisions for the owner

1. **Day-one L2 list.** Acknowledge and schedule, assign, route question, file reads (my call)? Or start everything at L1, with proposals only?
2. **Undo window.** 10 minutes (my call), or another length?
3. **Time-lapse beat.** Add it now (+20 s demo, +1 d), or keep it for later (my call)?

## 11. Cost

| Item | Days |
|---|---|
| Work-item events and watcher rules | 2 |
| Planner (templates, optional reword) | 1 |
| Policy gate, undo, approve, kill switch, API | 3 |
| Screens: handling strip, proposal cards, feed, dock chip | 3 |
| Replay evaluation | 1 |
| D-format work items (lease field, owner_role) | 1 |
| **Total** | **11** |
