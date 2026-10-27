"""Lightday look (2026-10-27): the screen is restyled to the owner's Lightday design system (docs/design-system/lightday).
theme.css is screen only and loads last, so print and the PDF never change. Two themes, Day and Dusk, are token sets named as
the design system names them; every other rule reads only tokens. The layout decisions of the Midnight build stay (mic words
beside the icon, a light rule before the steps, the empty sheet previews every section, patient left and vitals right,
full-height list panel). How it looks is checked by eye; these pin the contract."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend"
TOKENS = ROOT / "docs" / "design-system" / "lightday" / "project" / "tokens.json"
DAY_SEL = ':root, :root[data-theme="day"], #sheet'
DUSK_SEL = ':root[data-theme="dusk"]'


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def _nocomment(name):
    return re.sub(r"/\*.*?\*/", "", _read(name), flags=re.S)


def _outside_screen(css):
    """css with the brace-matched `@media screen { ... }` blocks removed."""
    out, i = [], 0
    while True:
        j = css.find("@media screen", i)
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


def _blocks(css):
    """{selector: body} of the token blocks (selectors starting with :root)."""
    return {sel.strip(): body for sel, body in re.findall(r"(:root[^{]*)\{([^}]*)\}", css)}


def _decls(body):
    return dict((k, v.strip()) for k, v in re.findall(r"(--[\w-]+):([^;]+);", body))


def _rule(css, selector):
    m = re.search(r"(?:^|[\n}])\s*" + re.escape(selector) + r" \{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


# ---- Task 1: tokens, themes, fonts ------------------------------------------------------------------------------------
def test_theme_css_loads_last_and_has_no_rule_outside_media_screen():
    html = _read("index.html")
    sheets = re.findall(r'<link rel="stylesheet" href="([^"?]+)\?v=\d+"', html)
    assert sheets[-1] == "theme.css" and sheets.count("theme.css") == 1
    assert '<link rel="stylesheet" href="theme.css?v=4" />' in html
    assert _outside_screen(_nocomment("theme.css")).strip() == ""


def test_day_and_dusk_carry_every_lightday_colour_token():
    blocks = _blocks(_nocomment("theme.css"))
    day, dusk = _decls(blocks[DAY_SEL]), _decls(blocks[DUSK_SEL])
    spot = {"--paper": ("#FAF7F0", "#14120E"), "--surface": ("#FFFFFF", "#1E1B16"), "--ink": ("#1C1A17", "#F4EEE3"),
            "--ink-muted": ("#5F584C", "#B4AA98"), "--sun": ("#F2A93B", "#F5B54A"), "--sun-soft": ("#FCEBCB", "#3A2C14"),
            "--on-sun": ("#1C1A17", "#1C1A17"), "--record": ("#C42B1C", "#FF6B5B"), "--leaf": ("#1D7445", "#5BC98B"),
            "--sheet": ("#FFFFFF", "#FFFFFF"), "--sheet-accent": ("#8A4F00", "#8A4F00"), "--line-control": ("#8A806E", "#807664")}
    for name, (d, k) in spot.items():
        assert day[name].upper() == d and dusk[name].upper() == k, name
    assert day["--action"] == dusk["--action"] == "var(--ink)" and day["--on-action"] == dusk["--on-action"] == "var(--surface)"
    assert set(day) == set(dusk)                                             # every theme sets every themed token
    for name in ("--shadow-sheet", "--halo-sun", "--halo-record", "--focus-ring"):
        assert name in day and name in dusk, name
    assert day["--focus-ring"] == "0 0 0 2px #FAF7F0, 0 0 0 4px #2350C2"
    assert dusk["--halo-sun"] == "0 0 0 8px #3A2C14"


def test_the_colour_tokens_are_exactly_the_design_systems():
    if not TOKENS.exists():
        pytest.skip("the design-system copy is not in this checkout")
    spec = json.loads(TOKENS.read_text(encoding="utf-8"))
    blocks = _blocks(_nocomment("theme.css"))
    themes = {"day": _decls(blocks[DAY_SEL]), "dusk": _decls(blocks[DUSK_SEL])}
    for tok in spec["color"]["tokens"]:
        for theme, value in tok["value"].items():
            want = "var(--%s)" % value.strip("{}") if value.startswith("{") else value
            assert themes[theme]["--" + tok["name"]].upper() == want.upper(), (theme, tok["name"])
    for tok in spec["shadow"]["tokens"]:
        for theme, value in tok["value"].items():
            assert themes[theme]["--" + tok["name"]].replace(" ", "") == value.replace(" ", ""), (theme, tok["name"])
    fixed = _decls(blocks[":root"])
    for group in ("spacing", "radius", "size"):
        for tok in spec[group]["tokens"]:
            assert fixed["--" + tok["name"]] == tok["value"], tok["name"]
    assert fixed["--font-sans"] == spec["type"]["families"]["sans"] and fixed["--font-serif"] == spec["type"]["families"]["serif"]


def test_no_raw_colour_outside_the_token_blocks_and_old_vars_follow_the_tokens():
    css = _nocomment("theme.css")
    rest = re.sub(r":root[^{]*\{[^}]*\}", "", css)
    assert not re.findall(r"#[0-9A-Fa-f]{3,8}\b", rest)
    assert "rgb" not in rest
    alias = _decls(_blocks(css)[":root, #sheet"])                            # recomputed on #sheet, so the sheet reads Day values
    for old, new in (("--muted", "--ink-muted"), ("--soft", "--line"), ("--card", "--surface"), ("--bg", "--paper"), ("--accent", "--sky"),
                     ("--ok", "--leaf"), ("--warn", "--sun-text"), ("--bad", "--record"), ("--radius", "--radius-lg"), ("--font-ui", "--font-sans")):
        assert alias[old] == "var(%s)" % new, old
    assert "--t-" not in css and "midnight" not in css and "graphite" not in css


def test_fonts_come_from_google_fonts_in_a_link_and_nothing_else_is_third_party():
    html = _read("index.html")
    head = html[:html.index("</head>")]
    href = ("https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800&amp;family=Source+Serif+4:opsz,wght@8..60,600;"
            "8..60,700&amp;family=Noto+Sans+Tamil:wght@400;700;800&amp;display=swap")
    assert '<link rel="stylesheet" href="%s" />' % href in head
    assert head.index(href) < head.index("styles.css?v=")
    assert '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />' in head
    others = [u for u in re.findall(r'(?:href|src)="(https?://[^"]+)"', html) if not u.startswith("https://fonts.g")]
    assert others == []
    assert "@import" not in _read("theme.css")


# ---- Task 2: components -----------------------------------------------------------------------------------------------
def test_app_bar_has_the_mark_the_wordmark_and_plain_word_buttons():
    html, theme = _read("index.html"), _nocomment("theme.css")
    bar = html[html.index('<header class="topbar'):html.index("</header>")]
    assert '<path class="ld-mark-sun" d="M6 19a10 10 0 0 1 20 0z"/>' in bar
    assert '<rect class="ld-mark-horizon" x="3" y="22" width="26" height="3.5" rx="1.75"/>' in bar
    assert '<span class="ld-wordmark">lightday</span><span class="brand-app"> · Clinic</span>' in bar
    assert bar.index('id="topClinic"') < bar.index('id="topDoctor"')
    for emoji in ("↺", "⚙", "🖨", "↻"):
        assert emoji not in bar and emoji not in html[html.index('<div class="workspace">'):html.index("<section id=\"sheet\"")], emoji
    assert re.search(r'<button id="newPatientBtn"[^>]*><svg[^>]*aria-hidden="true">.*?</svg> New patient</button>', bar)
    assert re.search(r'<button id="profileOpenBtn"[^>]*><svg[^>]*aria-hidden="true">.*?</svg> Profile</button>', bar)
    assert re.search(r'<button id="printBtn"[^>]*><svg[^>]*aria-hidden="true">.*?</svg> Print</button>', html)
    assert '<link rel="icon" href="lightday-app-icon.svg" type="image/svg+xml" />' in html
    icon = _read("lightday-app-icon.svg")
    assert 'viewBox="0 0 64 64"' in icon and 'fill="#F2A93B"' in icon and "<script" not in icon
    top = _rule(theme, ".topbar")
    assert "background:var(--surface)" in top and "border-bottom:1px solid var(--line)" in top
    logo = _rule(theme, ".brand-mark")
    assert "width:40px" in logo and "background:var(--sun-soft)" in logo and "border-radius:var(--radius-md)" in logo
    assert "fill:var(--sun)" in _rule(theme, ".ld-mark-sun") and "fill:var(--ink)" in _rule(theme, ".ld-mark-horizon")
    word = _rule(theme, ".ld-wordmark")
    assert "font-weight:800" in word and "letter-spacing:-0.02em" in word


def test_the_status_chip_is_a_pill_with_a_tone_per_state():
    theme = _nocomment("theme.css")
    assert "border-radius:var(--radius-full)" in _rule(theme, ".agent-chip, .badge")
    for state, tone in (("ready", "leaf"), ("listening", "record"), ("working", "sun"), ("failed", "record")):
        body = _rule(theme, ".agent-chip.%s" % state)
        soft = "--sun-soft" if tone == "sun" else "--%s-soft" % tone
        text = "--sun-text" if tone == "sun" else "--%s" % tone
        assert "background:var(%s)" % soft in body and "color:var(%s)" % text in body, state
    assert re.search(r"\.agent-chip::before \{[^}]*width:8px; height:8px; border-radius:50%; background:currentColor", theme)


def test_the_mic_is_the_sun_and_records_in_red_with_a_slow_pulse():
    theme = _nocomment("theme.css")
    mic = _rule(theme, ".mic")
    for v in ("width:var(--mic)", "height:var(--mic)", "background:var(--sun)", "color:var(--on-sun)", "box-shadow:var(--halo-sun)"):
        assert v in mic, v
    rec = _rule(theme, ".mic.recording")
    for v in ("background:var(--record)", "color:var(--on-record)", "box-shadow:var(--halo-record)", "animation:ld-pulse 1.6s ease-in-out infinite"):
        assert v in rec, v
    assert "@keyframes ld-pulse" in theme
    assert re.search(r"@media \(prefers-reduced-motion: reduce\) \{ \.mic\.recording, \.mic\.busy::after \{ animation:none; \}", theme)
    assert "background:var(--ink-muted)" in _rule(theme, ".mic.busy")


def test_one_primary_button_in_ink_and_ghost_for_the_rest_with_one_focus_ring():
    theme = _nocomment("theme.css")
    ghost = _rule(theme, "button")
    assert "background:var(--surface)" in ghost and "border-color:var(--line-control)" in ghost and "border-radius:var(--radius-md)" in ghost
    prim = _rule(theme, "button.primary, .save, .rx-act.primary, #spellMic[aria-pressed=\"true\"]")
    assert "background:var(--action)" in prim and "color:var(--on-action)" in prim
    assert "background:var(--surface)" in _rule(theme, ".save.print")
    ring = re.search(r"([^{}]*:focus-visible[^{}]*)\{ outline:2px solid transparent; outline-offset:0; box-shadow:var\(--focus-ring\); \}", theme)
    assert ring and all(s in ring.group(1) for s in ("button:focus-visible", "input:focus-visible", ".mic:focus-visible", "[contenteditable]:focus-visible"))


def test_the_list_panel_is_a_light_surface_and_the_open_row_glows_sun_soft():
    theme = _nocomment("theme.css")
    side = _rule(theme, ".sidebar")
    assert "background:var(--surface)" in side and "color:var(--ink)" in side
    item = _rule(theme, ".today-item")
    assert "min-height:var(--row-h)" in item and "border-radius:var(--radius-sm)" in item
    assert "background:var(--sun-soft)" in _rule(theme, ".today-item.active, .today-item.active:hover")
    assert "color:var(--sun-text)" in _rule(theme, ".today-item.active .today-meta")


def test_what_to_say_is_a_quiet_numbered_guide():
    html, theme = _read("index.html"), _nocomment("theme.css")
    assert '<div class="cue-title">What to say</div>' in html and 'id="cuePanel"' in html
    panel = _rule(theme, ".cue-panel")
    assert "background:none" in panel and "counter-reset:cue" in panel
    title = _rule(theme, ".cue-title")
    for v in ("font-size:13px", "font-weight:800", "letter-spacing:.8px", "text-transform:uppercase"):
        assert v in title, v
    num = _rule(theme, ".cue-panel li::before")
    assert "counter(cue)" in num and "color:var(--ink-muted)" in num and "font-variant-numeric:tabular-nums" in num
    assert "font-weight:700" in _rule(theme, ".cue-lead") and "color:var(--ink)" in _rule(theme, ".cue-lead")
    rest = _rule(theme, ".cue-rest")
    assert "color:var(--ink-muted)" in rest and "font-size:14px" in rest
    assert "sun-soft" not in panel


def test_the_sheet_is_white_paper_in_both_themes():
    theme = _nocomment("theme.css")
    sheet = _rule(theme, "#sheet")
    for v in ("background:var(--sheet)", "color:var(--sheet-ink)", "border-radius:var(--radius-lg)", "box-shadow:var(--shadow-sheet)",
              "padding:28px var(--space-9) var(--space-8)"):
        assert v in sheet, v
    h2 = _rule(theme, "#sheet h2")
    assert "font-family:var(--font-serif)" in h2 and "font-size:22px" in h2 and "border-bottom:2px solid var(--sheet-ink)" in h2
    assert re.search(r'#sheet\.empty \.sec::after \{ content:"Not dictated yet";[^}]*font-size:14px; color:var\(--sheet-muted\)', theme)
    assert 'content:"Not dictated yet"' not in _outside_screen(theme)
    assert "background:var(--paper)" in _rule(theme, "body")


def test_dialogs_follow_the_theme_and_tinted_notes_use_status_tokens():
    theme = _nocomment("theme.css")
    dlg = _rule(theme, "dialog.panel")
    assert "background:var(--surface)" in dlg and "color:var(--ink)" in dlg
    assert "background:var(--surface-sunk)" in _rule(theme, ".field input, .field textarea, .spell-line input, #shareTel, .team-panel .team-filter input[type=\"search\"]")
    for sel, soft in ((".lh-warn", "--sun-soft"), (".lh-error, .team-panel .team-error, .error", "--record-soft"),
                      (".lh-done, .team-panel .team-secret", "--leaf-soft")):
        assert "background:var(%s)" % soft in _rule(theme, sel), sel
    assert "background:var(--surface)" in _rule(theme, ".lh-foot")
    assert "background:var(--surface-sunk)" in _rule(theme, ".lh-preview")


def test_the_theme_swatches_are_tokens_too():
    css = _nocomment("theme.css")
    assert "var(--sw-day-paper)" in _rule(css, '.theme-swatch[data-swatch="day"]')
    assert "var(--sw-dusk-paper)" in _rule(css, '.theme-swatch[data-swatch="dusk"]')


# ---- layout kept from the Midnight build (owner-approved) --------------------------------------------------------------
def test_the_empty_sheet_previews_every_section_screen_only_and_is_inert():
    html, styles, app = _read("index.html"), _read("styles.css"), _read("app.js")
    assert '<div id="sheetBody" inert>' in html and 'id="sheet" class="empty"' in html
    assert re.search(r'<section id="sheet"[^>]*inert', html) is None            # dictguard.js owns inert on #sheet
    assert "#sheet.empty #sheetBody { display:none; }" not in styles
    assert "#sheet.empty #sheetBody { display:block; }" in styles               # the print rule is unchanged
    assert 'sheetEl.classList.remove("empty"); $("sheetBody").inert = false;' in app
    assert 'sheetEl.classList.add("empty"); $("sheetBody").inert = true;' in app


def test_r1_the_mic_holds_the_icon_only_and_the_words_sit_beside_it_without_shifting():
    html, theme, app = _read("index.html"), _nocomment("theme.css"), _read("app.js")
    button = html[html.index('<button id="recBtn"'):]
    button = button[:button.index("</button>")]
    assert "mic-label" not in button and "mic-icon" in button
    assert '<span id="micLabel" class="mic-label" aria-hidden="true">Tap to dictate</span>' in html
    assert html.index('id="recBtn"') < html.index('id="micLabel"') < html.index('id="timer"') < html.index('id="wave"')
    assert 'function setMicLabel(t) { const l = $("micLabel"); if (l) l.textContent = t; recBtn.setAttribute("aria-label", t); }' in app
    assert re.search(r"\.dictation \{[^}]*display:grid; grid-template-columns:var\(--mic\) 76px 100px", theme)
    assert re.search(r"\.rec-dot, \.rec-dot\.on \{[^}]*display:flex; visibility:hidden", theme)
    assert re.search(r"\.rec-dot\.on \{ visibility:visible; \}", theme)
    assert re.search(r"\.timer \{[^}]*font-variant-numeric:tabular-nums[^}]*min-width:", theme)
    assert re.search(r"\.mic-label \{[^}]*width:\d+px[^}]*white-space:nowrap", theme)


def test_r2_a_very_light_rule_separates_what_to_say_from_the_steps():
    rule = _rule(_nocomment("theme.css"), ".cue-panel:not([hidden]) + .stp-list")
    assert "border-top:1px solid var(--line)" in rule and "margin-top:14px" in rule and "padding-top:14px" in rule


def test_r3_the_screen_sheet_keeps_patient_left_and_vitals_right():
    html, theme = _read("index.html"), _nocomment("theme.css")
    for field in ('id="pDate"', 'id="pOp" contenteditable="true" data-field="opNo"', 'id="pName" contenteditable="true" data-field="patientName"',
                  'id="pAge" contenteditable="true" data-field="ageSex"', 'id="pVitals"'):
        assert field in html, field
    assert re.search(r"#sheet \.patient-block \{[^}]*display:grid; grid-template-columns:minmax\(0, ?1fr\) auto", theme)
    for label in ('#sheet #pAge::before { content:"Age / Sex"', '#sheet #pOp::before { content:"OP / IP No"', '#sheet #pDate::before { content:"Date"'):
        assert label in theme, label
    assert re.search(r"#sheet #pVitals \{[^}]*display:grid; grid-template-columns:auto", theme)
    assert re.search(r"@media \(max-width:640px\) \{[^@]*#sheet \.patient-block \{ grid-template-columns:1fr; \}", theme)
    title = _rule(theme, "#sheet .sec-title")
    for v in ("background:none", "border:0", "font-family:var(--font-sans)", "font-size:13px", "letter-spacing:.8px", "font-weight:800", "color:var(--sheet-ink)"):
        assert v in title, v
    assert "border-top:1px solid var(--sheet-line)" in _rule(theme, "#sheetBody > .sec:not([hidden]) ~ .sec:not([hidden])")


def test_m4_the_sidebar_is_a_full_height_frame_with_a_scrolling_list():
    theme = _nocomment("theme.css")
    wide = theme[theme.index("@media (min-width:1001px)"):]
    assert re.search(r"\.sidebar \{[^}]*position:sticky; top:var\(--topbar-h, 64px\); height:calc\(100vh - var\(--topbar-h, 64px\)\); display:flex; flex-direction:column", wide)
    assert re.search(r"\.sidebar \{[^}]*border-right:1px solid var\(--line\)", wide)
    assert re.search(r"\.today-list \{[^}]*flex:1 1 auto; min-height:0; overflow-y:auto", wide)
