"""Midnight look (2026-10-27): theme.css is screen only and loads last; the empty sheet previews every section and is inert;
the "What to say" panel is always in the page. How it looks is checked by eye; these pin the contract."""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1] / "frontend"


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


def test_theme_css_loads_last_and_has_no_rule_outside_media_screen():
    html = _read("index.html")
    sheets = re.findall(r'<link rel="stylesheet" href="([^"?]+)\?v=\d+"', html)
    assert sheets[-1] == "theme.css" and sheets.count("theme.css") == 1
    assert _outside_screen(_nocomment("theme.css")).strip() == ""


def test_theme_css_carries_the_midnight_palette():
    css = _read("theme.css")
    for value in ("#0B1220", "#A9B3C6", "#1E2A40", "#16213A", "#EEF0F3", "#E1E4EA", "#0B7A6E", "#E2F3F1", "#14B8A6",
                  "#CDEFEA", "#C81E1E", "#0B0D12", "0 1px 3px rgba(0,0,0,.12), 0 12px 32px rgba(11,18,32,.10)"):
        assert value.lower() in css.lower(), value
    assert "@font-face" not in css and "@import" not in css and "googleapis" not in css


def test_the_empty_sheet_previews_every_section_screen_only_and_is_inert():
    html, styles, theme, app = _read("index.html"), _read("styles.css"), _nocomment("theme.css"), _read("app.js")
    assert '<div id="sheetBody" inert>' in html and 'id="sheet" class="empty"' in html
    assert re.search(r'<section id="sheet"[^>]*inert', html) is None            # dictguard.js owns inert on #sheet
    assert "#sheet.empty #sheetBody { display:none; }" not in styles            # the rule that showed nothing is gone
    assert "#sheet.empty #sheetBody { display:block; }" in styles               # the print rule is unchanged
    assert 'content:"Not dictated yet"' in theme and "#sheet.empty .sec::after" in theme
    assert 'content:"Not dictated yet"' not in _outside_screen(theme)
    assert 'sheetEl.classList.remove("empty"); $("sheetBody").inert = false;' in app
    assert 'sheetEl.classList.add("empty"); $("sheetBody").inert = true;' in app


def test_the_what_to_say_panel_is_grey_and_quiet():
    html, theme = _read("index.html"), _nocomment("theme.css")
    assert '<div class="cue-title">What to say</div>' in html and 'id="cuePanel"' in html
    for value in ("#4A5468", "#5B6476", "font-size:13px", "text-transform:uppercase"):
        assert value in theme
    assert re.search(r"\.cue-panel \{[^}]*background:none", theme)


# ---- round 2 (owner review 2026-10-27) ------------------------------------------------------------------------------
def _theme_blocks(css):
    """[(selector, body)] of the theme token blocks: `:root...{...}` inside theme.css."""
    return re.findall(r"(:root[^{]*)\{([^}]*)\}", css)


def test_r1_the_mic_holds_the_icon_only_and_the_words_sit_beside_it_without_shifting():
    html, theme, app = _read("index.html"), _nocomment("theme.css"), _read("app.js")
    button = html[html.index('<button id="recBtn"'):]
    button = button[:button.index("</button>")]
    assert "mic-label" not in button and "mic-icon" in button                 # the circle holds the icon only
    assert '<span id="micLabel" class="mic-label" aria-hidden="true">Tap to dictate</span>' in html
    assert html.index('id="recBtn"') < html.index('id="micLabel"') < html.index('id="timer"') < html.index('id="wave"')
    assert 'function setMicLabel(t) { const l = $("micLabel"); if (l) l.textContent = t; recBtn.setAttribute("aria-label", t); }' in app
    for words in ('setMicLabel("Tap to stop");', '"Tap to dictate"', 'setMicLabel("Working…")'):
        assert words in app, words
    assert "■ Stop" not in app
    assert re.search(r"\.mic \{[^}]*width:88px; height:88px", theme)
    assert re.search(r"\.dictation \{[^}]*display:grid", theme)                # fixed boxes: no reflow between states
    assert re.search(r"\.rec-dot, \.rec-dot\.on \{[^}]*display:flex; visibility:hidden", theme)
    assert re.search(r"\.rec-dot\.on \{ visibility:visible; \}", theme)
    assert re.search(r"\.timer \{[^}]*font-variant-numeric:tabular-nums[^}]*min-width:", theme)
    assert re.search(r"\.mic-label \{[^}]*width:\d+px[^}]*white-space:nowrap", theme)


def test_r2_a_very_light_rule_separates_what_to_say_from_the_steps():
    theme = _nocomment("theme.css")
    rule = re.search(r"\.cue-panel:not\(\[hidden\]\) \+ \.stp-list \{([^}]*)\}", theme).group(1)
    assert "border-top:1px solid var(--t-divider)" in rule and "margin-top:14px" in rule and "padding-top:14px" in rule
    assert all("--t-divider:#E6E9EF" in body for sel, body in _theme_blocks(theme) if "graphite" not in sel)


def test_r3_the_screen_sheet_follows_the_mockup_and_keeps_the_fields():
    html, theme = _read("index.html"), _nocomment("theme.css")
    for field in ('id="pDate"', 'id="pOp" contenteditable="true" data-field="opNo"', 'id="pName" contenteditable="true" data-field="patientName"',
                  'id="pAge" contenteditable="true" data-field="ageSex"', 'id="pVitals"'):
        assert field in html, field                                           # same elements, restyled by CSS only
    assert re.search(r"#sheet \.patient-block \{[^}]*display:grid; grid-template-columns:minmax\(0, ?1fr\) auto", theme)
    assert re.search(r"#sheet #pName \{[^}]*font-size:20px; font-weight:700", theme)
    for label in ('#sheet #pAge::before { content:"Age / Sex"', '#sheet #pOp::before { content:"OP / IP No"', '#sheet #pDate::before { content:"Date"'):
        assert label in theme, label
    assert re.search(r"#sheet #pVitals \{[^}]*display:grid; grid-template-columns:auto", theme)
    assert re.search(r"@media \(max-width:640px\) \{[^@]*#sheet \.patient-block \{ grid-template-columns:1fr; \}", theme)
    assert re.search(r"#sheet h2 \{[^}]*font-size:21px[^}]*border-bottom:2px solid #0B0D12", theme)
    title = re.search(r"#sheet \.sec-title \{([^}]*)\}", theme).group(1)
    for v in ("background:none", "border:0", "font-family:var(--font-ui)", "font-size:13px", "letter-spacing:.8px", "font-weight:800", "color:#0B0D12"):
        assert v in title, v
    assert re.search(r"#sheetBody > \.sec:not\(\[hidden\]\) ~ \.sec:not\(\[hidden\]\) \{[^}]*border-top:1px solid #E2E4E9", theme)
    assert re.search(r'#sheet\.empty \.sec::after \{ content:"Not dictated yet";[^}]*font-size:14px; color:#6B7180', theme)
    assert re.search(r"#sheet \.disclaimer \{[^}]*font-size:12px", theme)


def test_r4_three_themes_are_token_sets_and_the_frame_reads_only_tokens():
    css = _nocomment("theme.css")
    blocks = dict((sel.strip(), body) for sel, body in _theme_blocks(css))
    assert set(blocks) == {':root, :root[data-theme="midnight"]', ':root[data-theme="ink"]', ':root[data-theme="graphite"]'}
    ink, gr = blocks[':root[data-theme="ink"]'], blocks[':root[data-theme="graphite"]']
    for v in ("--t-top-bg:#FFFFFF", "--t-top-fg:#0B0D12", "--accent:#1F4FD8", "--t-logo-bg:#0B0D12", "--t-logo-fg:#FFFFFF", "--t-mic:#0B0D12"):
        assert v in ink, v
    for v in ("--t-top-bg:#0D0F13", "--t-bg:#0D0F13", "--t-card:#161A21", "--t-fg:#F4F5F7", "--t-muted:#A1A7B3", "--t-line:#262C36",
              "--accent:#5B8CFF", "--t-on-accent:#0D0F13", "--t-paper:#2F5FD0"):
        assert v in gr, v
    names = [set(re.findall(r"(--[\w-]+):", b)) for b in blocks.values()]
    assert names[0] == names[1] == names[2]                                   # every theme sets every token
    # outside the token blocks, the only literal colours are the white paper's own ink and the fixed recording red
    rest = re.sub(r":root[^{]*\{[^}]*\}", "", css)
    rest = re.sub(r'\.theme-swatch\[data-swatch="\w+"\] \{[^}]*\}', "", rest)            # a swatch shows its own theme's colours
    paper = {"#fff", "#0b0d12", "#e2e4e9", "#5b6170", "#6b7180", "#c3c7d0", "#c81e1e", "#b42318", "#f0faf8"}
    assert {h.lower() for h in re.findall(r"#[0-9A-Fa-f]{3,8}\b", rest)} <= paper
    assert "#sheet, dialog.panel { --ink:#0B0D12;" in rest and "--accent:var(--t-paper)" in rest   # sheet and dialogs stay white paper


def test_m4_the_sidebar_is_a_full_height_frame_with_a_scrolling_list():
    theme = _nocomment("theme.css")
    wide = theme[theme.index("@media (min-width:1001px)"):]
    assert re.search(r"\.sidebar \{[^}]*position:sticky; top:var\(--topbar-h, 64px\); height:calc\(100vh - var\(--topbar-h, 64px\)\); display:flex; flex-direction:column", wide)
    assert re.search(r"\.sidebar \{[^}]*border-right:1px solid var\(--t-side-line\)", wide)
    assert re.search(r"\.today-list \{[^}]*flex:1 1 auto; min-height:0; overflow-y:auto", wide)
