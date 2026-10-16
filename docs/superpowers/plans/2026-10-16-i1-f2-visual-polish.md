# I1-f2: Visual Polish (Tokens, Type, Buttons, Orb, Login, Team)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the app the look of the approved design canvas (colour tokens, type pairing, 10px buttons, 14px cards, the segmented "Today" switch, an SVG brand mark, the dictation orb with a recording pulse, wave bars and a busy spinner ring, a calmer sign-in page and Team panel) with no behaviour change and **no change to what prints**.

**Architecture:** Tokens change in place in `styles.css`'s `:root`. Everything else is a new `frontend/polish.css` that only contains `@media screen` rules plus one `@media print` block pinning the three values the tokens could move on paper. `login.css` and `team.css` are rewritten in the same style. Markup changes are three small swaps in `index.html` and two in `login.html`.

**Tech Stack:** CSS, inline SVG, pytest, Playwright MCP tools.

**Spec:** `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md` "Iteration 1" section 6; canvas boards `Main.dc.html`, `States.dc.html`, `Login.dc.html`, `Team.dc.html` (visual reference only).

**Assumptions about earlier plans:** I1-e to I1-f are applied (`index.html` links `steps.css?v=1`; `styles.css` has no three-step block). The "Clinic medicines" tab of the Team panel belongs to plan I1-h; this plan leaves only its CSS and a comment naming it.

## Global Constraints

- No `git commit` or `git push`. Baseline first: `.venv/bin/python -m pytest tests/ -q`, expect count + 6.
- **Print is unchanged.** The print rules of `styles.css` (from `/* --- print: only the sheet` to `/* Authorship (M3)`) are not edited; a test pins their SHA-256. The PDF the doctor prints comes from the server (`pdf/sheet.py`) and is not touched; only the browser-print fallback (`app.js:1206`) uses these styles.
- The login page must not depend on files behind the session (`api/session.py` `PUBLIC_PATHS` allows only `/login.css` and `/login.js`): inline SVG, no new asset, no third-party request.
- Every animation is inside `@media screen` and switched off by `prefers-reduced-motion: reduce`.
- Existing ids, classes that `app.js`, `login.js`, `team.js`, `letterhead.js` use, and the existing tests are unchanged. Browser checks use `DB_PATH` on a temp file.

## Review Focus

- The browser-print fallback must look exactly as before even though `--ink`, `--muted` and the font token changed: the print pin and `test_the_print_rules_are_byte_for_byte...`.
- Reduced motion must still show recording and busy without animation (bars at a fixed height, no spinner ring): `test_every_animation_is_screen_only...`.
- The sign-in page must keep working when only public files load: `test_no_page_loads_anything_from_a_third_party...`, and `login.html` keeps every id `login.js` reads.
- Team-panel rules must stay scoped (`tests/test_frontend_team.py:62` requires every selector to start with `.team-panel`); the reserved tab rules obey it.
- Keyboard focus must stay visible on every restyled button: focus rings are 3px (`rx.css`, `steps.css`, `login.css`, `team.css`).

## Decision: fonts

**Recommendation: keep system fonts, do not load Google Fonts.** The canvas links `fonts.googleapis.com`. For this app that is the wrong default: (1) every page load would tell a third party that this clinic's app is open and from which IP, in a medical product that already promises demo-only data; (2) a clinic on a poor or closed network would wait on a blocked request before the text swaps; (3) the sign-in page runs before the session exists and should make no third-party request at all. Instead the tokens `--font-ui` and `--font-serif` list "Public Sans" and "Source Serif 4" first, so a machine that has them installed uses them, and fall back to `Segoe UI`/`system-ui` and `Georgia`/`Iowan Old Style`. If the owner wants the exact faces everywhere, the follow-up is to self-host the two OFL-licensed families (woff2 files under `frontend/fonts/` plus `@font-face` with `font-display: swap`); it changes only the two tokens' source, and needs files this plan does not have. Serif is applied on screen only (sheet title, clinic name, section bars, medicine names); the fallback print path keeps `Segoe UI`, Arial.

### Task 1: Tests first

**Files:** Create `tests/test_frontend_polish.py`.

- [ ] **Step 1: Write the tests.** The constant `PRINT_BLOCK_SHA256` is the hash of the print block as it is in the repo before this plan; recompute it first with `python3 -c "import hashlib; s=open('frontend/styles.css',encoding='utf-8').read(); print(hashlib.sha256(s[s.index('/* --- print: only the sheet'):s.index('/* Authorship (M3)')].encode()).hexdigest())"` and expect `a3adba36f9bd592924443aa52a2a3b2e1abb6e00b3057c8a75d2c5ca7f79916b`; if it differs, someone changed the print rules: stop and tell the owner.

```python
"""Visual polish (I1-f2): static checks. How it looks is the manual checklist in the plan."""
import hashlib
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1] / "frontend"
PRINT_BLOCK_SHA256 = "a3adba36f9bd592924443aa52a2a3b2e1abb6e00b3057c8a75d2c5ca7f79916b"      # the print rules of styles.css as they were before this plan (from /* --- print: only the sheet to /* Authorship (M3)


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def _strip_blocks(css, opener):
    """css without the `opener { ... }` blocks (brace-matched)."""
    out, i = [], 0
    while True:
        j = css.find(opener, i)
        if j < 0:
            out.append(css[i:])
            return "".join(out)
        out.append(css[i:j])
        depth, k = 0, css.index("{", j)
        while True:
            depth += (css[k] == "{") - (css[k] == "}")
            k += 1
            if depth == 0:
                break
        i = k


def test_the_print_rules_are_byte_for_byte_what_they_were_and_polish_only_touches_the_screen():
    css = _read("styles.css")
    block = css[css.index("/* --- print: only the sheet"):css.index("/* Authorship (M3)")]
    assert hashlib.sha256(block.encode("utf-8")).hexdigest() == PRINT_BLOCK_SHA256
    polish = re.sub(r"/\*.*?\*/", "", _read("polish.css"), flags=re.S)
    rest = _strip_blocks(_strip_blocks(polish, "@media screen"), "@media print")
    assert rest.strip() == ""                      # every rule is inside the screen block or the print pin
    pin = polish[polish.index("@media print"):polish.index("@media screen")]
    assert "--ink:#1a1a1a" in pin and "--muted:#5f6b7a" in pin and '"Segoe UI", Arial' in pin


def test_no_page_loads_anything_from_a_third_party_and_the_fonts_are_tokens():
    for name in ("index.html", "login.html", "styles.css", "polish.css", "login.css", "team.css", "steps.css", "rx.css", "letterhead.css"):
        text = _read(name)
        assert "googleapis" not in text and "gstatic" not in text and "@import" not in text and not re.search(r'(?:href|src)="https?://', text), name
    css = _read("styles.css")
    assert '--font-ui:"Public Sans", "Segoe UI"' in css and '--font-serif:"Source Serif 4"' in css and "font-family: var(--font-ui)" in css
    assert "--font-serif" in _read("login.css") and "@font-face" not in css


def test_the_brand_mark_and_orb_are_inline_svg_and_the_recording_hooks_are_unchanged():
    html, login, app = _read("index.html"), _read("login.html"), _read("app.js")
    assert "✚" not in html and "🎤" not in html and "● REC" not in html and "⚕" not in login and "&#9877;" not in login
    assert html.count('<path d="M12 5v14M5 12h14"/>') == 1 and login.count('<path d="M12 5v14M5 12h14"/>') == 1
    assert 'id="wave" class="rec-dot" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><span class="rec-text">REC</span>' in html
    assert 'wave.classList.add("on")' in app and 'wave.classList.remove("on")' in app and 'class="mic-label"' in html


def test_every_animation_is_screen_only_and_switched_off_for_reduced_motion():
    css = re.sub(r"/\*.*?\*/", "", _read("polish.css"), flags=re.S)
    screen = css[css.index("@media screen"):]
    assert screen.count("animation:") >= 4 and "@media (prefers-reduced-motion: reduce) { .mic.recording, .mic.busy::after, .rec-dot i { animation:none; }" in screen
    assert "animation" not in _read("login.css") and "animation" not in _read("team.css") and "animation" not in _read("steps.css")


def test_login_and_team_keep_their_behaviour_and_leave_a_named_place_for_the_clinic_medicines_tab():
    login, team_css, team_js = _read("login.html"), _read("team.css"), _read("team.js")
    for token in ('id="loginForm"', 'id="changeForm"', 'id="msg" role="alert"', 'id="signoutLink"', 'autocomplete="current-password"', "Use a different account"):
        assert token in login, token
    assert ".team-panel .team-tabs" in team_css and "plan I1-h" in team_css and "I1-h" not in team_js and not re.search(r"team-tabs?\b", team_js)
    assert "Clinic medicines" not in login and "Clinic medicines" not in team_js


def test_new_controls_are_44px_high():
    polish, login, team = _read("polish.css"), _read("login.css"), _read("team.css")
    assert ".topbar-actions button, .panel-actions button, .save-row button, .lh-foot button, .retry, .lh-act, #lhCloseBtn { min-height:44px; }" in polish
    assert "min-height:44px" in login and "min-height:48px" in login and ".team-panel .team-tab { min-height:44px;" in team
```

- [ ] **Step 2: Run them.** `.venv/bin/python -m pytest tests/test_frontend_polish.py -q` -> expected `6 failed`.

### Task 2: Tokens, `polish.css`, markup

**Files:** Create `frontend/polish.css`; modify `frontend/styles.css` (`:root` at `:5-9`, `body` at `:11`), `frontend/index.html`, `frontend/login.html`.

- [ ] **Step 1: Write `frontend/polish.css`.**

```css
/* Visual polish from the design canvas, loaded after styles.css. Screen only: the print rules in styles.css are untouched and the
   first block below pins the few values that tokens or fonts could otherwise change on paper (browser-print fallback). */
@media print { :root { --ink:#1a1a1a; --muted:#5f6b7a; } body { font-family:"Segoe UI", Arial, sans-serif; } }
@media screen {
  button { border-radius:10px; }
  .topbar-actions button, .panel-actions button, .save-row button, .lh-foot button, .retry, .lh-act, #lhCloseBtn { min-height:44px; }
  .sidebar, .middle, #sheet { border-radius:var(--radius); }
  dialog.panel { border-radius:16px; }
  #sheet h2, .clinic-name, .sec-title, .rx-name { font-family:var(--font-serif); }
  .brand-mark { width:38px; height:38px; }
  .brand-clinic { font-size:16px; }
  .agent-chip { border-radius:999px; padding:4px 12px; }
  .pane-title { font-weight:600; letter-spacing:.08em; }
  .today-scope { background:#eef2f0; border-radius:10px; padding:3px; gap:3px; }
  .today-scope button { border:0; min-height:34px; border-radius:8px; color:var(--muted); font-weight:500; background:transparent; }
  .today-scope button[aria-pressed="true"] { background:#fff; color:var(--ink); font-weight:600; box-shadow:0 1px 2px rgba(0,0,0,.12); }
  .today-item { border-radius:10px; padding:10px; }
  .today-item:hover { background:#f1f6ff; }
  .today-item.active { background:#eaf1ff; border-color:#bcd0ff; }
  /* the dictation orb: idle, recording (pulse + wave bars), busy (spinner ring) */
  .mic { width:96px; height:96px; box-shadow:0 0 0 8px #e3ecff; position:relative; justify-content:center; }
  .mic .mic-icon { display:flex; }
  .mic .mic-label { font-size:12px; }
  .mic.recording { background:var(--bad); animation:rx-pulse 1.4s ease-out infinite; }
  .mic.busy { background:#6b7a74; box-shadow:0 0 0 8px #e6ebe8; }
  .mic.busy::after { content:""; position:absolute; inset:0; border-radius:50%; border:4px solid rgba(255,255,255,.35); border-top-color:#fff; animation:rx-spin 1.1s linear infinite; }
  .rec-dot.on { display:flex; align-items:center; gap:4px; height:32px; animation:none; }
  .rec-dot i { display:block; width:4px; height:6px; border-radius:2px; background:var(--bad); animation:rx-bar 1s ease-in-out infinite; }
  .rec-dot i:nth-child(2) { animation-delay:.12s; } .rec-dot i:nth-child(3) { animation-delay:.24s; } .rec-dot i:nth-child(4) { animation-delay:.36s; }
  .rec-dot i:nth-child(5) { animation-delay:.48s; } .rec-dot i:nth-child(6) { animation-delay:.6s; } .rec-dot i:nth-child(7) { animation-delay:.72s; }
  .rec-text { margin-left:6px; font-size:12px; font-weight:700; color:var(--bad); }
  @keyframes rx-pulse { 0% { box-shadow:0 0 0 0 rgba(168,38,29,.35); } 100% { box-shadow:0 0 0 20px rgba(168,38,29,0); } }
  @keyframes rx-spin { to { transform:rotate(360deg); } }
  @keyframes rx-bar { 0%, 100% { height:6px; } 50% { height:28px; } }
  @media (prefers-reduced-motion: reduce) { .mic.recording, .mic.busy::after, .rec-dot i { animation:none; } .rec-dot i { height:18px; } }
}
```

- [ ] **Step 2: Apply the token and markup edits.** From the repo root, paste as `python3 - <<'PY' ... PY`:

```python
# Run from the repo root (after plan I1-f). Every edit must match exactly once.
def edit(path, pairs):
    s = open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert s.count(old) == 1, (path, old[:70])
        s = s.replace(old, new)
    open(path, "w", encoding="utf-8").write(s)
MIC = '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3z"/><path d="M5 11a7 7 0 0014 0M12 18v3"/></svg>'
PLUS = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>'
edit("frontend/styles.css", [
 ('''  --ink:#1a1a1a; --muted:#5f6b7a; --line:#333; --soft:#d7dde5;
  --accent:#0b5fff; --warn:#9a6700; --bad:#b3261e; --ok:#1a7f37;
  --bg:#eef1f5; --card:#fff; --radius:12px;''', '''  --ink:#16211d; --muted:#566660; --line:#333; --soft:#d6ded9;
  --accent:#1456d9; --warn:#7d5200; --bad:#a8261d; --ok:#17703a;
  --bg:#eef2f0; --card:#fff; --radius:14px;
  --font-ui:"Public Sans", "Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif;
  --font-serif:"Source Serif 4", "Iowan Old Style", "Palatino Linotype", Georgia, serif;'''),
 ('body { font-family: "Segoe UI", Arial, sans-serif;', 'body { font-family: var(--font-ui);'),                      # :11 body
])
edit("frontend/index.html", [
 ('<link rel="stylesheet" href="steps.css?v=1" />\n', '<link rel="stylesheet" href="steps.css?v=1" />\n<link rel="stylesheet" href="polish.css?v=1" />\n'),
 ('<div class="brand-mark" aria-hidden="true">✚</div>', '<div class="brand-mark" aria-hidden="true">' + PLUS + '</div>'),
 ('<span class="mic-icon" aria-hidden="true">🎤</span>', '<span class="mic-icon" aria-hidden="true">' + MIC + '</span>'),
 ('<span id="wave" class="rec-dot" aria-hidden="true">● REC</span>', '<span id="wave" class="rec-dot" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><span class="rec-text">REC</span></span>'),
])
edit("frontend/login.html", [
 ('''  <div class="brand-mark" aria-hidden="true">&#9877;</div>
  <h1>Doctor Dictation</h1>
''', '''  <div class="brand"><div class="brand-mark" aria-hidden="true">''' + PLUS + '''</div><h1>Doctor Dictation</h1></div>
  <p class="tagline">Speak. Review. Print.</p>
'''),
 ('  <p id="msg" role="alert"></p>\n', '  <p id="msg" role="alert"></p>\n  <p class="foot">Forgot your password? Ask your clinic admin to reset it.</p>\n'),
])
```

- [ ] **Step 3: Run the tests.** `.venv/bin/python -m pytest tests/test_frontend_polish.py tests/test_frontend_steps.py tests/test_frontend_rxrow.py tests/test_frontend_auth.py tests/test_frontend_authorship.py tests/test_frontend_letterhead.py tests/test_frontend_doctorgrid.py tests/test_frontend_team.py -q` -> expected the polish file shows `3 passed, 3 failed` (the print/polish, brand/orb and animation tests pass; the third-party/fonts, login/team and 44px tests wait for Task 3) and every other file passes.

### Task 3: Sign-in page and Team panel

**Files:** Replace `frontend/login.css` and `frontend/team.css` (full contents below; the old files are in git).

- [ ] **Step 1: Write `frontend/login.css`.**

```css
/* Self-contained: styles.css is not a public path (api/session.py PUBLIC_PATHS), so the few values we need are copied here.
   System fonts only: the sign-in page makes no third-party request. */
:root { --ink:#16211d; --muted:#566660; --soft:#d6ded9; --accent:#1456d9; --bad:#a8261d; --bg:#eef2f0; --card:#fff;
  --font-ui:"Public Sans", "Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif;
  --font-serif:"Source Serif 4", "Iowan Old Style", "Palatino Linotype", Georgia, serif; }
* { box-sizing: border-box; }
body { font-family:var(--font-ui); font-size:14px; line-height:1.45; margin:0; color:var(--ink); background:linear-gradient(160deg,#e3ecff 0%,var(--bg) 55%);
  min-height:100vh; display:flex; align-items:center; justify-content:center; padding:16px; }
.card { width:100%; max-width:400px; background:var(--card); border:1px solid var(--soft); border-radius:18px;
  padding:32px 30px 28px; box-shadow:0 18px 40px rgba(20,35,29,.1); }
.brand { display:flex; align-items:center; gap:12px; margin-bottom:6px; }
.brand-mark { width:42px; height:42px; flex:0 0 42px; border-radius:12px; background:var(--accent); color:#fff; display:flex; align-items:center; justify-content:center; }
h1 { font-family:var(--font-serif); font-size:24px; margin:0; }
.tagline { margin:0 0 6px; color:var(--muted); }
h2 { font-size:15px; margin:14px 0 6px; color:var(--muted); font-weight:600; }
form { display:flex; flex-direction:column; gap:6px; }
form[hidden] { display:none; }
label { font-size:12px; font-weight:600; color:var(--muted); margin-top:10px; }
input { font:inherit; min-height:46px; padding:0 12px; border:1px solid #9aa8a1; border-radius:10px; width:100%; color:var(--ink); }
input:focus-visible, button:focus-visible { outline:3px solid #8fb2ff; outline-offset:2px; }
button { font:inherit; cursor:pointer; border-radius:10px; min-height:44px; padding:0 16px; margin-top:14px; border:1px solid #b5c0ba; background:#fff; }
button.primary { min-height:48px; margin-top:20px; background:var(--accent); border-color:var(--accent); color:#fff; font-weight:700; font-size:15px; }
.hint { font-size:12px; color:var(--muted); margin:0; }
#msg { min-height:1.2em; margin:14px 0 0; font-size:13px; color:var(--bad); }
.foot { margin:6px 0 0; font-size:12px; color:var(--muted); text-align:center; }
```

- [ ] **Step 2: Write `frontend/team.css`.** Same selectors as before plus the reserved tab rules; green "password ready" box as in the canvas, with the warning line still bold.

```css
/* Team panel (team.js). Reuses dialog.panel, .field and button.primary from styles.css; every rule is scoped here (tests enforce it). */
.team-panel [hidden] { display:none !important; }
dialog.team-panel { width:min(780px, 96vw); max-height:92vh; border-radius:16px; }
dialog.team-panel[open] { display:flex; flex-direction:column; }
.team-panel .team-head { display:flex; justify-content:space-between; align-items:center; padding:20px 24px 12px; }
.team-panel .team-head h2 { margin:0; font-size:20px; }
.team-panel .team-body { padding:8px 24px 20px; overflow-y:auto; display:flex; flex-direction:column; gap:14px; }
/* Reserved for plan I1-h: its "Clinic medicines" tab. I1-h adds <div class="team-tabs" role="tablist"> as the first child of .team-body
   and a second panel; the rules are here so that plan only adds team.js code. This plan adds no tab. */
.team-panel .team-tabs { display:flex; gap:4px; border-bottom:1px solid var(--soft); margin:0 -24px; padding:0 14px; }
.team-panel .team-tab { min-height:44px; padding:0 16px; border:0; border-bottom:3px solid transparent; border-radius:0; background:transparent; color:var(--muted); font-weight:500; }
.team-panel .team-tab[aria-selected="true"] { border-bottom-color:var(--accent); color:var(--ink); font-weight:700; }
.team-panel .team-error { background:#fdeceb; border:1px solid #efb0aa; color:var(--bad); border-radius:12px; padding:12px 16px; font-size:14px; }
.team-panel .team-secret { background:#e5f4ea; border:1px solid #a8d6b6; border-radius:12px; padding:14px 16px; display:flex; flex-direction:column; gap:8px; }
.team-panel .team-secret-for, .team-panel .team-secret-warn { margin:0; font-size:13px; }
.team-panel .team-secret-warn { font-weight:600; color:#355d44; }
.team-panel .team-secret-value { align-self:flex-start; font-size:17px; font-weight:700; letter-spacing:.04em; padding:6px 12px; background:#fff; border:1px solid #a8d6b6; border-radius:8px; user-select:all; }
.team-panel .team-secret-actions { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.team-panel .team-copy-status { font-size:13px; color:var(--muted); }
.team-panel .team-table-box { overflow-x:auto; }
.team-panel .team-table { width:100%; border-collapse:collapse; font-size:14px; }
.team-panel .team-table th { font-size:11px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
.team-panel .team-table th, .team-panel .team-table td { text-align:left; padding:12px 6px; border-bottom:1px solid var(--soft); vertical-align:middle; }
.team-panel .team-table tr.team-off td { color:var(--muted); }
.team-panel .team-row-actions button { margin:0 6px 4px 0; min-height:36px; border-radius:8px; font-weight:600; }
.team-panel form.team-add { padding:14px 0 0; border-top:1px solid var(--soft); display:flex; flex-direction:column; gap:8px; }
.team-panel form.team-add h3 { margin:0; font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }
.team-panel form.team-add button { align-self:flex-start; min-height:44px; }
.team-panel .field input { min-height:44px; border-radius:8px; border-color:#9aa8a1; }
.team-panel button:focus-visible, .team-panel input:focus-visible { outline:3px solid #8fb2ff; outline-offset:2px; }
```

- [ ] **Step 3: Run the whole suite.** `.venv/bin/python -m pytest tests/ -q` -> expected baseline + 6. Then `.venv/bin/python -m pytest tests/test_frontend_team.py::test_team_css_rules_are_scoped_to_the_team_panel -q` -> `1 passed`.

- [ ] **Step 4: Leave uncommitted.** `git status --short`: `M` on `frontend/styles.css`, `index.html`, `login.html`, `login.css`, `team.css`; `??` on `polish.css` and the new test file.

### Task 4: Browser check (Playwright MCP)

Screenshots (`browser_take_screenshot`) can hang in some headless setups; if so use computed styles as below and look at the page in a normal browser afterwards.

- [ ] **Step 1: Start** (background): `cd <repo> && DB_PATH="$(mktemp -d)/p.db" STT_ENGINE=stub LLM_PROVIDER=stub .venv/bin/python -m uvicorn doctor_dictation.main:app --port 8791`, `browser_navigate` to `http://localhost:8791/`.
- [ ] **Step 2: Look and feel.** `browser_evaluate`: `() => { const c = (s, p) => getComputedStyle(document.querySelector(s))[p]; return [c("body","fontFamily"), c("#recBtn","width"), c("#recBtn","borderRadius"), c("#sheet h2","fontFamily"), !!document.querySelector(".brand-mark svg"), !!document.querySelector("#recBtn .mic-icon svg")]; }` -> `["\"Public Sans\", \"Segoe UI\", ...","96px","50%","\"Source Serif 4\", ...",true,true]`.
- [ ] **Step 3: Recording and busy.** `() => { recBtn.classList.add("recording"); wave.classList.add("on"); return [getComputedStyle(recBtn).animationName, getComputedStyle(wave).display, getComputedStyle(document.querySelector("#wave i")).animationName]; }` -> `["rx-pulse","flex","rx-bar"]`; then `() => { recBtn.classList.replace("recording","busy"); wave.classList.remove("on"); return getComputedStyle(recBtn, "::after").animationName; }` -> `rx-spin`.
- [ ] **Step 4: Reduced motion.** `browser_emulate_media` `reducedMotion: "reduce"`, put the classes back (`recording`, wave `on`): `animationName` of `#recBtn` and of `#wave i` are `none` and the bar height is `18px`. Reset with `reducedMotion: null`.
- [ ] **Step 5: Print.** `browser_emulate_media` `media: "print"`: `() => { const b = getComputedStyle(document.body); return [b.fontFamily, b.color, getComputedStyle(document.getElementById("sheet")).borderRadius, getComputedStyle(document.querySelector(".topbar")).display]; }` -> `["\"Segoe UI\", Arial, sans-serif","rgb(26, 26, 26)","0px","none"]`. Reset with `media: null`. Optionally render the I1-e2 fixture sheet and compare against the same step run on a build without this plan.
- [ ] **Step 6: Targets.** `() => ["#newPatientBtn","#profileOpenBtn","#saveBtn"].map(s => Math.round(document.querySelector(s).getBoundingClientRect().height))` -> every number at least `44` (Save only once a sheet is shown).
- [ ] **Step 7: Sign-in and Team.** `browser_navigate` to `/login.html`: h1 uses the serif token, the primary button is 48 px and the inputs 46 px, the tagline and the forgot-password line show. The page loads only `login.css` and `login.js` (`browser_network_requests`: no `fonts.googleapis.com`). The Team panel needs multi-clinic mode (`MULTI_CLINIC=1`, `DATA_DIR` on a temp folder, an admin user): open Team and check the header, table rows and the "password ready" box; there is no tab strip yet (plan I1-h adds it).
- [ ] **Step 8: Clean up.** `browser_close`, stop uvicorn, `rm -rf .playwright-mcp` in the repo.

## Self-Review

- Spec coverage: tokens, type pairing decision, buttons and cards, brand mark SVG, sidebar items (segmented switch, rows), orb with pulse, wave bars and spinner ring, reduced motion, print unchanged (hash + pin), login and Team looks without behaviour change, named place for the I1-h tab.
- Not applied from the canvas: avatar circles and "Admin/Active" tags in the Team list need new markup in `team.js` (a behaviour-neutral but non-CSS change); the app-wide light/dark theming; the canvas's second accent options. Say if you want them.
- Placeholder scan: none.

**Decision needed:** approve system fonts over Google Fonts (and say if you want the self-hosting follow-up). Not done: font files, `team.js` markup, any backend or PDF change, any commit.
