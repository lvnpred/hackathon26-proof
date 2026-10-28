"""Lightday loose ends (2026-10-28): leftover Midnight symbols and off-rule copy are gone from the screen, and the
Dusk leftovers outside theme.css follow the tokens."""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def _nocomment(name):
    return re.sub(r"/\*.*?\*/", "", _read(name), flags=re.S)


def _code(js):
    """js with // line comments and /* */ blocks removed (history comments may still name old symbols)."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$|(?<=[\s;{}])//\s.*$", "", js)


def _rule(css, selector):
    m = re.search(r"(?:^|[\n}])\s*" + re.escape(selector) + r" \{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


def test_no_symbol_icons_or_off_rule_copy_remain_on_screen():
    html, app, ix, share = _read("index.html"), _read("app.js"), _read("ixlist.js"), _read("share.js")
    assert "Add your clinic details in Profile so they print on every prescription." in html
    for sym in ("⚙", "⚠", "•"):
        assert sym not in html and sym not in _code(app), sym
    assert 'textContent = "×"' not in app and '"×"' not in ix
    icon = re.search(r"const X_ICON = '([^']+)';", app).group(1)
    assert icon == re.search(r"const X_ICON = '([^']+)';", ix).group(1)
    decl = re.search(r"^\s*const X_ICON = (.*);$", app, re.M).group(1)
    assert re.fullmatch(r"'[^']*'", decl) and "${" not in decl and "+" not in decl and "`" not in decl
    assert len(re.findall(r"^\s*b\.innerHTML = X_ICON;\s*$", app, re.M)) == 1 and app.count("b.innerHTML") == 1
    assert 'stroke="currentColor" stroke-width="2"' in icon and 'aria-hidden="true"' in icon
    assert "b.innerHTML = X_ICON" in app and "x.innerHTML = X_ICON" in ix
    assert 'x.setAttribute("aria-label", "Delete this test")' in ix
    assert '" Check: " + j.warnings.join(" ")' in app and "} · ${llm}" in app
    assert '"The share link could not be loaded. Try again."' in share and "Please" not in share


def test_dusk_has_no_day_only_banner_or_check_box():
    theme = _nocomment("theme.css")
    banner = _rule(theme, ".adding-banner")
    assert "background:var(--action)" in banner and "color:var(--on-action)" in banner
    check = _rule(theme, ".name-check")
    assert "background:var(--sun-soft)" in check and "border-color:var(--sun-text)" in check and "color:var(--ink)" in check
    assert ".team-panel .field input" in theme[:theme.index("{", theme.index(".field input, .field textarea"))]
    assert "midnight" not in theme and "graphite" not in theme


# ---- Task 3: sign-in page in Lightday ---------------------------------------------------------------------------------
_DAY_LOGIN, _DUSK_LOGIN = ':root, :root[data-theme="day"]', ':root[data-theme="dusk"]'
_DAY_THEME, _DUSK_THEME = ':root, :root[data-theme="day"], #sheet', ':root[data-theme="dusk"]'


def _token_blocks(css):
    """{selector: {token: value}} of the :root token blocks."""
    return {sel.strip(): dict((k, v.strip()) for k, v in re.findall(r"(--[\w-]+):([^;]+);", body))
            for sel, body in re.findall(r"(:root[^{]*)\{([^}]*)\}", css)}


def test_login_is_lightday_with_the_mark_and_wordmark():
    html = _read("login.html")
    assert "<title>Sign in · lightday Clinic</title>" in html and "Doctor Dictation" not in html
    assert '<link rel="icon" href="lightday-app-icon.svg" type="image/svg+xml">' in html
    assert '<path class="ld-mark-sun" d="M6 19a10 10 0 0 1 20 0z"/>' in html
    assert '<rect class="ld-mark-horizon" x="3" y="22" width="26" height="3.5" rx="1.75"/>' in html
    assert '<h1 class="brand-title"><span class="ld-wordmark">lightday</span><span class="brand-app"> · Clinic</span></h1>' in html
    assert 'M12 5v14M5 12h14' not in html


def test_login_loads_themepick_in_head_before_its_stylesheet():
    head = _read("login.html").split("</head>")[0]
    assert head.index('<script src="themepick.js?v=') < head.index('login.css?v=3')


def test_login_tokens_match_theme_css_in_day_and_dusk():
    login_blocks, theme_blocks = _token_blocks(_nocomment("login.css")), _token_blocks(_nocomment("theme.css"))
    for login_sel, theme_sel in ((_DAY_LOGIN, _DAY_THEME), (_DUSK_LOGIN, _DUSK_THEME)):
        mine, theirs = login_blocks[login_sel], theme_blocks[theme_sel]
        assert len(mine) >= 14, login_sel
        for name, value in mine.items():
            assert value.lower() == theirs[name].lower(), (login_sel, name)
    shared = {k: v for sel, b in login_blocks.items() if sel not in (_DAY_LOGIN, _DUSK_LOGIN) for k, v in b.items()}
    theme_shared = {k: v for sel, b in theme_blocks.items() if sel not in (_DAY_THEME, _DUSK_THEME) for k, v in b.items()}
    for name in ("--font-sans", "--radius-md", "--radius-lg", "--control-h"):
        assert shared[name] == theme_shared[name], name
    login = _nocomment("login.css")
    assert "box-shadow:var(--focus-ring)" in login and "outline:3px" not in login and "#1456d9" not in login
    assert "fill:var(--sun)" in _rule(login, ".ld-mark-sun") and "fill:var(--ink)" in _rule(login, ".ld-mark-horizon")
    assert "font-weight:800" in _rule(login, ".ld-wordmark") and "letter-spacing:-0.02em" in _rule(login, ".ld-wordmark")
    assert "background:var(--action)" in _rule(login, "button.primary") and "min-height:var(--control-h)" in _rule(login, "input")


def test_sign_in_assets_are_public_and_nothing_else_opened():
    from doctor_dictation.api.session import is_public
    for p in ("/login", "/login.css", "/login.js", "/themepick.js", "/fonts.css", "/lightday-app-icon.svg",
              "/fonts/figtree-latin-400-normal.woff2"):
        assert is_public(p), p
    for p in ("/", "/index.html", "/app.js", "/theme.css", "/styles.css", "/fonts/../app.js", "/fonts/x.woff2/../../app.js",
              "/fonts/OFL-Figtree.txt", "/fonts/SOURCES.txt", "/fonts/", "/fonts/a.woff", "/fonts/.woff2", "/fonts/A.woff2",
              "/fonts/a/b.woff2", "/fonts/a.woff2/", "/fonts/a.woff2\n", "/fonts/%2e%2e/app.js", "/themepick.js/x"):
        assert not is_public(p), p


def test_traversal_through_the_real_middleware_stays_closed(multi):
    from fastapi.testclient import TestClient
    from doctor_dictation.api.app import create_app
    with TestClient(create_app(), follow_redirects=False) as c:
        for p in ("/themepick.js", "/lightday-app-icon.svg"):
            assert c.get(p).status_code == 200, p
        for p in ("/app.js", "/fonts/../app.js", "/fonts/..%2fapp.js", "/fonts/%2e%2e/app.js", "/fonts/x.woff2/../../app.js", "/index.html"):
            r = c.get(p)
            assert r.status_code in (303, 401, 404) and "IIFE" not in r.text, (p, r.status_code)
