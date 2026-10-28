"""The browser side is plain JS; check the wiring that must not regress. No browser needed."""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def test_auth_js_loads_before_app_js():
    html = _read("index.html")
    assert html.index("auth.js") < html.index("app.js")


def test_index_has_a_sign_out_button():
    assert 'id="signOutBtn"' in _read("index.html")


def test_auth_js_adds_the_csrf_header_and_handles_401_and_the_gate():
    js = _read("auth.js")
    assert "X-DD-Client" in js and "/login" in js
    assert "must_change_password" in js and "401" in js
    assert re.search(r"POST|PUT|DELETE|PATCH", js)


def test_login_page_posts_to_the_auth_routes_and_never_names_the_wrong_field():
    js, html = _read("login.js"), _read("login.html")
    assert "/api/v1/auth/login" in js and "/api/v1/auth/change-password" in js
    assert 'type="password"' in html
    assert "username is wrong" not in js.lower() and "password is wrong" not in js.lower()


def test_login_assets_are_the_public_ones_the_middleware_allows():
    from doctor_dictation.api.session import is_public
    html = _read("login.html")
    assets = [a for a in re.findall(r'(?:href|src)="([^"]+)"', html) if not a.startswith("data:")]
    assert {"login.css", "login.js"} <= {a.split("?")[0] for a in assets}
    for asset in assets:
        assert is_public("/" + asset.split("?")[0]), asset
    assert "auth.js" not in html          # the login page must not redirect to itself


def test_login_js_survives_an_unreachable_server():
    js = _read("login.js")
    assert re.search(r"try\s*\{[^}]*await fetch\(url", js)
    assert "catch" in js and "Could not reach the server. Check your connection and try again." in js


def test_login_js_disables_the_submit_button_in_flight_and_restores_it_in_finally():
    js = _read("login.js")
    assert ".disabled = true" in js
    assert re.search(r"finally\s*\{[^}]*\.disabled = false", js)


def test_login_js_clears_the_password_after_copying_it_to_the_change_form():
    assert '$("password").value = ""' in _read("login.js")


def test_auth_js_sends_must_change_password_users_to_login_before_the_top_bar():
    js = _read("auth.js")
    assert "me.must_change_password" in js
    assert js.index("me.must_change_password") < js.index('getElementById("topClinic")')


def test_forced_change_screen_has_a_way_out():
    js, html = _read("login.js"), _read("login.html")
    assert 'id="signoutLink"' in html and 'type="button"' in html.split('id="signoutLink"')[0].rsplit("<button", 1)[1] + '"'
    assert "Use a different account" in html
    assert "/api/v1/auth/logout" in js and 'show("login")' in js


def test_login_page_has_icon_and_a_hidden_username_for_password_managers():
    html, js = _read("login.html"), _read("login.js")
    assert '<link rel="icon" href="lightday-app-icon.svg" type="image/svg+xml">' in html
    assert 'id="changeUser"' in html and 'autocomplete="username"' in html and "readonly" in html
    assert 'aria-hidden="true"' in html.split('id="changeUser"')[1].split(">")[0] + ">" or "aria-hidden" in html
    assert "changeUser" in js
