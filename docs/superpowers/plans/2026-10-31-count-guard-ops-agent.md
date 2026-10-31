# Count Guard Operations Agent (Option C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task stands alone: read the Global Constraints, the Rulings, the Shared Contracts and your own task before you start. The Shared Contracts section holds everything two tasks share.

**Goal:** One rules-driven AI agent moves the ward between human taps. It acknowledges signed orders, assigns their tasks, routes patient questions and files late reads (L2, with a 10-minute undo). It drafts answers and theatre returns for one-tap approval (L1). It refuses the Never actions in the API. `make demo-check MODEL_API_KEY=` stays green with 32 beats at 58/58/58 s.

**Architecture:**
- A new package `backend/app/ops/` holds five pure parts and one router.
  - `policy.py`: the level table.
  - `items.py`: the work-item fold and the view.
  - `watch.py`: rules that decide *that* work is needed.
  - `plan.py`: rules that decide *who and what*, plus template text.
  - `gate.py`: the gate that writes events.
  - `run.py`: the loop.
- `journey/api.py` gains `settle(request, episode_id, ts)`, which runs `raise_nudges` and then `ops.run`. It replaces every route-level `raise_nudges` call, so the agent acts inside the same request (deterministic, R5).
- Every agent output is an ordinary event in the morning store: `work.*`, `task.assigned`, `question.routed`, plus the existing events that the reused helpers write.
- The frontend puts every decision in one pure helper, `care/handling.js`. JSX renders `AiHandling`, `ProposalCard` and `AiFeed`. Every **Why** opens the UX v4 Inspector (R23).

**Tech Stack:** FastAPI + pytest. React 18 + Vite. `node --test` for care and demo tests. playwright-core demo runner.

**Spec (binding):** `docs/superpowers/specs/2026-10-31-count-guard-ops-agent-design.md`. The owner accepted §10 as written:
- Day-one L2: `ack_order`, `assign_task`, `route_question`, `file_read`.
- Undo window: 10 min.
- No time-lapse beat in this build.

**Depends on:** the UX v4 plan `docs/superpowers/plans/2026-10-31-count-guard-v4-ux-ai-moments.md` (the `AiMoment` card and the `Inspector` drawer opened by `openInspector(momentId)`). It runs before this plan. Tasks 8 and 9 need it (R23).

All paths are relative to `count-guard/` unless they start with `docs/`. The demo document is `docs/demo/count-guard-v2-video-script.md`.

## Global Constraints

- Files stay under 500 lines. Validate input at system boundaries: ids, statuses and `by` are checked in the ops routes.
- Records only, no advice. The no-advice regex `/\b(give|take|stop|increase|reduce|start|administer|consider)\b/i` (`frontend/scripts/demo/beats.mjs:3`) applies to all new copy. Model text must also pass `app.agent.verifier.ADVICE`. Each task's tests assert this on its own strings.
- Never call live models in tests or in `make demo-check`. A reword is tested through the injected `app.state.ops_write`.
- Never touch ports 8100/5173. `make demo-check MODEL_API_KEY=` uses 8200/5273.
- Commit once per task with `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit`. Add no Co-Authored-By trailer. Never push or merge.
- Case-insensitive macOS file system: never create `foo.js` beside `Foo.jsx`. Import `.jsx` files with the extension.
- `make demo-check MODEL_API_KEY=` stays green after **every** task. A task that changes a click or a visible string updates `beats.mjs`, `steps.mjs`, `beats.test.mjs` and the demo document in the same commit.

Commands (run from `count-guard/`):
- Backend: `.venv/bin/pytest -q` (baseline about 493).
- Frontend: `cd frontend && node --test src/care/*.test.js scripts/demo/*.test.mjs` (baseline about 297).
- Build: `cd frontend && npm run build`.
- Demo: `make demo-check MODEL_API_KEY=`.
- Each task states "at least" counts above whatever you measure first.

## Rulings

Each ruling has the form: decision — why — cost if wrong.

- **R1 Ward name.** Ruling: `WARD = "Ward 4"` and `AI_BY = f"AI (on behalf of {WARD})"` are constants in `ops/policy.py`. — Why: no ward entity or setting exists. "Ward 4" is the only ward name in the code (`journey/stories.py:60`, the discharge card help line). — Cost: one constant to change. No demo string contains `AI_BY`.
- **R2 Assignment.** Ruling: a new event `task.assigned {task_id, to, by, level, reason, model, inputs}`. The latest visible one per task wins. It is folded by `ops.items.assignees(events)`. `task_list` is not changed. — Why: tasks have no assignee field (`journey/tasks.py:54-110`). An event keeps the store the single truth, and undo becomes a supersede. Leaving `task_list` alone keeps its tests. — Cost: the nurse queue does not filter by assignee yet.
- **R3 Assignment batch.** Ruling: one `assign_task` item per acknowledged order covers all of that order's unassigned `task.created`. Each task goes greedily to the nurse in `NURSES = (seed.NURSE, seed.NURSE_THEATRE)` with the fewest open assigned tasks *in this episode*. A tie goes to roster order. — Why: this keeps the strip short so the ack line stays visible in beats. Counting load across episodes would mean reading every episode on every write. — Cost: the split is not ward-wide. It is one function to change.
- **R4 `file_read` versus the human save.** Ruling: `read_unfiled` fires only when both hold:
  - `FILE_AFTER_MS = 300_000` (5 demo minutes) have passed since the read, with no saved value.
  - The read is either (a) a `proof.checked` whose `values_read` holds `sbp`, `dbp` and `hr`, for an obs task that is still open and has no `task.done` citing that photo, or (b) a `swabs.counted` with a `count` in this theatre stay, a `count.pack_opened`, and no `count.closing` after it.

  The gate writes exactly what the human save writes: `tasks.complete_task(..., values=values_read, proof_id=photo)`, or `count.closing` with `via: "camera"` and the `evidence_id`. — Why: the nurse who took the photo is mid-confirm. Filing first would race her save and lose "Read 14, saved 15 by Nurse Asha". A later human correction still supersedes an AI closing through the existing route (`journey/count_api.py:53-80`) and keeps `read`/`saved`. — Cost: the demo never shows a `file_read`, because `kumar-count` saves in the same minute. Unit tests cover it.
- **R5 Synchronous on write.** Ruling: `settle(request, episode_id, ts)` in `journey/api.py` calls `raise_nudges`, then `ops.run.run(...)`, in the same request. It replaces the route-level `raise_nudges` calls at:
  - `api.py`: `_act`, `/strips`, `/strips/photo`, `/tick`
  - `flow_api.py`: `move` (:57), `_write` (:139), `sign_discharge` (:196)
  - `ask_api.py`: :67, :96
  - `video_api.py`: :226

  `seed_ward` and `play_journey` keep plain `raise_nudges`. `run` loops up to `MAX_PASSES = 3`, so ack → assign settles in one write. — Why: the demo stays deterministic (G3), and the returned view already shows the AI line. The spec's two hook points miss sign and move, because they bypass `_act`. — Cost: extra reads per write, and slower writes when a key is set.
- **R6 Agent switch.** Ruling: `Settings.ops_agent: bool = False` (a dataclass default). `get_settings` reads `CG_OPS_AGENT`, default `"0"`. Task 10 flips the default to `"1"` together with the beats. Ops tests pass `ops_agent=True`. — Why: 25 test files build `Settings` directly, and 7 of them acknowledge by hand, so they would get 409. The demo stays green until the beats change. — Cost: the agent stays off in dev if the flip is forgotten. Task 10 tests the default.
- **R7 Undo of multi-event actions.** Ruling:
  - `work.done.wrote` lists the ids the action appended (the gate diffs event ids before and after the helper call).
  - Undo writes one `work.reverted {work_id, event_id}` per id, newest first, with `supersedes_id=event_id`. Then it writes `work.undone {work_id, by, reverted}`.
  - AI work items whose `inputs` include a reverted id are undone in the same call (one level; for example, the assignment of an undone ack).
  - Undo is refused with 409 when a visible non-AI event references any `wrote` id through `task_id`, `order_id` or `question_id`.

  — Why: one event supersedes one event (`morning/store.py:70`, `morning/discharge.py:8`). An ack writes 1 + N events. — Cost: N + 1 bookkeeping events. The timeline hides `work.reverted`.
- **R8 No re-fire.** Ruling: the idempotency key is `(rule, kind, primary input id)`, checked against every `work.opened`. `work.opened` is never superseded, so undone work never reopens, and a person redoes it. — Why: otherwise undo is re-done on the next write. — Cost: none known.
- **R9 Never at the API.** Ruling:
  - The gate writes `work.dropped` with `code: "never"`.
  - `POST …/approve` on a Never kind returns **403**: `The AI never does this: <words>. A person does it from the chart.`
  - `set_level` raises `ValueError` for a Never kind.

  — Why: 403 means understood but forbidden. It stays distinct from 409 (state conflict) and 422 (bad input). — Cost: one client mapping.
- **R10 Provenance.** Ruling: events written through the reused helpers (`acknowledge_order`, `complete_task`, `count.closing`) keep their payload shape, with `by = AI_BY` wherever the helper takes `by`. `level`, `reason`, `model` and `inputs` sit on the `work.done` that lists them in `wrote`. Events new to ops carry all five fields. `ops_view` exposes `by_event: {event_id: work_id}`. — Why: the spec's non-goal says "reuse rules as they are", and the helpers stay single-path. — Cost: `task.created` has no `by`, so readers join through `by_event`.
- **R11 Kill switch storage.** Ruling: `ops.paused`, `ops.resumed` and `ops.policy_changed` events go on a site episode labelled `OPS_LABEL = "Ward 4 operations (synthetic)"`. It is created on first use and found by label (oldest). This mirrors the staff board (`journey/seed.py:21`). — Why: durable and audited, with no new table. — Cost: one more row in `/morning` episode lists, and one label scan per write.
- **R12 Paused.** Ruling: while paused, the watcher still writes `work.opened` (shown as `Paused · not done`), and the gate does nothing. After resume, the next write or tick plans the open items again. An item a person already did is dropped with `code: "done_by_person"`. — Why: the spec says "shows work items but does nothing". — Cost: a resumed agent acts on a backlog at the next tap.
- **R13 Approval fatigue.** Ruling: an L1 item stays `open` (queued) while `MAX_PROPOSALS = 3` proposals for its `owner_role` wait on this episode. — Why: `run` sees one episode. — Cost: up to 3 per patient, not 3 per ward.
- **R14 Stale proposals.** Ruling: each run drops a proposal whose condition no longer holds. Use `code: "done_by_person"` when a person did the same thing (the question was answered; the patient made the same move). Use `"no_longer_allowed"` otherwise. Replay precision counts `done_by_person` as agreement. — Why: in `kumar-back` and `kumar-review` the human does the step anyway. — Cost: precision is optimistic.
- **R15 `propose_move` scope.** Ruling: only `theatre → ward`, when `allowed_moves` gives it empty `needs`. — Why: "Send to theatre" always needs `["procedure"]` (`journey/states.py:150-166`), so the §6 09:16 example cannot fire under the §3 and §4.2 rule. `clinic → clinic_done` would propose closing every clinic visit. — Cost: §6's theatre proposal is not shown.
- **R16 `draft_answer`.** Ruling:
  - It runs only for a doctor question, and only when a `discharge.card` exists.
  - The template quotes the card's warning signs and its wound-care line verbatim.
  - Approval is doctor-only: `by` must start with `Dr. `, else 403 `Only the doctor approves an answer to the patient.`
  - Approval writes `question.answered` with the doctor as author, `source: "doctor"` and `sources = cited`.
  - **Edit** means approve with `text`. Edit is shown only for text drafts.

  — Why: rows must be cited, and the record has no other card text. — Cost: patients with no card get routing only.
- **R17 Routing.** Ruling: `DOCTORS = (seed.DOCTOR,)`. Pick the first whose `doctor_status.current(doctor, [events], board_events, at_ms)["status"] == "available"`, else `DOCTORS[0]`. `board_events` comes from the newest staff board, found by `seed.BOARD_LABEL`. — Cost: one doctor today, so routing always lands on Dr. A. Rao.
- **R18 `nudge_obs_overdue`.** Ruling: L3. The gate writes only `work.done`. It cites the existing `nudge.raised` (kind `obs_overdue` or `dose_overdue`) and names the task's assignee (R2), else `NURSES[0]`. It writes no second nudge. — Why: nudges are already automatic (`api.py:142`). — Cost: none known.
- **R19 Reword.** Ruling: `plan` passes L1 text through `handover.reword(lines, settings, write, prompt=OPS_PROMPT)` (new kwarg, default `PROMPT`). Then come `handover.checked` and `verifier.check_sentence`. Any failure falls back to the template, with `model: "rules"`. — Why: the spec names Spark Open, but the existing path calls Muse Spark 1.3 (`journey/handover.py:94-108`), and the spec says to use the existing path. — Cost: the model label reads "spark", not "spark-open".
- **R20 Plain wording.** Ruling: `reason`, Why and every line show no event-type names and no snake_case. For example, `Dr. A. Rao signed orders at 09:02; not acknowledged yet.` — Why: staff copy, plus the beat `das-mycare` absent regex. — Cost: none known.
- **R21 Undo clock.** Ruling: windows use demo-clock ms. `undo_until_ms = ts + UNDO_MS` (600 000). The route compares the body's `at_ms` (`ward.act` sends `nowMs`), default `_at`. — Cost: a client can lie about the clock. It is a demo clock.
- **R22 Strip contents.** Ruling: the chart shows the 5 newest `done` AI actions of the episode, any stay, newest first, with **Undo** while the window is open. It also shows the proposals whose `owner_role` is the viewer's role. My patients shows the newest action per patient, plus every proposal for the doctor. The patient sees neither (only `routes`). — Cost: older actions are visible only in the `/ai` feed and History.
- **R23 Why opens the Inspector.** Ruling: every **Why** (handling strip, proposal card, `/ai` feed) calls `openInspector(momentId)` from the UX v4 plan, with a new moment kind `"agent"` that carries `{workId, episodeId, reason, inputs, level, undoUntilMs}`. Its panel shows the reason, the inputs, the level and **Undo** while open. The strip sits directly under the chart's next-action card (`NextCard` `footer`). Requires UX v4 Inspector (plan 2026-10-31-count-guard-v4-ux-ai-moments). This plan does not build the Inspector. It only registers the `"agent"` kind through whatever registration API that plan defines. Read that plan's Shared Contracts first. — Why: one inspection surface for every AI-backed event. — Cost: Tasks 8–9 are blocked until UX v4 lands. If its API differs, only `agentMoment()` and the registration line change.
- **R24 Demo copy.** Ruling: the AI line is `Acknowledged Dr. A. Rao's orders`, the template `` `Acknowledged ${short_name(order_by)}'s orders` ``. The patient line is `Your question went to Dr. A. Rao`. — Cost: four beats and the document change together (Task 10).

## Shared Contracts

**C1. Policy** (`ops/policy.py`, Task 1):

```python
LEVELS = {"transcribe": "L3", "read_photo": "L3", "count_camera": "L3", "nudge_obs_overdue": "L3",
          "ack_order": "L2", "assign_task": "L2", "route_question": "L2", "file_read": "L2",
          "draft_answer": "L1", "propose_move": "L1", "draft_discharge": "L1",
          "prescribe": "Never", "change_dose": "Never", "advise_patient": "Never", "clear_count": "Never", "discharge": "Never"}
NEVER_WORDS = {"prescribe": "prescribe", "change_dose": "change a dose", "advise_patient": "advise a patient",
               "clear_count": "clear a count", "discharge": "discharge a patient"}
UNDO_MS = 600_000; FILE_AFTER_MS = 300_000; MAX_PROPOSALS = 3; MAX_PASSES = 3
WARD = "Ward 4"; AI_BY = "AI (on behalf of Ward 4)"; OPS_LABEL = "Ward 4 operations (synthetic)"
NURSES = (seed.NURSE, seed.NURSE_THEATRE); DOCTORS = (seed.DOCTOR,)
```

**C2. Work events.** The work id is the `work.opened` event id (uuid7, `^[0-9a-f-]{36}$`).
- `work.opened {kind, reason, inputs: [ids], owner_role, lease: {"holder": "ops-agent", "until_ms": 0}, level, created_by_rule, key, by: AI_BY, model: "rules"}`
- `work.done {work_id, level, by, reason, model, inputs, summary, wrote: [ids], undo_until_ms?, approved_by?}`
- `work.proposed {work_id, level: "L1", by, reason, model, inputs, sentence, draft, cited: [{id, text}], action: {...}, owner_role, editable}`
- `work.dropped {work_id, by, reason, code: "never"|"rejected"|"done_by_person"|"no_longer_allowed"|"refused"}`
- `work.undone {work_id, by, reverted: [ids]}`, and `work.reverted {work_id, event_id}` with `supersedes_id = event_id`
- Ops-only actions: `task.assigned {task_id, to, by, level, reason, model, inputs}`, `question.routed {question_id, to, by, level, reason, model, inputs}`

**C3. Dataclasses** (`ops/items.py`, Task 1):

```python
@dataclass(frozen=True)
class WorkItem: kind: str; reason: str; inputs: tuple[str, ...]; owner_role: str; rule: str; key: str
@dataclass(frozen=True)
class Action: kind: str; args: dict; summary: str; sentence: str = ""; draft: str = ""; cited: tuple[dict, ...] = (); model: str = "rules"
```

**C4. `ops_view(events) -> dict`** (Task 1; added to the journey view as `"ops"` in Task 5):

```json
{"handling": [{"work_id", "kind", "level", "summary", "at_ms", "undo_until_ms", "reason", "inputs": [{"id", "label", "when"}], "status": "done|undone"}],
 "proposals": [{"work_id", "kind", "owner_role", "sentence", "draft", "cited", "at_ms", "editable", "reason", "inputs"}],
 "open": [{"work_id", "kind", "reason", "paused_note": "Paused · not done"}],
 "routes": {"<question_id>": "Dr. A. Rao"},
 "assignees": {"<task_id>": "Nurse Meena (synthetic)"},
 "by_event": {"<event_id>": "<work_id>"}}
```

`handling` holds at most 5 items (R22). An input `label` is plain words (R20), for example `Signed orders`.

**C5. Routes** (`ops/api.py`, Task 5). Bodies extend `At` (`extra="forbid"`).

| Route | Body | Result |
|---|---|---|
| `POST /journey/episodes/{id}/ops/work/{wi}/undo` | `by` 1–80 | the journey view |
| `POST …/ops/work/{wi}/approve` | `by` 1–80, `text` 1–1000 optional | the journey view |
| `POST …/ops/work/{wi}/reject` | `by` 1–80, `note` ≤ 300 | the journey view |
| `GET /journey/ops` | none | `{"paused": bool, "by": str \| null}` |
| `POST /journey/ops/pause`, `/journey/ops/resume` | `by` 1–80 | `{"paused", "by"}` |
| `GET /journey/ops/feed?ids=` | `ids` per `ai_api._ids` | `{"items": [handling row + "episode_id", "patient"]}`, newest first, ≤ 30 |

Refusals (exact copy):
- 404 `Work item not found`: the id is malformed, or is not a `work.opened` of this episode.
- 409 `The undo window has closed.`
- 409 `This action cannot be undone.`: the item is not L2 `done`.
- 409 `A person has already acted on this, so it cannot be undone here.`
- 409 `This proposal is no longer waiting.`
- 409 with the `check_move` reason: the move is no longer allowed.
- 403 Never (R9). 403 doctor-only (R16).
- 422 `A person must do this, not the AI.`: `by` starts with `AI`.

**C6. Copy** (each line passes both regexes):
- Summaries:
  - `Acknowledged {Dr} 's orders` (no space before `'s`)
  - `Assigned {n} task(s) to {names}`
  - `Nudged {nurse}: {says}`
  - `Sent the patient's question to {Dr}`
  - `Filed the monitor read {sbp}/{dbp}, pulse {hr}`
  - `Filed the camera count: {n} of {opened} swabs back`
- Proposal sentences: `Draft answer to {patient}'s question`, `Back to ward: {patient}`.
- Draft: `Your discharge card lists these warning signs: {signs joined "; "}. {wound_care}`
- UI:
  - `AI is handling · {n}`, `Needs you · {n}`, `Undo`, `Undo ({m} min)`, `Why`, `Approve`, `Edit`, `Reject`
  - `From: {cited}`, `Paused · not done`, `AI did this`, `AI: running`, `AI: paused`, `Pause AI`, `Resume AI`
  - `Your question went to {Dr}`, `Nothing handled yet.`

## Review Focus

| # | Input or condition the spec implies | Expected behaviour | Pinned by |
|---|---|---|---|
| 1 | Undo after a person used the result (the nurse began or finished a task the AI created). | 409 "A person has already acted…". Nothing is superseded. | Task 5 `test_undo_refused_after_person_acted` |
| 2 | Undo twice, or a write after an undo. | Second undo: 409 "This action cannot be undone." The agent does not re-acknowledge. The Acknowledge button returns. | Task 5 `test_undo_twice_and_no_refire` |
| 3 | Pause in the middle of a flow, then resume. | While paused, orders stay unacknowledged and the item shows `Paused · not done`. On resume, the next write acts, or drops the item if a person acked it. | Task 4 `test_paused_opens_but_does_nothing`, `test_resume_acts_or_drops` |
| 4 | Foreign, malformed or wrong-status work ids; `by` naming the AI; an empty `by`. | 404 / 409 / 422 with the C5 copy. Nothing is written. | Task 5 `test_ops_boundary_validation` |
| 5 | The patient lens. | The patient never sees work items, levels or summaries. The only patient line is `Your question went to Dr. A. Rao`. Patient timeline lines for `work.*` and `task.assigned` are `""`. | Task 4 `test_patient_never_sees_work`; Task 8 `thread.test.js` routed line |

---

### Task 1: Policy table, work-item fold, site switch · 1 d

**Files:**
- Create: `backend/app/ops/__init__.py`, `backend/app/ops/policy.py`, `backend/app/ops/items.py`, `backend/app/ops/site.py`
- Modify: `backend/app/config.py` (`ops_agent` field and env)
- Test: `backend/tests/test_ops_core.py`

**Interfaces:**
- Produces C1, C3 and C4, plus:
  - `items.work_items(events) -> list[dict]`: one dict per `work.opened`. It holds `{"id", "kind", "status", "level", "owner_role", "reason", "inputs", "key", "at_ms", "done": payload | None, "proposed": payload | None}`. `status` is the last of opened → `open`, done → `done`, proposed → `proposed`, dropped → `dropped`, undone → `undone`.
  - `items.assignees(events) -> dict[str, str]`: the latest visible `task.assigned` per `task_id`.
  - `items.routes(events) -> dict[str, str]`: `question_id` → `short_name(to)`, from visible `question.routed` events.
  - `items.ops_view(events) -> dict` (C4).
  - `site.site_episode(store) -> str` (find or create, R11). `site.paused(store) -> tuple[bool, str | None]`. `site.set_paused(store, paused: bool, by: str, at_ms: int) -> None`. `site.board_events(store) -> list[dict]` (`[]` when there is no board).
  - `site.level_of(store, kind) -> str`: the latest `ops.policy_changed` for that kind, else `LEVELS[kind]`. `site.set_level(store, kind, level, by, at_ms)` writes `ops.policy_changed {kind, from, to, by}`. It raises `ValueError` for an unknown kind, a level outside `L0`–`L3`, or a Never kind.
- `Settings.ops_agent: bool = False`. `get_settings()` passes `ops_agent=os.environ.get("CG_OPS_AGENT", "0") == "1"`.

- [ ] **Step 1: Write the failing tests** (build events with a local `_ev(type, payload, id, ts, supersedes=None)` helper; for site tests, `MorningStore(tmp_path / "m.db")`):
  - `test_levels_match_spec`: `LEVELS["ack_order"] == "L2"`, `LEVELS["draft_answer"] == "L1"`, `LEVELS["nudge_obs_overdue"] == "L3"`, `{k for k, v in LEVELS.items() if v == "Never"} == set(NEVER_WORDS)`, `UNDO_MS == 600_000`, `AI_BY == "AI (on behalf of Ward 4)"`.
  - `test_work_status_folds_in_order`: opened → `open`; + done → `done`; + undone → `undone`; a second item opened + proposed + dropped → `dropped`.
  - `test_assignees_latest_visible`: two `task.assigned` for t1 (Meena, then Asha) → Asha. Supersede the second → Meena.
  - `test_ops_view_handling_caps_at_five_newest_first` (7 done items → 5, newest first) and `test_ops_view_no_snake_case`: no `summary`, `reason` or input `label` matches `\b[a-z]+_[a-z_]+\b` or `\b[a-z]+\.[a-z_]+\b`.
  - `test_pause_resume_is_durable`: `set_paused(store, True, "Demo dock (Doctor)", 0)`; a new `MorningStore` on the same path still reads `(True, "Demo dock (Doctor)")`; `site_episode` returns the same id twice.
  - `test_set_level_audits_and_refuses_never`: `set_level(store, "ack_order", "L1", "Owner", 0)` → `level_of == "L1"` and one `ops.policy_changed` with `from: "L2", to: "L1"`. `set_level(store, "prescribe", "L2", …)` raises `ValueError`.
  - `test_settings_default_off`: `get_settings().ops_agent is False` with `CG_OPS_AGENT` unset (monkeypatch `delenv`).
- [ ] **Step 2: Run** `.venv/bin/pytest backend/tests/test_ops_core.py -q`. Expected: FAIL (`ModuleNotFoundError: app.ops`).
- [ ] **Step 3: Implement** the four modules and the Settings field. `ops/*` must never import `app.journey.api` or any `*_api` module, to avoid a cycle with `api.py → ops.run`.
- [ ] **Step 4: Run** the file, then the whole backend suite. Expected: PASS, backend ≥ 500.
- [ ] **Step 5: Commit**: "Count Guard ops: the level table, work items as events and a durable kill switch".

---

### Task 2: Watcher rules · 1 d

**Files:**
- Create: `backend/app/ops/watch.py`
- Test: `backend/tests/test_ops_watch.py`

**Interfaces:**
- Consumes: C1, C3, `items.work_items`, `items.assignees`, `items.routes`. Also reuses `tasks.orders_list`, `tasks.task_list`, `tasks.ACK_STATES`, `states.current_state`, `states.allowed_moves`, `states.stay_events`, `visible_events`.
- Produces:
  - `watch(events, at_ms) -> list[WorkItem]`: only the items whose `key` is not already in a `work.opened`.
  - `stale(events) -> list[tuple[str, str, str]]`: `(work_id, code, reason)` for proposals whose condition no longer holds (R14).
  - `RULES: tuple[str, ...]`.

| Rule | Fires when | Item (`kind`, `owner_role`, `key`) |
|---|---|---|
| `orders_unacknowledged` | an order with `acknowledged_by` None and state in `ACK_STATES` | `ack_order`, nurse, `orders_unacknowledged:ack_order:{order_id}` |
| `task_unassigned` | visible `task.created` with no assignee, grouped by `order_id` | `assign_task`, nurse, key on `order_id`; `inputs` = task ids |
| `obs_overdue` | `nudge.raised` with kind `obs_overdue` or `dose_overdue` | `nudge_obs_overdue`, nurse, key on the nudge id |
| `question_waiting` | `question.asked` with `to == "doctor"`, unanswered, not routed | `route_question` (doctor); plus `draft_answer` (doctor) when a `discharge.card` exists (R16) |
| `read_unfiled` | R4 conditions, `at_ms - read.ts_ms >= FILE_AFTER_MS` | `file_read`, nurse, key on the read id |
| `move_ready` | R15: state `theatre`, `allowed_moves` lists `ward` with `needs == []` | `propose_move`, the role from `allowed_moves`, key `move_ready:propose_move:ward:{last patient.state id}` |

`reason` is plain words (R20). For example: `Dr. A. Rao signed orders at 09:02; not acknowledged yet.` or `The read was not saved within 5 minutes.`

- [ ] **Step 1: Write the failing tests**:
  - `test_orders_rule_waits_for_admission`: an order signed in `clinic` → `[]`. After `patient.state` to `admitting` → one `ack_order`, with `inputs == (order_id,)`.
  - `test_each_rule_fires_once`: `watch` on the same events plus a matching `work.opened` with the item's key → `[]` (R8). The test runs once per rule.
  - `test_tasks_grouped_per_order`: 3 `task.created` with one `order_id` → one `assign_task` with 3 inputs. One task already assigned → 2 inputs.
  - `test_question_routes_and_drafts_only_with_card`: without a card → kinds `["route_question"]`. With `discharge.card` → `["route_question", "draft_answer"]`. A `bot` question → `[]`.
  - `test_read_unfiled_grace_and_saved`: a monitor `proof.checked` with `values_read {"sbp": 118, "dbp": 76, "hr": 80}` at t → `watch(…, t + 299_999) == []` and `watch(…, t + 300_000)` → one `file_read`. A `task.done` with that `proof_id` → `[]`. A strip `proof.checked` (no `values_read`) → `[]`. A `swabs.counted` followed by `count.closing` → `[]`.
  - `test_move_ready_only_theatre_to_ward`: in `ward` → `[]` (needs `procedure`). In theatre after `surgery.ended`, count closed → one `propose_move` with role `nurse`. Count open → `[]`.
  - `test_stale_codes`: a proposed `draft_answer` + `question.answered` by the doctor → `done_by_person`. A proposed move + `patient.state` to `ward` → `done_by_person`. A proposed move + `count.closing` with unaccounted 1 → `no_longer_allowed`.
- [ ] **Step 2: Run** `.venv/bin/pytest backend/tests/test_ops_watch.py -q`. Expected: FAIL (import error).
- [ ] **Step 3: Implement** `watch.py`. Use one function per rule, each `(events, at_ms, opened_keys) -> list[WorkItem]`.
- [ ] **Step 4: Run** the backend suite. Expected: PASS, ≥ 507.
- [ ] **Step 5: Commit**: "Count Guard ops: watcher rules decide that work is needed, once per input".

---

### Task 3: Planner, who and what, with template text · 1 d

**Files:**
- Create: `backend/app/ops/plan.py`
- Test: `backend/tests/test_ops_plan.py`

**Interfaces:**
- Consumes: C1, C3, C6, `items.assignees`, `doctor_status.current`, `ask.short_name`, `states.allowed_moves`.
- Produces:
  - `plan(item, events, *, board=(), at_ms=0, settings=None, write=None) -> Action | None`. It returns None when the work is no longer needed: the order is acknowledged, the question is answered, the task is done.
  - `TEMPLATES: dict[str, str]`.
  - `pick_nurses(events, task_ids) -> dict[str, str]` (R3).
  - `pick_doctor(events, board, at_ms) -> str` (R17).
  - `cited_card(events) -> list[dict]`: `[{"id": card_event_id + ":w{i}", "text": sign}, …, {"id": card_event_id + ":care", "text": wound_care}]`.
- `Action.args` per kind:
  - `ack_order {order_id}`
  - `assign_task {pairs: [[task_id, nurse], …]}`
  - `nudge_obs_overdue {nudge_id, nurse}`
  - `route_question {question_id, to}`
  - `file_read {source: "monitor", task_id, photo_id, values}` or `{source: "swabs", count, evidence_id}`
  - `draft_answer {question_id}`
  - `propose_move {to: "ward"}`
- This task ignores `settings` and `write`, so text is always the template. Task 6 adds the reword.

- [ ] **Step 1: Write the failing tests**:
  - `test_ack_summary`: an order by `Dr. A. Rao (synthetic)` → `summary == "Acknowledged Dr. A. Rao's orders"` and `args == {"order_id": oid}`.
  - `test_pick_nurses_greedy_with_roster_tiebreak`: no load, 3 tasks → Meena, Asha, Meena. With Meena holding 2 open assigned tasks → Asha, Asha, then Meena on the third (tie, roster order). Summary `Assigned 3 tasks to Nurse Meena, Nurse Asha`.
  - `test_pick_doctor_available_else_named`: no board → `seed.DOCTOR`. A board with a manual busy status for Dr. A. Rao → still `seed.DOCTOR` (the named doctor).
  - `test_draft_answer_quotes_card`: `draft` starts with `Your discharge card lists these warning signs: Fever above 38 °C;`. `cited` holds 6 rows whose texts are substrings of `draft`. `sentence == "Draft answer to R. Kumar's question"`.
  - `test_plan_none_when_done`: an acknowledged order → None. An answered question → None.
  - `test_templates_pass_both_regexes`: every rendered summary, sentence and draft from the tests above passes the demo regex and `verifier.ADVICE`.
- [ ] **Step 2: Run** `.venv/bin/pytest backend/tests/test_ops_plan.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `plan.py` with one function per kind behind a dispatch dict.
- [ ] **Step 4: Run** the backend suite. Expected: PASS, ≥ 513.
- [ ] **Step 5: Commit**: "Count Guard ops: the planner picks who and what by rule, with template text".

---

### Task 4: Gate, run loop and the write hook · 1.5 d

**Files:**
- Create: `backend/app/ops/gate.py`, `backend/app/ops/run.py`
- Modify:
  - `backend/app/journey/api.py` (`settle`; `_act`, `/strips`, `/strips/photo`, `/tick`)
  - `flow_api.py`, `ask_api.py`, `video_api.py` (call `settle`)
  - `states.py` (`closing_payload`), `count_api.py` (uses it)
  - `stories.py` (`plain` and `patient_line` for the new events; `timeline_items` skips `work.opened` and `work.reverted`)
- Test: `backend/tests/test_ops_gate.py`

**Interfaces:**
- Consumes: Tasks 1–3, `tasks.acknowledge_order`, `tasks.complete_task`, `tasks.TaskError`.
- Produces:
  - `gate.OpsError(status: int, detail: str)`.
  - `gate.apply(store, episode_id, work_id, item, action, at_ms) -> list[dict]`, per spec §4.4, using `site.level_of`:
    - L3: action events + `work.done`.
    - L2: action events + `work.done` with `undo_until_ms = at_ms + UNDO_MS` and `wrote`.
    - L1: `work.proposed` only.
    - Never: `work.dropped` with code `never`.
    - A `TaskError` from a helper → `work.dropped` with code `refused` and the detail.
  - `gate.drop(store, episode_id, work_id, code, reason, by=AI_BY, at_ms=0)`.
  - `run.run(store, episode_id, at_ms, *, settings, write=None) -> list[dict]`. The order is:
    1. Return `[]` unless `settings.ops_agent`.
    2. Drop `stale`.
    3. Open the `watch` items.
    4. If paused, stop.
    5. For each `open` item, oldest first: if it is L1 and `MAX_PROPOSALS` are already waiting for that role, skip it. Otherwise `plan` it; None → drop with `done_by_person`; else `apply`.
    6. Repeat up to `MAX_PASSES` while new items open.
  - `journey.api.settle(request, episode_id, ts) -> None` (R5). It passes `write=getattr(request.app.state, "ops_write", None)`.
  - `states.closing_payload(events, returned, by, *, evidence_id=None, detail="") -> dict`: the payload `count_api` builds today (opened, returned, unaccounted, detail, by, plus via/read/saved when there is a camera count). It raises `ValueError("Record the pack opened first.")`. `count_api` maps that to 409, with the same copy as now.
  - `stories.plain`: `work.done` → `f"{by}: {summary}."`; `work.proposed` → `f"AI proposal for the {owner_role}: {sentence}."`; `work.dropped` → `f"AI item closed: {reason}"`; `work.undone` → `f"{by} undid an AI action."`; `task.assigned` → `f"{by} assigned a task to {to}."`; `question.routed` → `f"{by} sent the question to {to}."`. `patient_line` returns `""` for all `work.*` and `task.assigned`, and `f"Your question went to {short_name(to)}."` for `question.routed`.

- [ ] **Step 1: Write the failing tests** (an `_ops_client(tmp_path)` that builds `Settings(..., ops_agent=True)` like `tests.test_care_demo._client`; reuse `_seed`):
  - `test_admit_acks_and_assigns_in_one_write`: Kumar → `rx/demo`, sign one dose + one obs item in clinic, then move to `admitting` with a reason. The returned view has `order_list[0]["acknowledged_by"] == AI_BY`, 2 tasks, `ops.handling[0]["summary"].startswith("Assigned 2 tasks to")` and `ops.handling[1]["summary"] == "Acknowledged Dr. A. Rao's orders"`. `now_next.next == "Nurse completes the admission."`
  - `test_l2_done_lists_wrote_and_window`: the ack's `work.done.wrote` holds the `order.acknowledged` id and both `task.created` ids. `undo_until_ms == ts + 600_000`.
  - `test_never_is_dropped`: monkeypatch `plan` to return `Action("prescribe", {}, "x")` for one item → `work.dropped` with code `never`. No other event.
  - `test_l1_proposes_and_caps_at_three`: 4 doctor questions with a card → 3 `work.proposed` for the doctor, and the fourth `draft_answer` stays `open`.
  - `test_seed_and_play_stay_quiet`: `/journey/demo/seed` and `/play` write no `work.*` events.
  - `test_paused_opens_but_does_nothing` and `test_resume_acts_or_drops` (Review Focus 3).
  - `test_file_read_keeps_human_correction`: theatre stay with pack 15, `swabs.counted` count 14, tick at +5 min → the AI writes `count.closing` with `by: AI_BY, via: "camera"`, and returned 14. Then `POST /count` with returned 15, `supersedes_id` set to the AI closing and `by: "Nurse Asha (synthetic)"` → `view["count"]["read"] == {"returned": 14}`, `saved == {"returned": 15}`, `closed_by == "Nurse Asha (synthetic)"`.
  - `test_patient_never_sees_work` (Review Focus 5): every `timeline` item whose type starts with `work.` or is `task.assigned` has `patient == ""`. The `question.routed` line is `Your question went to Dr. A. Rao.`
  - `test_agent_off_by_default_changes_nothing`: `_client` without `ops_agent` → sign and admit leave the order unacknowledged.
- [ ] **Step 2: Run** `.venv/bin/pytest backend/tests/test_ops_gate.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** gate, run, `settle`, `closing_payload` and the stories lines. Replace each listed `raise_nudges` call. Leave `seed_ward` and `play_journey` alone.
- [ ] **Step 4: Run** the whole backend suite. Expected: PASS, ≥ 523, with no existing test edited (R6). Run `make demo-check MODEL_API_KEY=`. Expected: green, because the agent is off by default.
- [ ] **Step 5: Commit**: "Count Guard ops: the gate writes AI actions as ordinary events inside the same write".

---

### Task 5: Undo, approve, reject, kill switch and feed routes · 1.5 d

**Files:**
- Create: `backend/app/ops/api.py`
- Modify: `backend/app/ops/gate.py` (`undo`, `approve`, `reject`), `backend/app/journey/api.py` (`view()` adds `"ops": ops_view(events)`), `backend/app/main.py` (include `ops_router`, `ops_site_router`)
- Test: `backend/tests/test_ops_api.py`

**Interfaces:**
- Consumes: C2, C5, Task 4, `states.move_payload`, `states.MoveRefused`, `ai_api._ids`, `ask_api.ANSWERED`.
- Produces C5, plus:
  - `gate.undo(store, episode_id, work_id, by, at_ms) -> None` (R7, R21).
  - `gate.approve(store, episode_id, work_id, by, text, at_ms) -> None` (R9, R16). For `propose_move`: re-check with `move_payload` and append `patient.state`. For `draft_answer`: refuse an answered question with 409 `ANSWERED`, else write `question.answered` per R16. Then `work.done {approved_by: by, level: "L1", wrote}`.
  - `gate.reject(store, episode_id, work_id, by, note, at_ms)`: `work.dropped` with code `rejected` and reason `note or "Rejected"`.
  - The routes call `settle` after each write and return `view(...)`.

- [ ] **Step 1: Write the failing tests**:
  - `test_undo_inside_window_restores_acknowledge`: after the Task 4 admit, `POST …/ops/work/{wi}/undo {"by": "Nurse Meena (synthetic)", "at_ms": ts + 60_000}` → 200. `order_list[0]["acknowledged_by"] is None`. `tasks == []`. The assignment item shows `status == "undone"` (cascade). There are 4 `work.reverted` events, each with `supersedes_id`.
  - `test_undo_after_window_409`: `at_ms = ts + 600_001` → 409 `The undo window has closed.`
  - `test_undo_refused_after_person_acted` (Review Focus 1): begin or finish one created task, then undo the ack → 409. The event count is unchanged.
  - `test_undo_twice_and_no_refire` (Review Focus 2).
  - `test_approve_move_no_longer_allowed`: the `propose_move` item after `surgery.ended`. Then a `count.closing` with unaccounted 1 is written directly to the store (the stale pass has not run). Approve → 409 whose detail is the `check_move` reason (`The closing count is open. A reason is needed…`).
  - `test_approve_draft_is_doctor_only_and_writes_doctor_answer`: `by: "Nurse Meena (synthetic)"` → 403. `by: "Dr. A. Rao (synthetic)", text: "Edited."` → `ask.questions[-1].answer.text == "Edited."` with `source "doctor"`, and the item is `done`.
  - `test_never_refused_in_api`: append `work.opened` + `work.proposed` with kind `clear_count` directly. Approve → 403 `The AI never does this: clear a count. A person does it from the chart.`
  - `test_ops_boundary_validation` (Review Focus 4): another episode's work id → 404. `"nope"` → 404. Approve on a `done` item → 409 `This proposal is no longer waiting.` `by: "AI (on behalf of Ward 4)"` → 422. `by: ""` → 422.
  - `test_pause_resume_routes`: `GET /journey/ops` → `{"paused": False, "by": None}`. Pause → `True`. Resume → `False`.
  - `test_feed_lists_actions_across_roster`: `/journey/ops/feed?ids=<kumar>,<iyer>` items carry `episode_id`, `patient == "R. Kumar"` and newest first. Eleven ids → 422.
- [ ] **Step 2: Run** `.venv/bin/pytest backend/tests/test_ops_api.py -q`. Expected: FAIL (404 routes).
- [ ] **Step 3: Implement** the routes and the gate functions. Check `wc -l backend/app/journey/api.py` < 500.
- [ ] **Step 4: Run** the backend suite and `make demo-check MODEL_API_KEY=`. Expected: PASS, ≥ 534; demo green.
- [ ] **Step 5: Commit**: "Count Guard ops: undo inside 10 minutes, approve or reject proposals, a kill switch and the AI feed".

---

### Task 6: Planner text, an optional model reword with fallback · 0.5 d

**Files:**
- Modify: `backend/app/journey/handover.py` (`reword(..., prompt=PROMPT)`), `backend/app/ops/plan.py` (`_worded`)
- Test: `backend/tests/test_ops_plan.py` (add)

**Interfaces:**
- `plan.OPS_PROMPT: str`: "Reword these record lines as one short plain sentence for a doctor to approve. Add no number, medicine or instruction that is not in the lines."
- `plan._worded(template: str, cited: list[dict], settings, write) -> tuple[str, str]`. It returns `(text, model)`. It calls `reword(lines, settings, write, prompt=OPS_PROMPT)`, then `handover.checked(text, lines)`, then `verifier.check_sentence(text, evidence_ids=[], known_ids=set(), figures={f"n{i}": int(n) for i, n in enumerate(numbers in cited)}, claims={})`. The result is `(text, "spark")` when every check passes, else `(template, "rules")`. Only L1 `sentence` and `draft` are reworded. Summaries stay templates.

- [ ] **Step 1: Write the failing tests**:
  - `test_reword_used_when_checked`: `write=lambda p: "Your discharge card lists fever above 38 °C as a warning sign."` gives `model == "spark"`.
  - `test_reword_with_advice_falls_back`: a reply holding "should" → the template, `"rules"`.
  - `test_reword_new_number_falls_back`: a reply with `"72 hours"` → the template.
  - `test_no_key_no_write_is_template`: settings without a key, `write=None` → the template, `"rules"`, and no network (`no_network` fixture).
  - `test_handover_prompt_default_unchanged`: `reword(lines, settings, write=capture)` still sends the old `PROMPT`.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the backend suite. Expected: PASS, ≥ 539.
- [ ] **Step 5: Commit**: "Count Guard ops: draft text may be reworded by the model and falls back to the template on any check".

---

### Task 7: Frontend helpers and proxy · 0.5 d

**Files:**
- Create: `frontend/src/care/handling.js`, `frontend/src/care/handling.test.js`
- Modify: `frontend/vite.config.js` (`journeyApi` adds `"/journey/ops"`), `frontend/src/care/dock.js` + `dock.test.js`, `frontend/src/care/thread.js` + `thread.test.js`

**Interfaces** (all pure):
- `handling.js`:
  - `stripTitle(n) -> "AI is handling · n"`. `needsTitle(n) -> "Needs you · n"`.
  - `undoLabel(untilMs, nowMs) -> "Undo (m min)" | ""`, with `m = Math.ceil((untilMs - nowMs) / 60000)`. It returns `""` when `untilMs` is null or `nowMs >= untilMs`.
  - `handlingRows(ops, nowMs) -> [{workId, text, when, undo, level}]`. `text` is `displayName(summary)`. `when` is `hhmm(at_ms)`.
  - `proposalsFor(ops, role) -> []`: `owner_role === role`, never for `patient`.
  - `citedLine(cited) -> "From: a; b"`.
  - `agentMoment(row, episodeId) -> {kind: "agent", workId, episodeId, reason, inputs, level, undoUntilMs}` (R23).
  - `feedRows(feed, nowMs)`, and `isFeed(out) -> boolean`.
  - `myPatientsStrip(patients, role) -> {rows: [{episodeId, name, text}], proposals: [{episodeId, name, p}]}`.
  - `STAFF_BY = {doctor: "Dr. A. Rao (synthetic)", nurse: "Nurse Meena (synthetic)"}`. `OPS_SCOPE = "/ops/"`.
- `dock.js`: `aiChip(paused) -> "AI: running" | "AI: paused" | ""` (`""` for null). `pauseLabel(paused) -> "Pause AI" | "Resume AI"`.
- `thread.js`: `routedLine(view, questionId) -> "Your question went to Dr. A. Rao" | ""`, read from `view.ops.routes`.

- [ ] **Step 1: Write the failing tests**. Assert:
  - `undoLabel(600_000, 120_000) === "Undo (8 min)"`, `undoLabel(600_000, 600_000) === ""` and `undoLabel(null, 0) === ""`.
  - `handlingRows` keeps order and strips `(synthetic)`.
  - `proposalsFor(ops, "patient")` deep-equals `[]`.
  - `agentMoment` carries `kind: "agent"`.
  - `aiChip(null) === ""`.
  - `routedLine` reads `routes`.
  - Every C6 UI string passes `ADVICE`.

  The existing proxy test in `ai.test.js` fails once a component names `/journey/ops`. That happens in Task 9; add `"/journey/ops"` now.
- [ ] **Step 2: Run** `cd frontend && node --test src/care/handling.test.js src/care/dock.test.js src/care/thread.test.js`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** all frontend tests. Expected: PASS, ≥ 306.
- [ ] **Step 5: Commit**: "Count Guard ops: pure helpers for the handling strip, proposals, feed and dock chip".

---

### Task 8: Chart strip, proposal cards, My patients and the patient lens · 1.5 d

Requires UX v4 Inspector (R23).

**Files:**
- Create: `frontend/src/care/AiHandling.jsx`, `frontend/src/care/ProposalCard.jsx`
- Modify:
  - `NextCard.jsx` (optional `footer` prop rendered last inside the section)
  - `StatePanel.jsx` (builds `<AiHandling …/>` once; passes `footer` to `DoctorActions` and `NurseActions`, which pass it to `NextCard`)
  - `MyPatients.jsx`, `Thread.jsx`, `care.css`, `styles.test.js`
  - the UX v4 Inspector registry (add the `"agent"` kind panel: reason, inputs, level, Undo)

**Interfaces:**
- `<AiHandling view role nowMs act episodeId busy fault />` renders `<section className="ai-handling" aria-label="AI is handling">`, containing:
  - `<p className="label">{stripTitle(n)}</p>`.
  - One `<li>` per `handlingRows` row: `{text} · {when}`, a `<button>` named **Undo** with `undoLabel` as visible text only while open, and a `<button className="linklike">Why</button>` calling `openInspector` with `agentMoment`.
  - `Nothing handled yet.` when there are no rows.
  - `{needsTitle(k)}` followed by one `ProposalCard` per `proposalsFor(view.ops, role)`.
  - `<Fault … only={[OPS_SCOPE]} />`.

  It renders nothing for the patient role. Undo is `act(\`/ops/work/${id}/undo\`, { by: STAFF_BY[role] }, OPS_SCOPE + "undo")`.
- `<ProposalCard p act busy role />` renders `<article className="proposal-card" aria-label="AI proposal">` with the sentence, the draft, `citedLine`, and the buttons **Approve**, **Edit** (only when `p.editable`; opens a textarea labelled `Answer to send`, then **Approve** sends `text`), **Reject** and **Why**. No button may be named like an existing step button ("Back to ward", "Send to R. Kumar").
- `MyPatients` renders, under the status menu, `<section aria-label="AI is handling">` from `myPatientsStrip`: one row per patient linking to `/chart/{id}`, then the doctor's proposal cards, which act through `ward.act(episodeId, …)`.
- `Thread.jsx`: an unanswered doctor row adds `<p className="small">{routedLine(view, item.id)}</p>` when that line is not empty.
- CSS: `.ai-handling`, `.proposal-card`, reusing the existing `.card` tokens.

- [ ] **Step 1: Write the failing tests**:
  - `styles.test.js` asserts `.ai-handling` and `.proposal-card`.
  - `handling.test.js` adds `myPatientsStrip` grouping: 2 patients → 2 rows, the newest per patient.
- [ ] **Step 2: Run** the frontend tests. Expected: FAIL.
- [ ] **Step 3: Implement.** Then run `npm run build`. Expected: clean.
- [ ] **Step 4: Run** all frontend tests and `make demo-check MODEL_API_KEY=`. Expected: PASS, ≥ 309; demo green (agent off; strip shows `Nothing handled yet.`, which no beat names).
- [ ] **Step 5: Commit**: "Count Guard ops: the chart and My patients show what the AI is handling, with Undo, Why and proposal cards".

---

### Task 9: The AI did this feed and the dock chip · 1 d

Requires UX v4 Inspector (R23).

**Files:**
- Create: `frontend/src/care/AiFeed.jsx`
- Modify: `AiDashboard.jsx` (render `<AiFeed>` directly below the model cards), `DemoDock.jsx`

**Interfaces:**
- `<AiFeed ids nowMs ward />` loads `call(\`/journey/ops/feed?ids=${ids}\`)` and checks it with `isFeed`. It renders `<section aria-label="AI did this"><h3>AI did this</h3>`. Each row is `{patient} · {text} · {when}` with **Why** (`openInspector`) and **Undo** while open. Undo goes through `ward.act(row.episode_id, …)`, then reloads. The empty state is `Nothing handled yet.`
- `DemoDock`: when `canSeeAi(role)`, `GET /journey/ops` sets `paused`. It shows `<span className="pill">{aiChip(paused)}</span>` and a button `{pauseLabel(paused)}`. The button posts `/journey/ops/pause` or `/resume` with `{by: \`Demo dock (${ROLE_NAME[role]})\`}`. It renders nothing for the patient.

- [ ] **Step 1: Write the failing tests.** The proxy test now sees `/journey/ops` in `AiFeed.jsx` and `DemoDock.jsx`, and passes because of Task 7. Add `dock.test.js`: the patient gets `canSeeAi === false`, so no chip.
- [ ] **Step 2: Implement.** Run `npm run build`.
- [ ] **Step 3: Run** all frontend tests and `make demo-check MODEL_API_KEY=`. Expected: PASS, ≥ 310; demo green. The dock gains `AI: running` text, and no beat's `absent` regex matches it.
- [ ] **Step 4: Commit**: "Count Guard ops: AI did this on the AI page, and a running or paused chip with a pause switch in the dock".

---

### Task 10: Turn the agent on, with beats, steps and the video script · 1 d

**Files:**
- Modify: `backend/app/config.py` (`CG_OPS_AGENT` default `"1"`), `backend/tests/test_ops_core.py` (`test_settings_default_on`, replacing `test_settings_default_off`)
- Modify: `frontend/scripts/demo/beats.mjs`, `steps.mjs`, `beats.test.mjs`, `docs/demo/count-guard-v2-video-script.md`

**Beat changes** (no new beat; seconds unchanged; 32 beats, 58/58/58 s, 200 s):

| Beat | Why it changes | `clicks` | `expect` / `before` | `say` |
|---|---|---|---|---|
| `kumar-admit` | Admit moves Kumar to `admitting`, so the AI acks in the same write | unchanged | expect `["Being admitted", "Acknowledged Dr. A. Rao's orders", "Nurse completes the admission."]` | "Dr. Rao signs the orders and admits him; the AI acknowledges the orders, and the screen says which nurse step comes next." |
| `kumar-admission` | The nurse's Acknowledge click is now the AI's action | drop `'Button "Acknowledge"'` | before `["Acknowledged Dr. A. Rao's orders"]`; expect `["On the ward", "Acknowledged Dr. A. Rao's orders"]` | "Nurse Meena finds the orders already acknowledged by the AI, with an undo, ticks the admission checks and completes the admission." |
| `kumar-ask` | The AI routes the question (patient lens) | unchanged | expect adds `"Your question went to Dr. A. Rao"` | "At home Mr. Kumar asks Dr. Rao about his wound and sends a day 3 photo; the page says where the question went and who is waiting." |
| `iyer-orders` | Iyer is on the ward, so signing triggers the AI ack | unchanged | expect `["Draft from dictation", "Acknowledged Dr. A. Rao's orders"]` | "Dr. Rao sees the flagged reading in her queue, dictates saline orders, and signs them; the AI acknowledges them at once." |
| `iyer-setup` | The nurse's Acknowledge click is now the AI's action | drop `'Button "Acknowledge"'` | unchanged | "The nurse films the saline set-up, and the check matches the list before she begins." |

Beats `kumar-back` (a "Back to ward" proposal appears, and the nurse's own click drops it) and `kumar-review` (a draft card appears, and the voice answer drops it) keep their clicks and strings. The card buttons are Approve, Edit, Reject and Why, so no step locator collides.

- [ ] **Step 1: Write the failing demo tests** (`beats.test.mjs`):
  - Remove the `NEXT_ADMIT` exception.
  - Assert `by["kumar-admit"].expect.includes("Acknowledged Dr. A. Rao's orders")`.
  - Assert `!by["kumar-admission"].clicks.includes('Button "Acknowledge"')` and the same for `iyer-setup`.
  - Assert `by["kumar-ask"].expect.includes("Your question went to Dr. A. Rao")`.
  - Keep `BEATS.length === 32` and `roleSeconds` 58/58/58.
- [ ] **Step 2: Run** `cd frontend && node --test scripts/demo/*.test.mjs`. Expected: FAIL.
- [ ] **Step 3: Implement** the beats. In `steps.mjs`, delete `H.click("Acknowledge")` from `kumar-admission` (:62) and `iyer-setup` (:174). In the document, update the blocks at lines 98, 103–107, 215, 220–224 and the `kumar-ask` block (Clicks, On screen, narration). Run `grep -n acknowledg docs/demo/count-guard-v2-video-script.md` and fix any summary line that still says the nurse acknowledges. Flip the `CG_OPS_AGENT` default.
- [ ] **Step 4: Run** every suite and `make demo-check MODEL_API_KEY=`. Expected: "DEMO CHECK PASSED: 32 beats; filmed doctor 58 s, nurse 58 s, patient 58 s, total 200 s". If a beat fails, debug with `CG_DEMO_UNTIL=<id>`.
- [ ] **Step 5: Commit**: "Count Guard ops: the agent is on; the demo shows the AI acknowledging orders and routing the question inside the same beats".

---

### Task 11: Replay evaluation · 1 d

**Files:**
- Create: `eval/replay_ops.py`, `backend/tests/test_replay_ops.py`

**Interfaces:**
- `metrics(events) -> dict[str, dict]`, per kind:
  - `{"proposed", "agreed", "precision", "l2", "undone", "undo_rate"}`.
  - `agreed` = approved (`work.done.approved_by`) + dropped with code `done_by_person` (R14).
  - `precision = agreed / proposed`, or None when 0. `undo_rate = undone / l2`, or None.
- `replay(events, settings) -> list[tuple[str, str]]`:
  1. Drop `work.*` and `ops.*` events, every event in a `wrote`, and every `by == AI_BY` event.
  2. Re-append the rest in order into a temporary `MorningStore`.
  3. Call `run.run` after each append, at that event's `ts_ms`.
  4. Return `(kind, rule)` per `work.opened`.
- `eligible(days: list[dict[str, dict]]) -> dict[str, bool]`: True only with at least 3 days, every day `precision >= 0.9` (or None for L2 kinds), and `undo_rate <= 0.05`.
- CLI: `.venv/bin/python eval/replay_ops.py --db <morning.db> [--db …]`. Each db is a recorded day: `cd frontend && node scripts/demo/run.mjs --keep-data` keeps one under the printed temp dir. The CLI prints one table row per kind plus `eligible: yes/no`, and states whether the replay reproduces the recorded work items (`same: N/M`). It exits 0.

- [ ] **Step 1: Write the failing tests**:
  - `test_metrics_counts_done_by_person_as_agreed`: 2 proposed, 1 approved, 1 `done_by_person` → precision 1.0.
  - `test_undo_rate`: 10 L2, 1 undone → 0.1.
  - `test_eligible_needs_three_days_and_thresholds`: 2 good days → False. 3 good days → True. One day with `undo_rate` 0.06 → False.
  - `test_replay_reproduces_agent_on_a_recorded_flow`: run the Task 4 admit flow with `ops_agent=True`, export `store.events`, replay → the same `(kind, rule)` list.
  - `test_cli_prints_table`: subprocess on a tmp db → exit 0, and the output holds `eligible:`.
- [ ] **Step 2: Run** `.venv/bin/pytest backend/tests/test_replay_ops.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** (import `app.*` via `sys.path` as `eval/run_eval.py` does).
- [ ] **Step 4: Run** every suite and `make demo-check MODEL_API_KEY=`. Expected: backend ≥ 544, frontend ≥ 310, demo green. Run `wc -l backend/app/ops/*.py backend/app/journey/*.py frontend/src/care/*.js* eval/replay_ops.py`: every file is under 500 lines.
- [ ] **Step 5: Commit**: "Count Guard ops: replay recorded demo days to measure proposal precision and undo rate before any level goes up".

---

## Estimate

| Task | What | Days |
|---|---|---|
| 1 | Policy, work items, kill switch | 1 |
| 2 | Watcher rules | 1 |
| 3 | Planner who/what, templates | 1 |
| 4 | Gate, run loop, write hook | 1.5 |
| 5 | Undo, approve, reject, pause, feed routes | 1.5 |
| 6 | Reword with fallback | 0.5 |
| 7 | Frontend helpers, proxy | 0.5 |
| 8 | Chart strip, proposals, My patients, patient lens | 1.5 |
| 9 | AI did this feed, dock chip | 1 |
| 10 | Agent on, beats and script | 1 |
| 11 | Replay evaluation | 1 |
| | **Total** | **11.5** |

The spec says 11 d. The extra 0.5 d is the write-hook sweep across five route files (R5), which the spec's two hook points did not cover. Order: 1 → 2 → 3 → 4 → 5 → 6; 7 → 8 → 9 (8 and 9 need UX v4); 10 needs 4, 5 and 8; 11 needs 4.

## Self-review against the spec

| Spec item | Task |
|---|---|
| §3 ladder in `ops/policy.py`, kill switch to L0, `ops.policy_changed` | 1 (R11, R12) |
| §4.1 work-item format, five `work.*` events, lease | 1 (C2) |
| §4.2 six watcher rules, once per input, hook after writes and on `/tick` | 2, 4 (R5, R8) |
| §4.3 planner rules, template first, reword then checked and verifier, offline template | 3, 6 (R19) |
| §4.4 gate L3/L2/L1/Never writes; attribution fields | 4 (R10) |
| §4.5 undo (409 after the window), approve with `check_move` re-check, reject, pause/resume, validation, Vite allow-list | 5, 7 (R7, R9, R21) |
| §5 strip under the next-action card, proposal card, AI did this feed with Why/Undo, dock chip, patient lens | 8, 9 (R22, R23) |
| §6 the morning | 09:02 ack and assign: 4, 10. 09:11 nudge: 4 (R18). 09:12 monitor file: 4 (R4). 09:16 theatre proposal: not possible (R15). 09:20 count alert, no clear: 4 (Never). Day 3 route and draft: 4, 10 |
| §7 demo green, 32 beats, 58/58/58; tests for Never in API, undo after window, approve no longer allowed | 10; 5 |
| §8 replay harness, two numbers, threshold | 11 |
| Anti-goals: no advice (regex tests per task), no invisible AI action (`work.done` + timeline), fatigue ≤ 3 | 3, 4 (R13) |

Names stay consistent: `settle`, `run`, `apply`, `undo`, `approve`, `reject`, `ops_view`, `assignees`, `routes`, `by_event`, `closing_payload`, `handlingRows`, `proposalsFor`, `agentMoment` and `routedLine` are each defined once (Interfaces) and used with the same spelling.

**Left out on purpose:**
- the time-lapse beat (§9);
- option D's extra agents (§9);
- a `draft_discharge` watcher rule (the spec gives a level but no rule);
- nurse queue filtering by assignee;
- a UI or route to change levels (`set_level` exists for config and audit only);
- building the Inspector (UX v4 plan).
