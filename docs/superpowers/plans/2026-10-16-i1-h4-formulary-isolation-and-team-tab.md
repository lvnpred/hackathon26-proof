# Clinic Formulary, Part 4: Isolation and the Team Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that Clinic A's learned drugs never reach Clinic B (matching, hints, list, removal), then give clinic admins the "Clinic medicines" tab on the Team screen to see and remove names.

**Architecture:** One isolation test file on the seeded two-clinic world, with admin clients created inside the tests. The tab is added to `frontend/team.js` (built in JS, shown only when `/api/v1/auth/me` says `admin`), tested statically (the file's method) and in node against a small fake DOM.

**Tech Stack:** Python 3 / FastAPI / sqlite3 (stdlib), vanilla JS, pytest. No new dependency.

**Spec:** `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md` section 2d ("Clinic formulary") and table row "Clinic formulary"; contracts in `docs/superpowers/plans/2026-10-16-i1-00-index-and-contracts.md` (facts 1, 2, 5, 6; sections 4.1, 4.2, 4.3).

**Assumptions about earlier plans** (re-find every anchor with `grep -n`; line numbers below are from the repository as it stood before I1-a..I1-g)**:**
- I1-h1 to I1-h3 are applied. Used exactly: `GET /api/v1/formulary -> {"items": [...]}` (items have `id, name, confirm_count, last_seen_at`), `DELETE /api/v1/formulary/{entry_id} -> {"removed": id, "name": name}` with 403/404/422 as in I1-h3; rows carry `source`; `use_clinic_layer` is on `/api/format` and `/api/transcribe`; the isolation sweep already skips and classifies the admin-only route (I1-h3 Step 8).
- I1-e: `frontend/rxstate.js` maps `verified` + `source: "clinic"` to the state `known` with the label "Known to your clinic" (contract 4.5). Check with `grep -n "Known to your clinic" frontend/rxstate.js`; this plan changes no row UI. I1-f restyles Team and leaves a named place for this tab; if it has landed, put the tab strip and panel there (`grep -n "Clinic medicines" frontend/team.js`) and do not restyle.

**Produces:** `tests/test_isolation_formulary.py` (3 tests); the tab in `frontend/team.js`, `team.css`, `index.html` (`?v=2`); 4 tests in `tests/test_frontend_team.py` and `tests/js/team_medicines.js`.

## Global Constraints

- `core/` stays pure (`tests/test_core_purity.py`): `core/formulary.py` imports only the standard library and `core.candidates`/`core.determinism` (lazily). Per-clinic data comes in as data.
- Changes to `core/determinism.py`: at most 4 net lines (this plan: +1). No source file over 500 lines (`db/__init__.py` is 487 lines, so the new SQL lives in `db/formulary.py`).
- Existing endpoints keep their status codes and JSON shapes; rows gain only `source` (and `lookalike` for a clinic name flagged as a look-alike). `preserve_untouched_rx_status` also restores `source` (`core/correction.py:273`).
- A clinic name is verified for its NAME only: no strength options, dose check `cannot-check`. Another clinic never sees a name: every query runs on the scoped clinic database (`db/__init__.py:35-44`).
- Tests offline: stub LLM (`STUB_LLM_JSON`), fake PDF renderer, no network. Test command `.venv/bin/python -m pytest tests/ -q`. No commits: every "commit" step is "leave uncommitted".

## Review Focus

- Clinic A learns a drug and Clinic B still sees unknown-medicine, an empty list and no hint for it; B's admin cannot remove A's name. Pinned in Task 1.
- A plain doctor never sees the tab or the Remove buttons; a failed removal keeps the red message and reloads the row. Pinned in Task 2 (node fake-DOM test).
- Names from the server are only ever set with `textContent`. Pinned in Task 2.

## File Structure

| File | Change |
|---|---|
| `tests/test_isolation_formulary.py` | NEW |
| `frontend/team.js`, `frontend/team.css`, `frontend/index.html` | the tab, scoped CSS, cache-busting |
| `tests/test_frontend_team.py`, `tests/js/team_medicines.js` | 4 tests |

Adds 7 tests (3 + 4). Baseline: the suite as it stands after I1-h3; expect that count + 7. After this part the five plans have added 22 tests in all.

---

### Task 1: Isolation: Clinic A learns, Clinic B does not

**Files:** Create `tests/test_isolation_formulary.py`.

- [ ] **Step 1: Write the isolation tests** (seeded two-clinic world from `tests/isolation_fixtures.py`; the admin clients are created in the test, because the seeded doctors are plain doctors and promoting them would drop them from the letterhead's doctor lists, `db/templates.py:96`).

```python
"""Clinic A learns a drug; Clinic B never sees it (plan I1-h). Offline; the seeded two-clinic world."""
import json

from fastapi.testclient import TestClient

from doctor_dictation import accounts
from doctor_dictation.api import stt as api_stt
from doctor_dictation.config import override_settings
from doctor_dictation.core import determinism as D
from isolation_fixtures import A, B, H, fingerprint, login, save_body, sql, world  # noqa: F401

ROW = {"form": "Tab.", "name": "Zorbexin", "strength": "10 mg", "dose": "1-0-0", "timing": "", "duration": "5 days",
       "instructions": "", "status": "unknown-medicine"}
ASK = {"transcript": "tablet Zorbexin 10 mg once daily for 5 days"}


def admin(world, slug, name):
    uid, _ = accounts.create_user(slug, name, role="admin", password="a-long-password-1")
    sql(slug, "UPDATE users SET must_change_password = 0 WHERE id = ?", uid)
    client = TestClient(world.app, follow_redirects=False)
    assert login(client, name, "a-long-password-1").status_code == 200
    return client


def learn(client, patient):
    body = save_body(patient, medicine="Zorbexin")
    body["structured"]["rx"][0]["status"] = "unknown-medicine"
    body["confirmed_rows"] = [0]
    r = client.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text


def test_clinic_a_learns_a_drug_and_clinic_b_still_sees_it_as_unknown(world, monkeypatch):
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps({"rx": [ROW]}))
    D._FORMAT_CACHE.clear()
    ask = lambda client: client.post("/api/format", json=ASK, headers=H).json()["structured"]["rx"][0]   # noqa: E731
    assert ask(world.rao)["status"] == ask(world.iyer)["status"] == "unknown-medicine"
    learn(world.rao, "Asha Verma")
    learn(world.mehta, "Ravi Kulkarni")                                  # a second doctor of the same clinic counts too
    assert (ask(world.rao)["status"], ask(world.rao)["source"]) == ("verified", "clinic")
    assert (ask(world.mehta)["status"], ask(world.iyer)["status"]) == ("verified", "unknown-medicine")
    assert [i["name"] for i in world.mehta.get("/api/v1/formulary").json()["items"]] == ["Zorbexin"]
    assert world.iyer.get("/api/v1/formulary").json() == {"items": []}
    assert sql(B, "SELECT COUNT(*) FROM clinic_formulary")[0][0] == 0 and sql(A, "SELECT COUNT(*) FROM clinic_formulary")[0][0] == 1


def test_the_speech_hints_carry_only_the_callers_own_clinic_names(world, monkeypatch):
    learn(world.rao, "Asha Verma")
    learn(world.rao, "Lakshmi Narayan")
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, stt_chain=("stub",),
                      stt_use_hints=True, stt_trim_silence=False)
    real, seen = api_stt.build_hints, {}
    for who in ("rao", "iyer"):
        monkeypatch.setattr(api_stt, "build_hints", lambda top, limit, who=who: seen.setdefault(who, real(top, limit)))
        r = getattr(world, who).post("/api/transcribe", files={"audio": ("a.webm", b"x" * 64, "audio/webm")}, headers=H)
        assert r.status_code == 200, r.text
    assert "Zorbexin" in seen["rao"] and "Zorbexin" not in seen["iyer"]


def test_only_a_clinic_admin_removes_and_only_in_their_own_clinic(world):
    learn(world.rao, "Asha Verma")
    learn(world.rao, "Lakshmi Narayan")
    adm_a, adm_b = admin(world, A, "adm.rao"), admin(world, B, "adm.iyer")
    (item,) = world.rao.get("/api/v1/formulary").json()["items"]
    before_a = fingerprint(A)
    assert world.rao.delete(f"/api/v1/formulary/{item['id']}", headers=H).status_code == 403    # a doctor, not an admin
    assert adm_b.delete(f"/api/v1/formulary/{item['id']}", headers=H).status_code == 404        # the other clinic's admin
    assert fingerprint(A) == before_a
    assert adm_a.delete(f"/api/v1/formulary/{item['id']}", headers=H).status_code == 200
    assert world.rao.get("/api/v1/formulary").json() == {"items": []}
```

- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_isolation_formulary.py -q`. Expected: `3 passed` (the feature exists since I1-h3). To see them guard something, temporarily delete `dependencies=[Depends(use_clinic_layer)]` from `/api/format` in `api/format.py`: the first test fails; restore it.
- [ ] **Step 3: Run.** Run: `.venv/bin/python -m pytest tests/ -q`. Expected: baseline + 3 passed, no failure.
- [ ] **Step 4: Leave uncommitted.**

---

---

### Task 2: The "Clinic medicines" tab on the Team screen

**Files:** Modify `frontend/team.js`, `frontend/team.css`, `frontend/index.html`, `tests/test_frontend_team.py`; Create `tests/js/team_medicines.js`.

`team.js` builds its dialog in JS (`build()` at `:26`), reports errors through `send()` into `#teamError` (`:107-123`), and shows the Team button only when `GET /api/v1/users` answers 200 (`:194-200`). The tab is for admins: `team.js` asks `/api/v1/auth/me` (which returns `role`, `api/auth.py:99-106`) and shows a tab strip only for `admin`; everyone else sees the screen exactly as before. Real `<button>`s, `aria-label`, `textContent` only (a test forbids `innerHTML`), the same confirm-then-`send()` pattern as the members' actions.

- [ ] **Step 1: Append the failing tests** to `tests/test_frontend_team.py` (static checks, the file's method) and add `import shutil`, `import subprocess`, `import pytest` at its top.

```diff
- import re
- from pathlib import Path
+ import re
+ import shutil
+ import subprocess
+ from pathlib import Path
+ 
+ import pytest
```
```python


def test_clinic_medicines_tab_is_for_admins_and_uses_the_formulary_routes():
    js = _read("team.js")
    assert '"/api/v1/formulary"' in js and 'method: "DELETE"' in js and '"/api/v1/auth/me"' in js
    assert 'me.role !== "admin"' in js and 'role: "tablist"' in js and "Clinic medicines" in js
    assert "hidden: true" in js.split("function buildTabs()")[1].split("tabs.append")[0]      # hidden until the role is known


def test_each_clinic_medicine_has_a_real_remove_button_and_failures_use_the_members_error_box():
    js = _read("team.js")
    assert 'make("button", { type: "button" }, "Remove")' in js and 'setAttribute("aria-label", "Remove "' in js
    assert "Number(m.id)" in js and "m.id + " not in js and js.count("window.confirm(") >= 3
    remove = js.split("async function removeMed")[1].split("\n  }")[0]
    assert "send(MEDS" in remove and "showErr(msg)" in remove          # send() fills #teamError exactly as for members
    assert "innerHTML" not in js and 'class: "team-row-actions"' in js.split("function renderMeds")[1]


def test_the_tab_behaves_in_a_fake_dom_for_admins_and_doctors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    out = subprocess.run([node, str(Path(__file__).parent / "js" / "team_medicines.js"), str(FRONT / "team.js")],
                         capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.strip().endswith("OK"), out.stdout + out.stderr


def test_the_team_assets_are_cache_busted_and_the_script_parses():
    html = _read("index.html")
    assert "team.js?v=2" in html and "team.css?v=2" in html
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    assert subprocess.run([node, "--check", str(FRONT / "team.js")], capture_output=True).returncode == 0
```

The fourth test runs `team.js` in node against a small fake DOM and fake server (no jsdom needed): create `tests/js/team_medicines.js`.

```javascript
// Runs frontend/team.js against a tiny fake DOM and fake server: node tests/js/team_medicines.js frontend/team.js
const assert = require("assert");
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const tick = () => new Promise((r) => setTimeout(r, 5));

class Node {
  constructor(tag) { Object.assign(this, { tag, children: [], attrs: {}, on: {}, hidden: false, textContent: "", parentNode: null }); }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "id") this.ids[v] = this; }
  append(...kids) { kids.forEach((k) => { k.parentNode = this; this.children.push(k); }); }
  replaceChildren(...kids) { this.children = []; this.append(...kids); }
  addEventListener(type, fn) { (this.on[type] = this.on[type] || []).push(fn); }
  click() { (this.on.click || []).forEach((fn) => fn()); }
  querySelectorAll() { return []; }
  showModal() {} close() {} focus() {} reset() {}
}

async function open(role, deleteStatus) {
  const ids = {}, calls = [];
  Node.prototype.ids = ids;
  let boot;
  global.document = { createElement: (tag) => new Node(tag), getElementById: (id) => ids[id] || null, body: new Node("body"),
                      addEventListener: (type, fn) => { boot = fn; } };
  ids.teamOpenBtn = new Node("button");
  global.window = { confirm: () => true, addEventListener() {} };
  global.navigator = {};
  global.fetch = async (url, opts = {}) => {
    calls.push((opts.method || "GET") + " " + url);
    const reply = (status, body) => ({ ok: status < 300, status, json: async () => body });
    if (url === "/api/v1/auth/me") return reply(200, { role });
    if (url === "/api/v1/users") return reply(200, { users: [], me: 1 });
    if (opts.method === "DELETE") return reply(deleteStatus, deleteStatus < 300 ? {} : { error: "You are not allowed to do that" });
    return reply(200, { items: [{ id: 7, name: "Zorbexin", confirm_count: 2, last_seen_at: "2026-10-02T00:00:00Z" }] });
  };
  (0, eval)(source);
  await boot();
  await tick();
  return { ids, calls };
}

(async () => {
  let { ids, calls } = await open("doctor", 200);                       // a plain doctor never gets the tab
  assert.strictEqual(ids.teamTabPeople.parentNode.hidden, true);
  assert.ok(!calls.some((c) => c.includes("formulary")));

  ({ ids, calls } = await open("admin", 403));                          // an admin does; Remove fails: message stays, list reloads
  assert.strictEqual(ids.teamTabPeople.parentNode.hidden, false);
  ids.teamTabMeds.click();
  await tick();
  const remove = ids.teamMedRows.children[0].children[3].children[0];
  assert.strictEqual(remove.textContent, "Remove");
  assert.strictEqual(remove.attrs["aria-label"], "Remove Zorbexin from your clinic's medicines");
  assert.strictEqual(ids.teamMeds.hidden, false);
  assert.strictEqual(ids.teamPeople.hidden, true);
  remove.click();
  await tick();
  assert.deepStrictEqual(calls.slice(-3), ["GET /api/v1/formulary", "DELETE /api/v1/formulary/7", "GET /api/v1/formulary"]);
  assert.strictEqual(ids.teamError.textContent, "You are not allowed to do that");
  assert.strictEqual(ids.teamError.hidden, false);

  ({ ids, calls } = await open("admin", 200));                          // success: the error box stays empty
  ids.teamTabMeds.click();
  await tick();
  ids.teamMedRows.children[0].children[3].children[0].click();
  await tick();
  assert.strictEqual(ids.teamError.hidden, true);
  console.log("OK");
})().catch((e) => { console.error(e); process.exit(1); });
```

- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_frontend_team.py -q`. Expected: 4 FAIL (the strings are not in `team.js`; the node script throws `Cannot read properties of undefined (reading 'parentNode')`), 12 pass.
- [ ] **Step 3: Edit `team.js`.** (a) the route constant; (b) `build()` wraps the members part in a tab panel and appends the tab strip and the medicines panel; (c) the functions, above `function showErr`; (d) the call at the end of the `DOMContentLoaded` handler.

```diff
-   const API = "/api/v1/users";
+   const API = "/api/v1/users";
+   const MEDS = "/api/v1/formulary";
```
```javascript
    const people = make("div", { id: "teamPeople", class: "team-tab-body", role: "tabpanel", "aria-labelledby": "teamTabPeople" });
    people.append(secret, tableBox, form);
    const box = make("div", { class: "team-body" });
    box.append(make("div", { id: "teamError", class: "team-error", role: "alert", hidden: true }), buildTabs(), people, buildMeds());
    d.append(head, box);
    return d;
```
```javascript
  // "Clinic medicines": the names this clinic has confirmed on two prescriptions. Shown to clinic admins only.
  function buildTabs() {
    const tabs = make("div", { class: "team-tabs", role: "tablist", "aria-label": "Team sections", hidden: true });
    tabs.append(make("button", { id: "teamTabPeople", type: "button", role: "tab", "aria-selected": "true", "aria-controls": "teamPeople" }, "People"),
      make("button", { id: "teamTabMeds", type: "button", role: "tab", "aria-selected": "false", "aria-controls": "teamMeds" }, "Clinic medicines"));
    return tabs;
  }
  function buildMeds() {
    const hrow = make("tr");
    ["Medicine", "Confirmed on", "Last seen", "Actions"].forEach((h) => hrow.append(make("th", { scope: "col" }, h)));
    const thead = make("thead");
    thead.append(hrow);
    const table = make("table", { class: "team-table" });
    table.append(thead, make("tbody", { id: "teamMedRows" }));
    const tableBox = make("div", { class: "team-table-box" });
    tableBox.append(table);
    const panel = make("div", { id: "teamMeds", class: "team-tab-body", role: "tabpanel", "aria-labelledby": "teamTabMeds", hidden: true });
    panel.append(make("p", { class: "team-hint" }, "Medicines your doctors confirmed on two saved prescriptions. They are recognised for dictation " +
      "and shown as known to your clinic. Remove a wrong one: it is learned again only after two new prescriptions confirm it."),
      make("p", { id: "teamMedEmpty", class: "team-hint" }, "Nothing learned yet."), tableBox);
    return panel;
  }
  function selectTab(meds) {
    el("teamPeople").hidden = meds;
    el("teamMeds").hidden = !meds;
    el("teamTabPeople").setAttribute("aria-selected", String(!meds));
    el("teamTabMeds").setAttribute("aria-selected", String(meds));
    showErr("");
    if (meds) refreshMeds();
  }
  function renderMeds(items) {
    const rows = el("teamMedRows");
    rows.replaceChildren();
    el("teamMedEmpty").hidden = items.length > 0;
    items.forEach((m) => {
      const tr = make("tr");
      tr.append(make("td", {}, m.name), make("td", {}, m.confirm_count + " prescriptions"), make("td", {}, when(m.last_seen_at)));
      const cell = make("td", { class: "team-row-actions" });
      const remove = make("button", { type: "button" }, "Remove");
      remove.setAttribute("aria-label", "Remove " + m.name + " from your clinic's medicines");
      remove.addEventListener("click", () => removeMed(m));
      cell.append(remove);
      tr.append(cell);
      rows.append(tr);
    });
  }
  async function refreshMeds() {
    const b = await send(MEDS);
    if (b) renderMeds(b.items || []);
  }
  async function removeMed(m) {
    if (!window.confirm("Remove " + m.name + " from your clinic's medicines? Doctors will be asked about it again " +
      "until two new prescriptions confirm it.")) return;
    const b = await send(MEDS + "/" + Number(m.id), { method: "DELETE" });
    const msg = b ? "" : el("teamError").textContent;     // the row on screen may be stale: reload it, keep the error visible
    await refreshMeds();
    showErr(msg);
    if (b) el("teamTitle").focus();
  }
  async function showMedsTab() {
    try {
      const me = await (await fetch("/api/v1/auth/me")).json();
      if (me.role !== "admin") return;
    } catch (e) { return; }
    el("teamTabPeople").parentNode.hidden = false;
    el("teamTabPeople").addEventListener("click", () => selectTab(false));
    el("teamTabMeds").addEventListener("click", () => selectTab(true));
  }

  function showErr(m)
```
```diff
-     el("teamAddForm").addEventListener("submit", addUser);
+     el("teamAddForm").addEventListener("submit", addUser);
+     showMedsTab();
```

- [ ] **Step 4: CSS and cache-busting.** Rules are scoped under `.team-panel` (a test enforces it); `index.html` bumps both `?v=` (`:9`, `:242`).

```diff
- .team-panel button:focus-visible
+ .team-panel .team-tabs { display:flex; gap:6px; border-bottom:1px solid var(--soft); }
+ .team-panel .team-tabs button { border-radius:8px 8px 0 0; }
+ .team-panel .team-tabs button[aria-selected="true"] { border-bottom:3px solid var(--accent); font-weight:600; }
+ .team-panel .team-tab-body { display:flex; flex-direction:column; gap:14px; }
+ .team-panel .team-hint { margin:0; font-size:14px; color:var(--muted); }
+ .team-panel button:focus-visible
```
```diff
- href="team.css?v=1"
+ href="team.css?v=2"
```
```diff
- src="team.js?v=1"
+ src="team.js?v=2"
```

- [ ] **Step 5: Run.** Run: `.venv/bin/python -m pytest tests/test_frontend_team.py -q`. Expected: `16 passed`. Then `node --check frontend/team.js` prints nothing.
- [ ] **Step 6: Manual check (once).** Sign in as an admin (create one with `.venv/bin/python -m doctor_dictation.admin create-user --clinic SLUG --username NAME --role admin`, `admin.py:198`), open Team: a "Clinic medicines" tab appears; with a doctor account it does not. Remove a name: the row disappears, the next dictation of it shows unknown again. A server error (stop the server, press Remove) shows the red message and keeps the row.
- [ ] **Step 7: Leave uncommitted.**

---

---

### Task 3: Whole-suite check and hand-over

- [ ] **Step 1:** `.venv/bin/python -m pytest tests/ -q`. Expected: the baseline from before I1-h1, plus 22 passed, same skip count. `wc -l doctor_dictation/core/determinism.py doctor_dictation/api/persistence.py doctor_dictation/db/__init__.py` stays below 500 each (483, 421, 487).
- [ ] **Step 2:** Confirm the safeguards with one throw-away session: single mode with `DB_PATH` set to a TEMP file (never the real dev database), stub LLM, save the same unknown drug on two prescriptions, watch `GET /api/v1/formulary`, dictate it again (verified, "Known to your clinic" once I1-e is in), remove it, dictate again (unknown).
- [ ] **Step 3:** Leave uncommitted. Changed files: the new files and edits listed in the File Structure table.

## Self-review

Isolation (Task 1), tab (Task 2), whole-suite check (Task 3). Not done, on purpose: voice or fuzzy matching of learned names, strengths or dose ranges for learned names, per-doctor lists, undo for a removal, editing a name, a "pending names" view, the lexicon import (I1-g1/I1-g2).
