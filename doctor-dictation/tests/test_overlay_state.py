"""core/overlay_state.py: request activation and effective_view (plan PQ-f, Task 3)."""
import asyncio
import contextvars

import pytest

from doctor_dictation.core import overlay as O

SHIPPED = [
    {"canonical": "Aceclofenac", "aliases": ["aceclofenac"], "brands": ["Zerodol"], "forms": ["Tab."], "strengths": ["100 mg"]},
    {"canonical": "Paracetamol", "aliases": ["paracetamol"], "brands": ["Crocin", "Dolo"], "forms": [], "strengths": ["650 mg"], "safety": True},
]


def row(key, action, data, base_sha=""):
    return {"entry_key": key, "action": action, "data": data, "base_sha": base_sha}

def mrow(key, action, data, base_sha="", kind="medicine"):
    return {"kind": kind, **row(key, action, data, base_sha)}


ADD = {"name": "Zedex", "generic": "Aceclofenac"}


@pytest.fixture
def clean_state():
    yield
    O.activate(O.OverlayState())


def test_effective_view_is_the_shipped_list_itself_without_rows(clean_state):
    assert O.effective_view("medicine", SHIPPED) is SHIPPED
    O.activate(O.state_from_rows([mrow("x", "add", ADD, kind="investigation")]))
    assert O.effective_view("medicine", SHIPPED) is SHIPPED


def test_effective_view_is_one_object_per_version(clean_state):
    O.activate(O.state_from_rows([mrow("zedex", "add", ADD)]))
    first = O.effective_view("medicine", SHIPPED)
    assert first is not SHIPPED and O.effective_view("medicine", SHIPPED) is first
    O.activate(O.state_from_rows([mrow("zedex", "add", ADD)]))          # same content, another state object
    assert O.effective_view("medicine", SHIPPED) is first
    O.activate(O.state_from_rows([mrow("zedex", "add", ADD), mrow("zyx", "add", {"name": "Zyx", "generic": "Aceclofenac"})]))
    assert O.effective_view("medicine", SHIPPED) is not first
    other = list(SHIPPED)
    assert O.effective_view("medicine", other) is not first             # another shipped list is another key


def test_effective_view_matches_effective_entries(clean_state):
    rows = [mrow("zedex", "add", ADD)]
    O.activate(O.state_from_rows(rows))
    assert O.effective_view("medicine", SHIPPED) == O.effective_entries("medicine", SHIPPED, rows)[0]


def test_effective_view_holds_at_most_32_slots(clean_state):
    O.activate(O.state_from_rows([mrow("zedex", "add", ADD)]))
    lists = [list(SHIPPED) for _ in range(40)]
    for s in lists:
        O.effective_view("medicine", s)
    assert len(O._views) <= 32
    O.effective_view("medicine", lists[-1])
    assert O.effective_view("medicine", lists[-1]) is O.effective_view("medicine", lists[-1])


def test_version_is_0_when_empty_and_changes_with_any_field():
    assert O.state_from_rows([]).version == "0" and O.OverlayState().version == "0"
    base = mrow("zedex", "edit", {"aliases": ["a"]}, "sha1")
    versions = {O.state_from_rows([base]).version}
    for changed in (mrow("zedey", "edit", {"aliases": ["a"]}, "sha1"), mrow("zedex", "add", {"aliases": ["a"]}, "sha1"),
                    mrow("zedex", "edit", {"aliases": ["b"]}, "sha1"), mrow("zedex", "edit", {"aliases": ["a"]}, "sha2"),
                    mrow("zedex", "edit", {"aliases": ["a"]}, "sha1", kind="investigation")):
        versions.add(O.state_from_rows([changed]).version)
    assert len(versions) == 6 and all(len(v) == 64 for v in versions)
    a, b = mrow("a", "hide", {}), mrow("b", "hide", {})
    assert O.state_from_rows([a, b]).version == O.state_from_rows([b, a]).version


def test_rows_for_filters_by_kind():
    st = O.state_from_rows([mrow("a", "hide", {}), mrow("b", "hide", {}, kind="investigation")])
    assert [r["entry_key"] for r in st.rows_for("medicine")] == ["a"]
    assert [r["entry_key"] for r in st.rows_for("investigation")] == ["b"]


def test_state_follows_asyncio_to_thread(clean_state):
    O.activate(O.state_from_rows([mrow("zedex", "add", ADD)]))

    async def go():
        return await asyncio.to_thread(lambda: O.active().version)
    assert asyncio.run(go()) == O.active().version != "0"


def test_two_contexts_see_their_own_view(clean_state):
    a = O.state_from_rows([mrow("zedex", "add", ADD)])
    seen = {}

    def run(name, state):
        O.activate(state)
        seen[name] = O.effective_view("medicine", SHIPPED)
    contextvars.copy_context().run(run, "a", a)
    contextvars.copy_context().run(run, "none", O.OverlayState())
    assert seen["none"] is SHIPPED and seen["a"] is not SHIPPED
    assert O.active().version == "0"                                    # the outer context never saw either


def test_shipped_of_an_unregistered_kind_is_empty():
    assert O.shipped("zzz") == []


def test_register_shipped_uses_the_loader():
    lst = [{"canonical": "CBC"}]
    old = O._loaders.get("investigation")
    try:
        O.register_shipped("investigation", lambda: lst)
        assert O.shipped("investigation") is lst
    finally:
        O._loaders.pop("investigation", None)
        if old:
            O._loaders["investigation"] = old


def test_two_non_empty_overlays_never_share_a_view(clean_state):
    a = O.state_from_rows([mrow("zedex", "add", {"name": "Zedex", "generic": "Aceclofenac"})])
    b = O.state_from_rows([mrow("zyqa", "add", {"name": "Zyqa", "generic": "Aceclofenac"})])
    seen = {}

    def run(name, state):
        O.activate(state)
        seen[name] = O.effective_view("medicine", SHIPPED)
    contextvars.copy_context().run(run, "a", a)
    contextvars.copy_context().run(run, "b", b)
    names = lambda v: {n for e in v for n in e.get("brands", []) + e.get("aliases", [])}
    assert "Zedex" in names(seen["a"]) and "Zyqa" not in names(seen["a"])
    assert "Zyqa" in names(seen["b"]) and "Zedex" not in names(seen["b"])
    assert seen["a"] is not seen["b"]


def test_a_hit_refreshes_its_slot(clean_state):
    O.activate(O.state_from_rows([mrow("zedex", "add", ADD)]))
    lists = [list(SHIPPED) for _ in range(32)]
    first = O.effective_view("medicine", lists[0])
    for s in lists[1:]:
        O.effective_view("medicine", s)
    assert O.effective_view("medicine", lists[0]) is first          # now the newest
    O.effective_view("medicine", list(SHIPPED))                     # evicts the oldest: lists[1]
    assert O.effective_view("medicine", lists[0]) is first


def test_rows_are_copied(clean_state):
    r = mrow("zedex", "add", ADD)
    st = O.state_from_rows([r])
    r["action"] = "hide"
    assert st.rows[0]["action"] == "add"
