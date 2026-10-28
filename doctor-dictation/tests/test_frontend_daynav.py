"""Browse earlier days in the Today list (UI-A Task 2), page side. frontend/daynav.js and frontend/dates.js run under node on
a tiny fake DOM (only the navigator's elements); the app.js and index.html wiring is checked as text."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"

_DOM = r"""
class El {
  constructor(id) { this.id = id; this.hidden = false; this.disabled = false; this.textContent = ""; this.value = ""; this.max = ""; this.handlers = {}; this.focused = false; }
  addEventListener(t, f) { (this.handlers[t] = this.handlers[t] || []).push(f); }
  fire(t) { (this.handlers[t] || []).forEach((f) => f({ type: t, target: this })); }
  focus() { this.focused = true; }
}
const ids = {}; ["dayPrev", "dayTitle", "dayPick", "dayInput", "dayNext", "dayToday"].forEach((id) => { ids[id] = new El(id); });
globalThis.window = globalThis;
globalThis.document = { getElementById: (id) => ids[id] || null };
"""


def _run(body, tz="Asia/Kolkata"):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = (_DOM + f"require({json.dumps(str(FRONT / 'dates.js'))}); require({json.dumps(str(FRONT / 'daynav.js'))});\n"
              "Dates.todayIso = () => \"2026-10-13\";\n"
              "let listDay = \"\"; const went = []; DayNav.init({ day: () => listDay, go: (d) => { went.push(d); listDay = d; } });\n"
              "const view = () => ({ title: ids.dayTitle.textContent, next: ids.dayNext.disabled, back: !ids.dayToday.hidden, max: ids.dayInput.max });\n"
              + body)
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, env={**os.environ, "TZ": tz})
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def test_dates_gives_the_clinic_zone_iso_day_and_a_short_label():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    js = ("globalThis.window = globalThis; require(process.argv[1]);"
          'const t = new Date("2026-10-12T19:00:00Z");'                      # 00:30 IST on the 13th; UTC says the 12th
          'Dates.init({ timezone: "Asia/Kolkata" }); const ist = Dates.todayIso(t);'
          'Dates.init({ timezone: "America/New_York" }); const ny = Dates.todayIso(t);'
          'console.log(JSON.stringify([ist, ny, Dates.short("2026-10-20"), Dates.short("2026-02-30"), Dates.short("")]));')
    out = subprocess.run([node, "-e", js, str(FRONT / "dates.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == ["2026-10-13", "2026-10-12", "Tue, 20 Oct", "", ""]


def test_today_shows_today_with_next_disabled_and_no_back_link():
    r = _run("console.log(JSON.stringify(view()));")
    assert r == {"title": "Today", "next": True, "back": False, "max": "2026-10-13"}


def test_prev_next_and_back_to_today_move_the_listed_day():
    r = _run("""const out = [];
      ids.dayPrev.fire("click"); out.push(view());
      ids.dayPrev.fire("click"); out.push(view());
      ids.dayNext.fire("click"); out.push(view());
      ids.dayToday.fire("click"); out.push(view());
      console.log(JSON.stringify({ went, out }));""")
    assert r["went"] == ["2026-10-12", "2026-10-11", "2026-10-12", ""]
    assert [v["title"] for v in r["out"]] == ["Mon, 12 Oct", "Sun, 11 Oct", "Mon, 12 Oct", "Today"]
    assert [(v["next"], v["back"]) for v in r["out"]] == [(False, True), (False, True), (False, True), (True, False)]


def test_next_from_yesterday_returns_to_today_and_never_goes_past_it():
    r = _run("""listDay = "2026-10-12"; DayNav.render(); ids.dayNext.fire("click"); const a = view();
      ids.dayNext.fire("click");                                                 // disabled on today: nothing moves
      console.log(JSON.stringify({ went, a }));""")
    assert r["went"][0] == "" and r["a"]["title"] == "Today" and all(d == "" for d in r["went"])


def test_the_calendar_picks_a_day_and_a_future_or_bad_pick_means_today():
    r = _run("""ids.dayPick.fire("click"); const focused = ids.dayInput.focused;            // no showPicker here: focus
      let picked = 0; ids.dayInput.showPicker = () => { picked++; }; ids.dayPick.fire("click");
      ids.dayInput.focused = false; ids.dayInput.showPicker = () => { throw new Error("NotAllowedError"); }; ids.dayPick.fire("click");
      const fellBack = ids.dayInput.focused;
      ids.dayInput.value = "2026-09-30"; ids.dayInput.fire("change"); const a = view().title;
      ids.dayInput.value = "2026-10-20"; ids.dayInput.fire("change");
      ids.dayInput.value = "garbage"; ids.dayInput.fire("change");
      ids.dayInput.value = "2026-10-13"; ids.dayInput.fire("change");
      console.log(JSON.stringify({ focused, picked, fellBack, a, went }));""")
    assert r["focused"] is True and r["picked"] == 1 and r["fellBack"] is True and r["a"] == "Wed, 30 Sep"
    assert r["went"] == ["2026-09-30", "", "", ""]


def test_the_query_adds_the_date_only_for_an_earlier_day():
    r = _run("""console.log(JSON.stringify([DayNav.url("/t", "?scope=mine", ""), DayNav.url("/t", "?scope=clinic", "2026-10-12"),
      DayNav.url("/t", "", "2026-10-12"), DayNav.url("/t", "", "")]));""")
    assert r == ["/t?scope=mine", "/t?scope=clinic&date=2026-10-12", "/t?date=2026-10-12", "/t"]


def test_the_empty_text_names_the_day():
    r = _run('console.log(JSON.stringify([DayNav.emptyText(""), DayNav.emptyText("2026-10-12")]));')
    assert r == ["No patients completed yet today.", "No prescriptions on 12 Oct 2026."]


def _function(js, name):
    start = js.index(f"function {name}(")
    return js[start:js.index("\n}\n", start)]


def test_index_has_the_day_navigator_with_labels():
    html = _read("index.html")
    aside = html.split('<aside id="today"')[1].split("</aside>")[0]
    assert 'aria-label="Prescriptions by day"' in html.split('<aside id="today"')[1].split(">")[0]
    for i in ("dayPrev", "dayTitle", "dayPick", "dayNext", "dayToday"):
        tag = re.search(r'<[^>]*id="' + i + r'"[^>]*>', aside).group(0)
        assert i == "dayTitle" or "aria-label=" in tag, tag
    tag = re.search(r'<input[^>]*id="dayInput"[^>]*>', aside).group(0)
    assert 'type="date"' in tag and "aria-label=" in tag and 'class="day-input"' in tag     # visually hidden: showPicker needs it rendered
    assert "Back to today" in aside and aside.index('id="dayToday"') and 'id="todayList"' in aside
    assert html.index("dates.js?v=") < html.index("daynav.js?v=") < html.index("app.js?v=")


def test_app_js_lists_the_chosen_day_and_returns_to_today():
    js = _read("app.js")
    assert 'listDay: ""' in js
    load = _function(js, "loadToday")
    assert "DayNav.url(" in load and "state.listDay" in load and "window.DayNav" in load
    assert "DayNav.emptyText(state.listDay)" in _function(js, "renderToday")
    save = _function(js, "saveDocument")
    assert save.index("const wasNew = state.documentId == null") < save.index("if (wasNew) state.listDay = \"\"") < save.index("loadToday();")
    assert "backToToday()" in _function(js, "resetSheet")
    assert re.search(r"DayNav\.init\(\{ day: \(\) => state\.listDay, go: ", js)
