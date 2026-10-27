"""SAM token parser, voice turns, and the sentence check."""

from __future__ import annotations

from app.adapters.sam import concept_request, parse_sam_text, read_sse_text
from app.adapters.spark import normalize_second_look, second_look_prompt
from app.adapters.voice import parse_voice_payload
from app.agent.reconciler import explain_case
from app.agent.verifier import check_sentence, template_sentence
from app.config import Settings
from app.engine import Engine
from app.scenarios import get_scenario
from app.store import Store

SAMPLE = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
    ",1<|box;x1=155;y1=228;x2=202;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,48,~!!!!J!0c[q=Pj_zs=*4C4(/./x#:/`S_GnD`=o3?X{emCgO$y@|>"
)


def test_parse_sam_line_keeps_object_ids():
    records = parse_sam_text(SAMPLE)
    assert [record["object_id"] for record in records] == ["0", "1"]
    assert records[0]["frame_index"] == 0
    assert records[0]["bbox"][0] == 211 / 320
    assert "mask" in records[0]["mask_token"]


def test_one_concept_per_sam_request():
    body = concept_request("lap sponge", file_id="file-abc")
    text = body["input"][0]["content"][0]["text"]
    assert text == "lap sponge"
    assert "," not in text


def test_sse_delta_joins():
    lines = [
        'data: {"type":"response.output_text.delta","delta":"<0f>"}',
        'data: {"type":"response.output_text.delta","delta":"0"}',
        "data: [DONE]",
    ]
    assert read_sse_text(lines) == "<0f>0"


def test_voice_uses_turn_times_not_words():
    turns = parse_voice_payload(
        {
            "transcript": "Adding 10 lap sponges",
            "turns": [{"turnId": 1, "startMs": 400, "endMs": 1800, "transcript": "Adding 10 lap sponges"}],
        },
        offset_ms=10_000,
    )
    assert turns == [{"text": "Adding 10 lap sponges", "t0_ms": 10400, "t1_ms": 11800}]


def test_second_look_stays_a_name():
    assert "should" not in second_look_prompt("lap sponge").lower()
    assert normalize_second_look("It is a gauze swab, I think") == "gauze swab"
    assert normalize_second_look("You should re-explore") == "unknown"


def test_advice_sentence_is_rejected_and_template_is_not(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        meta_api_key="",
        meta_base="https://api.meta.ai/v1",
        sam_model="sam-3.1",
        voice_model="muse-voice-transcribe-1.0",
        spark_model="muse-spark-1.3",
        baseten_api_key="",
        spark_open_base="https://inference.baseten.co/v1",
        spark_open_model="meta-models/muse-spark-open-1026",
        low_confidence=0.45,
        unannounced_window_ms=30_000,
        lost_after_frames=4,
        sam_fps=2,
    )
    store = Store(tmp_path / "db.sqlite")
    app = Engine(store, settings)
    scenario = get_scenario("clip2")
    case = app.create_case("clip2", scenario["item_types"])
    app.replay(case["id"], scenario)
    explained = explain_case(store, settings, case["id"])
    assert explained["model"] == "template"
    assert "x-ray" not in explained["narrative"].lower()
    for row in explained["sentences"]:
        errors = check_sentence(
            row["text"],
            evidence_ids=row["evidence_ids"],
            known_ids=store.known_evidence_ids(case["id"]) | set(row["evidence_ids"]),
            figures=_figures(store, case["id"], row["discrepancy_id"]),
            claims=row["claims"],
        )
        assert errors == [], row
    bad = check_sentence(
        "You should order an X-ray and re-explore.",
        evidence_ids=[],
        known_ids=set(),
        figures={"expected": 1, "observed": 0},
        claims={"expected": 1, "observed": 0},
    )
    assert "advice wording" in bad


def test_spark_tool_loop_accepts_a_grounded_sentence(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        meta_api_key="",
        meta_base="https://api.meta.ai/v1",
        sam_model="sam-3.1",
        voice_model="muse-voice-transcribe-1.0",
        spark_model="muse-spark-1.3",
        baseten_api_key="",
        spark_open_base="https://inference.baseten.co/v1",
        spark_open_model="meta-models/muse-spark-open-1026",
        low_confidence=0.45,
        unannounced_window_ms=30_000,
        lost_after_frames=4,
        sam_fps=2,
    )
    store = Store(tmp_path / "db.sqlite")
    app = Engine(store, settings)
    scenario = get_scenario("clip4")
    case = app.create_case("clip4", scenario["item_types"])
    result = app.replay(case["id"], scenario)
    row = next(item for item in result["discrepancies"] if item["rule_id"] == "R4")
    calls = {"n": 0}

    def complete(messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "get_ledger", "arguments": "{}"},
                    }
                ],
            }
        sentence = template_sentence(row)
        return {
            "role": "assistant",
            "content": json_sentence(sentence),
        }

    explained = explain_case(store, settings, case["id"], complete=complete)
    assert calls["n"] >= 2
    assert explained["trace"][0]["tool"] == "get_ledger"
    assert explained["sentences"][0]["source"] == "muse-spark-open"


def _figures(store: Store, case_id: str, discrepancy_id: str) -> dict:
    for event in store.events(case_id):
        if event["id"] == discrepancy_id:
            return event["payload"].get("figures") or {}
    return {}


def json_sentence(sentence: dict) -> str:
    import json

    return json.dumps({"sentences": [sentence]})
