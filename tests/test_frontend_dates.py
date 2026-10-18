"""Iteration 3, page side: frontend/dates.js under node (same table as the server), the wiring, the deployment files.
Offline; no browser."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend"
TABLE = json.loads((Path(__file__).parent / "data" / "date_formats.json").read_text(encoding="utf-8"))
FAKEDOM = Path(__file__).parent / "team_medicines_fakedom.js"


def _read(path):
    return Path(path).read_text(encoding="utf-8")


def _code(name):
    text = re.sub(r"/\*.*?\*/", "", _read(FRONT / name), flags=re.S)
    return "\n".join(re.sub(r"(^|\s)//.*$", "", line) for line in text.splitlines())


def _node(body, tz="Asia/Kolkata"):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    js = ("globalThis.window = globalThis; require(process.argv[1]);"
          "(async () => {" + body + "})().catch((e) => { console.error(e.stack); process.exit(1); });")
    import os
    out = subprocess.run([node, "-e", js, str(FRONT / "dates.js")], capture_output=True, text=True, timeout=30, env={**os.environ, "TZ": tz})
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_page_formatter_matches_the_shared_table():
    r = _node("""const T = %s; const bad = [];
      const check = (kind, fn, c, args) => { const got = fn(c["in"]); if (got !== c.out) bad.push([kind, c["in"], got, c.out]); };
      for (const c of T.date) { Dates.init({ locale: c.locale, timezone: "Asia/Kolkata" }); check("date", Dates.date, c); }
      for (const c of T.label) { Dates.init({ locale: c.locale, timezone: "Asia/Kolkata" }); check("label", Dates.label, c); }
      for (const c of T.time) { Dates.init({ locale: c.locale, timezone: c.tz }); check("time", Dates.time, c); }
      for (const c of T.datetime) { Dates.init({ locale: c.locale, timezone: c.tz }); check("datetime", Dates.dateTime, c); }
      console.log(JSON.stringify(bad));""" % json.dumps(TABLE))
    assert r == []


def test_invalid_input_gives_an_empty_string_never_invalid_date():
    r = _node("""const T = %s; const got = [];
      for (const v of T.invalid.date) got.push(Dates.date(v));
      for (const v of T.invalid.label) got.push(Dates.label(v));
      for (const v of T.invalid.instant) got.push(Dates.time(v), Dates.dateTime(v));
      got.push(Dates.time(new Date(NaN)), Dates.date(undefined), Dates.label({}));
      console.log(JSON.stringify(got));""" % json.dumps(TABLE))
    assert r and all(v == "" for v in r)


def test_init_takes_the_locale_and_zone_and_survives_bad_values():
    r = _node("""const out = {};
      out.before = [Dates.locale(), Dates.zone()];                       // the defaults match the server
      Dates.init({ locale: "en-IN", timezone: "America/New_York" }); out.ny = Dates.time("2026-10-17T12:00:00Z");
      Dates.init({ locale: "fr-FR", timezone: "Asia/Kolkata" }); out.fr = [Dates.locale(), Dates.date("2026-10-17")];
      Dates.init({ locale: "en-IN", timezone: "Not/AZone" }); out.badzone = Dates.time("2026-10-17T09:35:00Z");   // process TZ is Asia/Kolkata
      Dates.init(); out.none = [Dates.locale(), Dates.zone()];
      Dates.init(null); Dates.init({}); out.ok = true;
      console.log(JSON.stringify(out));""")
    assert r["before"] == ["en-IN", "Asia/Kolkata"] and r["ny"] == "8:00 am"
    assert r["fr"] == ["en-IN", "17 Oct 2026"] and r["badzone"] == "3:05 pm" and r["none"] == ["en-IN", "Asia/Kolkata"] and r["ok"]


def test_init_reads_the_health_field_names_for_locale_and_zone():
    r = _node("""Dates.tables["zz-TEST"] = { months: Array(12).fill("Mo"), days: Array(7).fill("Da"), am: "AM", pm: "PM" };
      Dates.init({ date_locale: "zz-TEST", timezone: "UTC" }); const health = [Dates.locale(), Dates.date("2026-10-17"), Dates.time("2026-10-17T15:05:00Z")];
      Dates.init({ locale: "zz-TEST" }); const alias = Dates.locale();
      Dates.init({ date_locale: "en-IN" }); console.log(JSON.stringify([health, alias, Dates.date("2026-10-17")]));""")
    assert r == [["zz-TEST", "17 Mo 2026", "3:05 PM"], "zz-TEST", "17 Oct 2026"]


def test_the_page_zone_is_the_clinic_zone_not_the_browser_zone():
    for browser_tz in ("UTC", "America/Los_Angeles", "Asia/Kolkata"):
        r = _node("""Dates.init({ locale: "en-IN", timezone: "Asia/Kolkata" });
          console.log(JSON.stringify([Dates.dateTime("2026-10-17T18:45:00Z"), Dates.today(new Date("2026-10-16T19:00:00Z")), Dates.time("2026-10-17T09:35:00Z")]));""", tz=browser_tz)
        assert r == ["18 Oct 2026, 12:15 am", "17 Oct 2026", "3:05 pm"], browser_tz


def test_today_follows_the_clinic_day_across_midnight():
    r = _node("""const day = (iso) => Dates.today(new Date(iso));
      console.log(JSON.stringify([day("2026-10-16T18:29:00Z"), day("2026-10-16T18:30:00Z"), day("2026-12-31T20:00:00Z")]));""")
    assert r == ["16 Oct 2026", "17 Oct 2026", "1 Jan 2027"]


def test_health_re_defaults_the_sheet_date_only_while_it_still_shows_the_default():
    r = _node("""const now = new Date("2026-10-17T05:00:00Z"); const fresh = { textContent: Dates.today(now) }; const opened = { textContent: "3 Mar 2026" };
      Dates.initFrom({ date_locale: "en-IN", timezone: "Pacific/Auckland" }, fresh, now);       // the clinic day differs: the default follows it
      Dates.initFrom({ date_locale: "en-IN", timezone: "Asia/Kolkata" }, opened, now);          // a reopened document's own day is left alone
      Dates.initFrom(null, opened); Dates.initFrom({}, null);
      console.log(JSON.stringify({ fresh: fresh.textContent, opened: opened.textContent, zone: Dates.zone() }));""")
    assert r == {"fresh": "17 Oct 2026", "opened": "3 Mar 2026", "zone": "Asia/Kolkata"}


# --- wiring ------------------------------------------------------------------------------------------------------

def test_index_loads_dates_js_before_every_consumer_and_the_versions_moved():
    html = _read(FRONT / "index.html")
    assert html.count("dates.js?v=") == 1
    assert html.index("dates.js?v=") < html.index("sections.js?v=") < html.index("app.js?v=") < html.index("team.js?v=")
    pin = lambda n: int(re.search(re.escape(n) + r"\?v=(\d+)", html).group(1))     # noqa: E731
    assert pin("app.js") >= 36 and pin("sections.js") >= 3 and pin("team.js") >= 3 and pin("dates.js") >= 2


def test_the_page_has_no_other_date_formatting_left():
    app, team, sections = _code("app.js"), _code("team.js"), _code("sections.js")
    for name, src in (("app.js", app), ("team.js", team), ("sections.js", sections)):
        assert "toLocale" not in src, name
    assert "window.Dates.today()" in app and "window.Dates.time(" in app and "window.Dates.initFrom(" in app
    assert "window.Dates.dateTime(" in team and "window.Dates.label(" in sections
    assert "DAYS" not in sections and "MONTHS" not in sections                       # one table, in dates.js
    assert 'setText($("pDate"), state.visitDate ? window.Dates.date(state.visitDate) : today())' in app    # the open document's own day, else today


def test_the_sheet_date_is_read_only_and_has_no_editing_hook():
    html = _read(FRONT / "index.html")
    tag = re.search(r'<span[^>]*id="pDate"[^>]*>', html).group(0)
    assert "contenteditable" not in tag and 'aria-label="Visit date"' in tag and 'aria-readonly="true"' in tag
    app = _code("app.js")
    assert len(re.findall(r'\$\("pDate"\)', app)) == 4 and "pDate" not in _code("authorship.js")   # show, new patient, init, health: no read of what was typed
    assert not re.search(r'text\(\$\("pDate"\)\)', app) and 'inputVal("pDate")' not in app
    assert "visitDate" in app and "j.visit_date" in app


def test_team_timestamps_use_the_clinic_format_and_zone():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = ("const D = require(process.argv[1]); (async () => { const p = await D.open({role: 'admin', dates: {locale: 'en-IN', timezone: 'Asia/Kolkata'}, "
              "users: [{id: 5, username: 'a', display_name: 'A', is_active: true, last_login_at: '2026-10-17T09:35:00Z'}, "
              "{id: 6, username: 'b', display_name: 'B', is_active: true, last_login_at: 'garbage'}, {id: 7, username: 'c', display_name: 'C', is_active: true, last_login_at: null}], me: 0}); "
              "await p.openTeam(); console.log(JSON.stringify(p.body.descendants().filter((n) => n.tag === 'td').map((n) => n.textContent))); })()"
              ".catch((e) => { console.error(e); process.exit(1); });")
    out = subprocess.run([node, "-e", script, str(FAKEDOM), str(FRONT / "team.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    cells = json.loads(out.stdout)
    assert "17 Oct 2026, 3:05 pm" in cells and "garbage" in cells and "Never" in cells and "Invalid Date" not in cells


# --- deployment --------------------------------------------------------------------------------------------------

def test_dockerfile_and_compose_set_the_clinic_zone_and_ship_zone_data():
    docker = _read(ROOT / "Dockerfile")
    assert re.search(r"^ENV TZ=Asia/Kolkata$", docker, re.M)
    apt = [ln for ln in docker.splitlines() if "apt-get install" in ln][0]
    assert "tzdata" in apt and "fonts-noto-core" in apt                    # python:3.12-slim-bookworm may not ship zone data
    compose = _read(ROOT / "docker-compose.yml")
    app_block = compose.split("  app:")[1].split("  caddy:")[0]
    assert re.search(r"environment:\s*\n\s+TZ: Asia/Kolkata", app_block)
