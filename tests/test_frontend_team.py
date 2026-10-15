"""Team panel wiring (team.js, team.css, the one button in index.html). Static checks; no browser."""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def test_index_has_one_hidden_team_button_right_after_profile():
    html = _read("index.html")
    assert html.count('id="teamOpenBtn"') == 1
    tag = re.search(r'<button id="teamOpenBtn"[^>]*>', html).group(0)
    assert " hidden" in tag and 'type="button"' in tag
    assert html.index('id="profileOpenBtn"') < html.index('id="teamOpenBtn"') < html.index('id="signOutBtn"')


def test_team_assets_are_linked_once_and_team_js_loads_after_auth_js():
    html = _read("index.html")
    assert html.count("team.js") == 1 and html.count("team.css") == 1
    assert '<link rel="stylesheet" href="team.css' in html
    assert html.index("auth.js") < html.index("team.js")


def test_team_js_uses_every_users_route_and_posts_the_changes():
    js = _read("team.js")
    assert '"/api/v1/users"' in js
    for verb in ("/disable", "/enable", "/reset-password"):
        assert verb in js, verb
    assert js.count('method: "POST"') >= 3


def test_team_list_shows_name_username_status_and_last_sign_in():
    js = _read("team.js")
    for word in ("display_name", "username", "is_active", "last_login_at", "Last sign-in", "Never", "(you)"):
        assert word in js, word


def test_team_js_never_turns_user_data_into_html():
    js = _read("team.js")
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", js)
    assert "textContent" in js


def test_temporary_password_is_shown_once_with_a_copy_button_and_a_warning():
    js = _read("team.js")
    assert "temporary_password" in js and "navigator.clipboard.writeText" in js
    assert "it will not be shown again" in js
    assert re.search(r'addEventListener\("close", clearSecret\)', js)      # closing the panel forgets it
    clear = js.split("function clearSecret()")[1].split("}")[0]
    assert 'textContent = ""' in clear


def test_team_js_confirms_risky_actions_and_offers_none_on_your_own_row():
    js = _read("team.js")
    assert js.count("window.confirm(") >= 2
    assert "u.id === t.me" in js and re.search(r"if \(!you\)", js)


def test_team_css_rules_are_scoped_to_the_team_panel():
    css = re.sub(r"/\*.*?\*/", "", _read("team.css"), flags=re.S)
    selectors = [s.strip() for block in re.findall(r"([^{}]+)\{", css) for s in block.split(",")]
    assert selectors and all(s.startswith((".team-panel", "dialog.team-panel")) for s in selectors), selectors


def test_team_row_buttons_are_named_for_the_user_and_set_with_setattribute():
    js = _read("team.js")
    for label in ('"Disable "', '"Enable "', '"Reset password for "'):
        assert label in js, label
    assert js.count('setAttribute("aria-label"') >= 2


def test_team_js_moves_focus_after_actions_and_refreshes_after_a_failure():
    js = _read("team.js")
    assert 'id: "teamTitle", tabindex: "-1"' in js
    assert 'el("teamTitle").focus()' in js and 'el("teamNewUsername").focus()' in js
    done = js.split("function doneSecret()")[1].split("\n  }")[0]
    assert 'el("teamNewUsername").focus()' in done and "clearSecret()" in done
    assert js.count("await refresh()") >= 4                    # success paths and the failure paths


def test_team_js_builds_ids_with_number_and_checks_for_a_password_before_showing_it():
    js = _read("team.js")
    assert "Number(u.id)" in js and "u.id + " not in js
    assert js.count("body.temporary_password") + js.count("b.temporary_password") >= 2


def test_team_js_forgets_the_password_on_pagehide_and_only_a_short_line_is_a_live_region():
    js = _read("team.js")
    assert re.search(r'window\.addEventListener\("pagehide", clearSecret\)', js)
    assert js.count('role: "status"') == 1
    assert 'id: "teamSecret", class: "team-secret", role' not in js          # the box holding the password is not live
    assert 'id: "teamSecretReady"' in js and "Password ready" in js
    value = re.search(r'make\("code", \{[^}]*\}', js).group(0)
    assert "role" not in value and "aria-live" not in js
