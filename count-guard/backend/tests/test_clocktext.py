import re

from app.journey.clocktext import when_text
from test_care_demo import H as _H, ORDERS, _client, _seed

H, M, DAY = _H, 60_000, 24 * _H


def ms(day=0, h=9, m=0):
    return day * DAY + (h - 9) * H + m * M


def test_same_day_is_just_the_time():
    assert when_text(ms(0, 9, 0), ms(0, 10, 0)) == "09:00"


def test_previous_day_says_yesterday():
    assert when_text(ms(0, 22, 10), ms(1, 9, 0)) == "Yesterday 22:10"


def test_older_is_a_dated_time():
    assert when_text(ms(day=2, h=9, m=14), ms(day=5, h=9)) == "Wed 4 Nov, 09:14"


def test_no_now_uses_the_full_date():
    assert when_text(ms(0, 9, 14), None) == "Mon 2 Nov, 09:14"


def test_after_midnight_rolls_the_day():
    assert when_text(ms(0, 9, 0) + 16 * H, None) == "Tue 3 Nov, 01:00"


DAY_N_TIME = re.compile(r"\bDay \d+ \d\d:\d\d")


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def test_view_has_no_day_n_text(tmp_path):
    """No product text carries 'Day N HH:MM'. A 'Day 3 check-in' line has no time after it, so it is allowed."""
    client = _client(tmp_path)
    views = [client.get(f"/journey/episodes/{p['id']}").json() for p in _seed(client)]
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    base = f"/journey/episodes/{eid}"
    client.post(f"{base}/orders", json={**ORDERS, "at_ms": 0})
    client.post(f"{base}/obs", json={"sbp": 120, "dbp": 80, "hr": 70, "by": "Nurse A", "at_ms": 0})
    client.post(f"{base}/handover", json={"from_nurse": "Nurse A", "to_nurse": "Nurse B", "at_ms": 30 * H})
    views.append(client.get(base).json())
    views.append(client.get(f"{base}/audit").json())
    assert views
    for view in views:
        bad = [text for text in _strings(view) if DAY_N_TIME.search(text)]
        assert bad == []
