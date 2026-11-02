"""Every remaining write route, called with a valid body and a person's name, cannot close the swab count (R17, A6).

Bodies are built from each route's OpenAPI request schema: the required fields plus the optional ones in HINTS, valid
values, a person's name in every `by`, no extra keys. A route on another id is tried with every event id the stay has.
Only `POST .../count` may write a person's `count.closing`; it is the one route skipped. The 2xx set is pinned.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.journey.correction import CORRECTABLE
from app.journey.stories import by_ai
from tests.test_count_gate import NOT_ADDING_UP, SAVE_FIRST, _begun
from tests.test_flow_states import _count, _surgery

APP = Path(__file__).resolve().parents[1] / "app"
PERSON = "Sister M. Thomas (synthetic)"
COUNT_ROUTE = "/journey/episodes/{episode_id}/count"
# Fields that need a real-looking value, and optional fields a route needs one of ("send text or a name").
HINTS = {"name": "L. Rao (synthetic)", "text": "closing count twenty swabs, all back", "scenario": "demo",
         "age_sex": "40 F", "reason": "Lump"}
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
       b"\x00\x0cIDAT\x08\xd7c\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82")
E = "/journey/episodes/{episode_id}"
# Pinned: the 39 write routes that accept the built body on this stay. Among them every count-adjacent route:
# camera case, clip, manual, replay, dwell, close, advice ack and resolve, heard drug and pack confirm.
ACCEPTED = {
    "/journey/episodes", f"{E}/rx/demo", f"{E}/orders", f"{E}/strips", f"{E}/reminders", f"{E}/dose", f"{E}/obs",
    f"{E}/tick", f"{E}/handover", f"{E}/discharge-card", f"{E}/help", f"{E}/checkin", f"{E}/camera/case",
    f"{E}/camera/clip", f"{E}/camera/manual", f"{E}/camera/replay", f"{E}/camera/dwell", f"{E}/camera/close",
    f"{E}/theatre/drug", f"{E}/theatre/vitals/step", f"{E}/theatre/tier", "/journey/demo/seed", "/journey/clock",
    "/journey/intake", "/journey/patients", "/journey/sync", f"{E}/photos", f"{E}/ask/bot", f"{E}/ask/doctor",
    "/journey/ops/pause", "/journey/ops/resume", f"{E}/nudges/{{nudge_id}}/seen",
    f"{E}/handover/{{handover_id}}/accept", f"{E}/camera/advice/{{advice_id}}/ack",
    f"{E}/camera/advice/{{advice_id}}/resolve", f"{E}/theatre/drug/{{draft_id}}/confirm",
    f"{E}/theatre/pack/{{draft_id}}/confirm", f"{E}/questions/{{question_id}}/answer",
    f"{E}/checkins/{{checkin_id}}/seen",
}
# Refused here, and why. A stay in surgery: ward, clinic and discharge steps are 409. No reachable id: tasks, orders,
# reviews, medicine reads, ops work, check items, models. Others need inputs a generic body cannot give (a DD on
# port 9, an audio file, a 12-hour board window, a strip photo with text, a video). The correct route is swept
# separately below with every event id this stay has.
REFUSED_HERE = {
    f"{E}/rx/import", f"{E}/correct", f"{E}/bed", f"{E}/state", f"{E}/surgery", f"{E}/orders/sign",
    f"{E}/discharge/sign", f"{E}/discharge/draft", f"{E}/dictate/orders", f"{E}/dictate/discharge",
    f"{E}/dictate/task", f"{E}/strips/photo", f"{E}/ask/hear", f"{E}/ask/review", f"{E}/ask/medicines",
    "/journey/staff/doctor", f"{E}/video", f"{E}/orders/{{order_id}}/ack", f"{E}/tasks/{{task_id}}/begin",
    f"{E}/tasks/{{task_id}}/done", f"{E}/checks/{{item}}/photo", f"{E}/checks/{{item}}/override",
    f"{E}/reviews/{{review_id}}/answer", f"{E}/medicines/{{read_id}}/mark", "/journey/ai/try/{model}",
    f"{E}/ops/work/{{work_id}}/undo", f"{E}/ops/work/{{work_id}}/approve", f"{E}/ops/work/{{work_id}}/reject",
}


def _resolve(schema: dict, spec: dict) -> dict:
    while "$ref" in schema:
        schema = spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [s for s in schema[key] if s.get("type") != "null"]
            return _resolve(options[0], spec)
    if "allOf" in schema:
        return _resolve(schema["allOf"][0], spec)
    return schema


def _value(name: str, schema: dict, spec: dict):
    schema = _resolve(schema, spec)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if name == "by" or name.endswith("_by"):
        return PERSON
    kind = schema.get("type")
    if schema.get("format") == "binary" or "contentMediaType" in schema:
        return PNG
    if name in HINTS and kind in ("string", None):
        return HINTS[name]
    if kind == "string":
        text = "Synthetic, X"
        return text[: schema.get("maxLength", len(text))].ljust(schema.get("minLength", 0), "x")
    if kind in ("integer", "number"):
        low = schema.get("minimum", schema.get("exclusiveMinimum", -1) + 1)
        value = min(max(low, 0), schema.get("maximum", max(low, 0)))
        return int(value) if kind == "integer" else value
    if kind == "boolean":
        return True
    if kind == "array":
        return [_value(name, schema.get("items", {}), spec) for _ in range(max(schema.get("minItems", 0), 1 if name == "files" else 0))]
    if kind == "object":
        return _fill(schema, spec)
    return "x"


def _fill(schema: dict, spec: dict) -> dict:
    schema = _resolve(schema, spec)
    props = schema.get("properties", {})
    wanted = [n for n in props if n in schema.get("required", []) or n in HINTS]
    return {name: _value(name, props[name], spec) for name in wanted}


def _request(client, method: str, path: str, op: dict, spec: dict):
    content = op.get("requestBody", {}).get("content", {})
    if "application/json" in content:
        return client.request(method, path, json=_fill(content["application/json"]["schema"], spec))
    if "multipart/form-data" in content:
        body = _fill(content["multipart/form-data"]["schema"], spec)
        files = [(k, ("photo.png", v, "image/png")) for k, v in body.items() if isinstance(v, bytes)]
        files += [(k, ("photo.png", f, "image/png")) for k, v in body.items() if isinstance(v, list) for f in v]
        data = {k: v for k, v in body.items() if not isinstance(v, (bytes, list))}
        return client.request(method, path, data=data, files=files)
    return client.request(method, path)


def _write_ops(spec: dict):
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if method.upper() in ("POST", "PUT", "PATCH", "DELETE") and path != COUNT_ROUTE:
                yield method.upper(), path, op


def test_no_write_route_but_count_closes_the_count_for_a_person(tmp_path):
    client, eid = _begun(tmp_path)
    _count(client, eid, "opened", quantity=20)
    heard = client.post(f"/journey/episodes/{eid}/theatre/drug", data={"by": PERSON, "text": "opening twenty swabs"})
    assert heard.status_code == 200, heard.text  # a heard pack, so the pack-confirm route has a draft to confirm
    spec = client.app.openapi()
    events = client.app.state.morning.events
    ok, refused, needs_id = [], [], []
    for method, path, op in _write_ops(spec):
        if [p for p in re.findall(r"\{([a-z_]+)\}", path) if p != "episode_id"]:
            needs_id.append((method, path, op))
            continue
        r = _request(client, method, path.replace("{episode_id}", eid), op, spec)
        (ok if r.status_code < 300 else refused).append((path, r.status_code, r.text[:160]))
    # A route on a draft, advice, nudge or check-in (or the correct route's event_id): try every id this stay has.
    for method, path, op in needs_id:
        tried = [_request(client, method, re.sub(r"\{[a-z_]+\}", e["id"], path.replace("{episode_id}", eid)), op, spec)
                 for e in events(eid)]
        (ok if any(r.status_code < 300 for r in tried) else refused).append((path, tried[-1].status_code, ""))
    for e in events(eid):
        body = {"event_id": e["id"], "payload": dict(e["payload"]), "by": PERSON, "at_ms": 0}
        r = client.post(f"/journey/episodes/{eid}/correct", json=body)
        assert r.status_code >= 300 or e["event_type"] in CORRECTABLE, (e["event_type"], r.text)
    closings = [e for e in events(eid) if e["event_type"] == "count.closing"]
    assert not [e for e in closings if str(e["payload"].get("by") or "").strip() and not by_ai(e["payload"])], closings
    r = _surgery(client, eid, "ended")
    assert r.status_code == 409 and r.json()["detail"] in (SAVE_FIRST, NOT_ADDING_UP)
    assert len(ok) == len(ACCEPTED), sorted(p for p, *_ in ok)
    assert {p for p, *_ in ok} == ACCEPTED
    assert {p for p, *_ in refused} == REFUSED_HERE, refused


def _closing_names(trees) -> set[str]:
    """Names bound to the literal "count.closing" anywhere in app/ (CLOSING = ..., A, B = ..., ...)."""
    names = set()
    for tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                pairs = zip(target.elts, node.value.elts) if isinstance(target, ast.Tuple) and isinstance(
                    node.value, ast.Tuple) else [(target, node.value)]
                for name, value in pairs:
                    if isinstance(name, ast.Name) and isinstance(value, ast.Constant) and value.value == "count.closing":
                        names.add(name.id)
    return names


def _is_closing(node, names: set[str]) -> bool:
    return ((isinstance(node, ast.Constant) and node.value == "count.closing")
            or (isinstance(node, ast.Name) and node.id in names)
            or (isinstance(node, ast.Attribute) and node.attr in names))


def test_only_the_count_route_writes_a_person_closing():
    """Static: every write of `count.closing` (a literal, a constant bound to it, positional or `event_type=`/`kind=`)
    is in count_api (a person's `by`) or in the replay builder count_rules, whose closing carries no `by`."""
    trees = {p: ast.parse(p.read_text(encoding="utf8")) for p in APP.rglob("*.py")}
    names = _closing_names(trees.values())
    writers: dict[str, list[int]] = {}
    for path, tree in trees.items():
        rel = path.relative_to(APP.parent).as_posix()
        for call in [n for n in ast.walk(tree) if isinstance(n, ast.Call)]:
            func = getattr(call.func, "attr", getattr(call.func, "id", ""))
            args = call.args[:3] + [k.value for k in call.keywords if k.arg in ("event_type", "kind")]
            if func in ("append", "_act") and any(_is_closing(a, names) for a in args):
                writers.setdefault(rel, []).append(call.lineno)
        for d in [n for n in ast.walk(tree) if isinstance(n, ast.Dict)]:
            pairs = {k.value: v for k, v in zip(d.keys, d.values) if isinstance(k, ast.Constant)}
            if "event_type" in pairs and _is_closing(pairs["event_type"], names):
                payload = pairs.get("payload")
                assert not (isinstance(payload, ast.Dict) and "by" in [getattr(k, "value", None) for k in payload.keys]), rel
                writers.setdefault(rel, []).append(d.lineno)
    assert set(writers) == {"app/journey/count_api.py", "app/morning/count_rules.py"}, writers


def test_static_scan_sees_a_constant_and_a_keyword():
    tree = ast.parse('CLOSING = "count.closing"\nA, B = "x", "count.closing"\nstore.append(eid, event_type=B, payload={})\n')
    names = _closing_names([tree])
    assert names == {"CLOSING", "B"}
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert _is_closing(call.keywords[0].value, names)
