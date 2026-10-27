"""Visual polish (I1-f2): static checks. How it looks is the manual checklist in the plan."""
import hashlib
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1] / "frontend"
# the print rules of styles.css as they were before this plan (from /* --- print: only the sheet to /* Authorship (M3)
PRINT_BLOCK_SHA256 = "8693328ac60e9c0eca84d4fc66dc385abcbfdba8c43fece96316c65f3f299c36"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def _nocomment(name):
    return re.sub(r"/\*.*?\*/", "", _read(name), flags=re.S)


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
    polish = _nocomment("polish.css")
    rest = _strip_blocks(_strip_blocks(polish, "@media screen"), "@media print")
    assert rest.strip() == ""                      # every rule is inside the screen block or the print pin
    pin = polish[polish.index("@media print"):polish.index("@media screen")]
    assert "--ink:#1a1a1a" in pin and "--muted:#5f6b7a" in pin and '"Segoe UI", Arial' in pin


def test_no_page_loads_anything_from_a_third_party_and_the_fonts_are_tokens():
    for name in ("index.html", "login.html", "styles.css", "polish.css", "login.css", "team.css", "steps.css", "rx.css", "letterhead.css"):
        text = _read(name)
        assert "googleapis" not in text and "gstatic" not in text and "@import" not in text and not re.search(r'(?:href|src)="https?://', text), name
        assert not re.search(r"url\(\s*['\"]?(?:https?:)?//", text), name
    css = _read("styles.css")
    assert '--font-ui:"Public Sans", "Segoe UI"' in css and '--font-serif:"Source Serif 4"' in css and "font-family: var(--font-ui)" in css
    assert "--font-serif" in _read("login.css") and "@font-face" not in css
    assert "@font-face" not in _read("polish.css") and "@font-face" not in _read("login.css")
    # the stylesheets are linked with a version, and the shared one moved past the pre-polish v=9
    html, login = _read("index.html"), _read("login.html")
    assert int(re.search(r"styles\.css\?v=(\d+)", html).group(1)) >= 10 and int(re.search(r"polish\.css\?v=(\d+)", html).group(1)) >= 1 and int(re.search(r"steps\.css\?v=(\d+)", html).group(1)) >= 2
    assert html.index("steps.css?v=") < html.index("polish.css?v=")      # polish loads after the sheets it refines
    assert int(re.search(r"login\.css\?v=(\d+)", login).group(1)) >= 2


def test_the_brand_mark_and_orb_are_inline_svg_and_the_recording_hooks_are_unchanged():
    html, login, app = _read("index.html"), _read("login.html"), _read("app.js")
    assert "✚" not in html and "🎤" not in html and "● REC" not in html and "⚕" not in login and "&#9877;" not in login
    assert html.count('<path d="M12 5v14M5 12h14"/>') == 1 and login.count('<path d="M12 5v14M5 12h14"/>') == 1
    assert 'id="wave" class="rec-dot" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><span class="rec-text">REC</span>' in html
    assert 'wave.classList.add("on")' in app and 'wave.classList.remove("on")' in app and 'class="mic-label"' in html


def test_every_animation_is_screen_only_and_switched_off_for_reduced_motion():
    css = _nocomment("polish.css")
    screen = css[css.index("@media screen"):]
    assert screen.count("animation:") >= 4 and "@media (prefers-reduced-motion: reduce) { .mic.recording, .mic.busy::after, .rec-dot i { animation:none; }" in screen
    assert "animation" not in _nocomment("login.css") and "animation" not in _nocomment("team.css") and "animation" not in _nocomment("steps.css")
    # without animation the recording orb still shows a red ring of its own
    assert re.search(r"\.mic\.recording \{[^}]*box-shadow:0 0 0 8px #[0-9a-f]{3,6}", screen)


def test_login_and_team_keep_their_behaviour_and_leave_a_named_place_for_the_clinic_medicines_tab():
    login, team_css = _read("login.html"), _read("team.css")
    for token in ('id="loginForm"', 'id="changeForm"', 'id="msg" role="alert"', 'id="signoutLink"', 'autocomplete="current-password"', "Use a different account"):
        assert token in login, token
    assert ".team-panel .team-tabs" in team_css and "plan I1-h" in team_css    # plan I1-h4 adds the tab itself, so team.js may name it
    assert "Clinic medicines" not in login


def test_new_controls_are_44px_high():
    polish, login, team = _read("polish.css"), _read("login.css"), _read("team.css")
    assert ".topbar-actions button, .panel-actions button, .save-row button, .lh-foot button, .retry, .lh-act, #lhCloseBtn { min-height:44px; }" in polish
    assert "min-height:44px" in login and "min-height:48px" in login and ".team-panel .team-tab { min-height:44px;" in team


def test_focus_rings_are_3px_in_the_accent_colour_and_the_panes_follow_the_real_topbar_height():
    for name in ("login.css", "team.css", "steps.css"):
        css = _nocomment(name)
        rings = re.findall(r"outline:\s*3px solid ([^;}]+)", css)
        assert rings and all(r.strip() == "var(--accent)" for r in rings), name     # 2.10:1 pale blue is gone
        assert "8fb2ff" not in css, name
    polish = _nocomment("polish.css")
    assert re.search(r"@media \(min-width:1001px\) \{ \.sidebar, \.middle \{ top:calc\(var\(--topbar-h, 64px\) \+ 8px\); \} \}", polish)
    assert re.search(r"button \{ font-family:inherit; \}", polish)


def test_the_sign_in_stylesheet_is_self_contained():
    css = _nocomment("login.css")
    defined = set(re.findall(r"(--[\w-]+)\s*:", css))
    used = set(re.findall(r"var\((--[\w-]+)", css))
    assert used and used <= defined, used - defined        # styles.css is not a public file: every token is defined here
    assert "url(" not in css and "#changeUser { min-height:0; padding:0; border:0; }" in css


def test_team_table_never_shrinks_the_buttons_are_44px_and_every_focus_ring_is_the_accent():
    team = _nocomment("team.css")
    box = re.search(r"\.team-panel \.team-table-box \{([^}]*)\}", team).group(1)
    assert "flex:none" in box.replace(" ", "") or "flex:0 0 auto" in box          # a flex child with overflow shrinks to a strip otherwise
    assert re.search(r"\.team-panel button \{ min-height:44px; \}", team)
    assert re.search(r"\.team-panel \.team-row-actions button \{[^}]*min-height:36px", team)   # row actions stay small
    polish = _nocomment("polish.css")
    ring = re.search(r"([^{}]*:focus-visible)\s*\{ outline:3px solid var\(--accent\); outline-offset:2px; \}", polish)
    assert ring and all(s in ring.group(1) for s in ("button:focus-visible", '[role="button"]', "a:focus-visible", "select:focus-visible", ".mic:focus-visible"))
    assert "outline:none" not in polish.replace(" ", "") and "outline:0" not in polish.replace(" ", "")
    assert "background:#5f6f69" in polish and "#6b7a74" not in polish        # white on the busy orb: 5.6:1, not 4.51
