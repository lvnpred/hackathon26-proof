from pathlib import Path

from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.vitals import VITAL_KEYS, coerce_vitals, extract_vitals, is_vitals_only, merge_vitals, same_reading
from template_fixtures import tclient  # noqa: F401

EMPTY = dict.fromkeys(VITAL_KEYS, "")


def test_extract_reads_each_vital():
    v = extract_vitals("BP 140/90, pulse 88, weight 72 kg, SpO2 98%, temperature 101 F. fever for 3 days")
    assert v == {"bp": "140/90", "pulse": "88/min", "weight": "72 kg", "spo2": "98%", "temp": "101 F"}
    assert extract_vitals("blood pressure 140 over 90, heart rate 88 per minute, temp 38.5 c")["bp"] == "140/90"
    assert extract_vitals("temp 38.5 c")["temp"] == "38.5 C" and extract_vitals("fever 5 days, 45 mm stone") == EMPTY


def test_extract_table_variants():
    assert extract_vitals("bp 140 by 90")["bp"] == "140/90"
    assert extract_vitals("pulse rate 88 per minute")["pulse"] == "88/min"
    assert extract_vitals("PR 88")["pulse"] == "88/min" and extract_vitals("heart rate 88")["pulse"] == "88/min"
    assert extract_vitals("wt 72.5")["weight"] == "72.5 kg" and extract_vitals("weight 72 kgs")["weight"] == "72 kg"
    assert extract_vitals("spo2 98 percent")["spo2"] == "98%" and extract_vitals("saturation 98")["spo2"] == "98%"
    assert extract_vitals("temp 101")["temp"] == "101" and extract_vitals("temperature 101 fever 3 days")["temp"] == "101"


def test_coerce_any_shape():                                  # Review Focus 1 and 5
    assert validate_structured({}, "")[0]["vitals"] == EMPTY
    for bad in (None, [], 7, "", {"bp": None, "x": "1"}, {"bp": {"a": 1}}, {"bp": [1]}, {"bp": True}):
        assert coerce_vitals(bad)[0] == EMPTY
    assert coerce_vitals({"pulse": 88, "bp": " 140 / 90 "})[0] == {**EMPTY, "pulse": "88/min", "bp": "140/90"}
    assert coerce_vitals("BP 140/90, pulse 88")[0] == {**EMPTY, "bp": "140/90", "pulse": "88/min"}
    v, w = coerce_vitals({"temp": "x" * 30})
    assert v["temp"] == "" and w == ["vitals.temp: ignored (unreadable or out of range)"]
    assert set(coerce_vitals({"bp": "1", "extra": "2"})[0]) == set(VITAL_KEYS)


def test_validate_survives_every_model_shape():
    for bad in (None, "BP 140/90", 5, [], {"bp": 1, "zz": 2}):
        out, _ = validate_structured({"vitals": bad}, "")
        assert set(out["vitals"]) == set(VITAL_KEYS)


def test_merge_keeps_unstated_vitals():
    assert merge_vitals({"bp": "140/90", "pulse": "88/min"}, {"bp": "130/80", "pulse": ""}) == {**EMPTY, "bp": "130/80", "pulse": "88/min"}
    assert merge_vitals(None, None) == EMPTY
    assert merge_vitals({"bp": "140/90"}, "garbage") == {**EMPTY, "bp": "140/90"}
    assert merge_vitals({"bp": "140/90"}, {"weight": "70 kg", "bp": "  "}) == {**EMPTY, "bp": "140/90", "weight": "70 kg"}


def test_vitals_only_and_same_reading():
    assert is_vitals_only("BP 140/90, pulse 88, weight 72 kg, SpO2 98%, temperature 101 F")
    assert not is_vitals_only("BP 140/90, fever for 3 days")
    assert not is_vitals_only("fever") and not is_vitals_only("")
    assert same_reading("88", "88/min") and not same_reading("140/90", "130/90") and not same_reading("", "")


def test_validate_reports_the_cut_and_save_keeps_vitals(tclient, monkeypatch):
    out, warnings = validate_structured({"vitals": {"bp": "140/90"}}, "")
    assert out["vitals"]["bp"] == "140/90" and not any("vitals" in w for w in warnings)

    def fake(structured, meta, out_path, layout=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    save = {"structured": {"patientName": "Anita", "vitals": {"bp": "140/90"}, "rx": []}, "confirmed_rows": []}
    doc = tclient.post("/api/v1/documents", json=save).json()["document_id"]
    got = tclient.get(f"/api/v1/documents/{doc}").json()
    assert got["structured"]["vitals"]["bp"] == "140/90"


def test_a_doubtful_unit_or_value_reads_as_empty():
    for text in ("weight 72 lbs", "weight 5 mg", "wt 10 mg daily", "weight 400 kg", "temp 3 days", "temp 101 c", "temp 60",
                 "pulse 88-92", "PR 88 mg", "pulse 300", "spo2 40", "bp 300/90", "bp 140/20"):
        assert extract_vitals(text) == EMPTY, text
    assert extract_vitals("temp 38.5 degree c")["temp"] == "38.5 C" and extract_vitals("temp 38.5 °C")["temp"] == "38.5 C"
    assert extract_vitals("temperature 98.6 degrees F")["temp"] == "98.6 F" and extract_vitals("pulse 88 and regular")["pulse"] == "88/min"


def test_the_last_mention_of_a_vital_wins():
    assert extract_vitals("bp 140/90 ... BP 130/80")["bp"] == "130/80"
    assert extract_vitals("weight 70 kg, correction weight 68 kg")["weight"] == "68 kg"


def test_coerce_rejects_markup_and_non_finite_values():
    v, w = coerce_vitals({"bp": "<b>x</b>", "pulse": float("nan"), "weight": 1e30, "temp": "1e+30", "spo2": "nan"})
    assert v == EMPTY and len(w) == 5
    assert coerce_vitals({"temp": "38.5 °C", "bp": "140/90", "spo2": "98%"})[0] == {**EMPTY, "temp": "38.5 C", "bp": "140/90", "spo2": "98%"}


def test_an_old_document_with_no_vitals_key_saves_and_reads_back_five_empty(tclient, monkeypatch):
    def fake(structured, meta, out_path, layout=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    doc = tclient.post("/api/v1/documents", json={"structured": {"patientName": "Old", "rx": []}, "confirmed_rows": []}).json()["document_id"]
    assert tclient.get(f"/api/v1/documents/{doc}").json()["structured"]["vitals"] == EMPTY


def test_the_model_path_is_range_checked_and_normalised():
    for bad in ({"pulse": "900"}, {"pulse": 900}, {"pulse": "300"}, {"spo2": "120"}, {"bp": "300/90"}, {"weight": "72 lbs"}, {"temp": "3"}, {"temp": "101 C"}):
        v, w = coerce_vitals(bad)
        assert v == EMPTY and len(w) == 1 and w[0].startswith("vitals."), bad
    kept = {"pulse": "88", "bp": "140/90", "temp": "101 F", "weight": "72", "spo2": "98 %"}
    assert coerce_vitals(kept) == ({"bp": "140/90", "pulse": "88/min", "weight": "72 kg", "spo2": "98%", "temp": "101 F"}, [])
    assert coerce_vitals({"temp": "38.5"})[0]["temp"] == "38.5" and coerce_vitals({"pulse": "88 bpm"})[0]["pulse"] == "88/min"
    assert coerce_vitals({"pulse": ""}) == (EMPTY, [])


def test_a_correction_patch_with_an_impossible_vital_does_not_land():
    assert merge_vitals({"pulse": "88/min"}, {"pulse": "900"}) == {**EMPTY, "pulse": "88/min"}
    assert merge_vitals({"pulse": "88/min"}, "pulse 900") == {**EMPTY, "pulse": "88/min"}
    assert merge_vitals({"pulse": "88/min"}, {"pulse": "92"}) == {**EMPTY, "pulse": "92/min"}


def test_units_are_accepted_after_the_number():
    assert coerce_vitals({"bp": "140/90 mmHg", "pulse": "88 bpm", "spo2": "98 percent", "temp": "38.5 °C", "weight": "72 kgs"})[0] == {
        "bp": "140/90", "pulse": "88/min", "spo2": "98%", "temp": "38.5 C", "weight": "72 kg"}
    assert coerce_vitals({"bp": "140/90 mm Hg", "pulse": "88 per min", "temp": "101 degrees F"})[0] == {**EMPTY, "bp": "140/90", "pulse": "88/min", "temp": "101 F"}


TYPED = {"pulse": "88 irregular", "bp": "150/100 sitting", "spo2": "900", "temp": "<b>1</b>", "weight": "72 kg"}


def test_typed_values_are_kept_but_the_model_path_stays_strict():
    kept, _ = coerce_vitals(TYPED, typed=True)
    assert kept == {"bp": "150/100 sitting", "pulse": "88 irregular", "weight": "72 kg", "spo2": "900", "temp": ""}
    assert coerce_vitals({"bp": "140/90 mmHg", "pulse": "900"}, typed=True)[0] == {**EMPTY, "bp": "140/90", "pulse": "900"}
    assert coerce_vitals({"pulse": "x" * 21}, typed=True)[0] == EMPTY
    strict, _ = coerce_vitals(TYPED)
    assert strict == {**EMPTY, "weight": "72 kg"}
    assert validate_structured({"vitals": TYPED}, "")[0]["vitals"] == strict
    assert validate_structured({"vitals": TYPED}, "", vitals_typed=True)[0]["vitals"] == kept


def test_save_route_keeps_what_the_doctor_typed(tclient, monkeypatch):
    def fake(structured, meta, out_path, layout=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    typed = {"pulse": "88 irregular", "bp": "150/100 sitting", "spo2": "900", "temp": "<b>1</b>", "weight": "72 kg"}
    doc = tclient.post("/api/v1/documents", json={"structured": {"patientName": "T", "vitals": typed, "rx": []}, "confirmed_rows": []}).json()["document_id"]
    assert tclient.get(f"/api/v1/documents/{doc}").json()["structured"]["vitals"] == {
        "bp": "150/100 sitting", "pulse": "88 irregular", "weight": "72 kg", "spo2": "900", "temp": ""}
    doc2 = tclient.post("/api/v1/documents", json={"structured": {"patientName": "T", "vitals": {"bp": "140/90 mmHg"}, "rx": []}, "confirmed_rows": []}).json()["document_id"]
    assert tclient.get(f"/api/v1/documents/{doc2}").json()["structured"]["vitals"]["bp"] == "140/90"


def test_rules_path_fills_vitals_and_drops_the_vitals_sentence():
    from doctor_dictation.core.determinism import normalize_transcript
    from doctor_dictation.core.fallback import fallback_format
    out = fallback_format(normalize_transcript("78 year old male. BP 140/90, pulse 88, weight 72 kg, SpO2 98%, "
                                               "temperature 101 F. fever for three days. tab dolo 650 mg twice daily"))
    assert out["vitals"] == {"bp": "140/90", "pulse": "88/min", "weight": "72 kg", "spo2": "98%", "temp": "101 F"}
    assert out["complaints"] == ["Fever for 3 days"]


def test_rules_path_keeps_a_mixed_sentence_whole_and_still_extracts_the_vital():
    from doctor_dictation.core.fallback import fallback_format
    out = fallback_format("BP 140/90, fever for 3 days")
    assert out["vitals"]["bp"] == "140/90"
    assert out["complaints"] and "fever" in out["complaints"][0].lower()
    assert fallback_format("")["vitals"] == {k: "" for k in ("bp", "pulse", "weight", "spo2", "temp")}


def test_rules_path_keeps_a_rejected_vitals_sentence_in_complaints():
    from doctor_dictation.core.fallback import fallback_format
    for text in ("BP 300/200", "pulse 5", "temperature 120 F"):
        out = fallback_format(text)
        assert out["complaints"], text
        assert all(v == "" for v in out["vitals"].values()), text
    out = fallback_format("BP 140/90")
    assert out["vitals"]["bp"] == "140/90" and not out["complaints"]


def test_merge_form_patches_one_vital():                                    # Review Focus 4
    from doctor_dictation.core.correction import merge_form
    cur = {"vitals": {"bp": "140/90", "pulse": "88/min"}, "complaints": ["Fever"]}
    out = merge_form(cur, {"vitals": {"bp": "130/80"}})
    assert out["vitals"]["bp"] == "130/80" and out["vitals"]["pulse"] == "88/min" and out["complaints"] == ["Fever"]
    assert merge_form(cur, {})["vitals"]["bp"] == "140/90"
    assert merge_form(cur, {"vitals": {"bp": "", "pulse": "900"}})["vitals"]["pulse"] == "88/min"
    assert cur["vitals"] == {"bp": "140/90", "pulse": "88/min"}  # never mutated


def test_correct_route_keeps_other_vitals(monkeypatch):
    from test_correction import _client, _stub_llm
    client = _client(monkeypatch)
    _stub_llm(monkeypatch, {"vitals": {"bp": "130/80"}})
    cur = {"vitals": {"bp": "140/90", "pulse": "88/min"}, "rx": []}
    r = client.post("/api/v1/correct", json={"transcript": "BP is now 130 by 80", "current_form": cur})
    j = r.json()
    assert r.status_code == 200
    assert j["structured"]["vitals"] == {"bp": "130/80", "pulse": "88/min", "weight": "", "spo2": "", "temp": ""}
    assert j["changed_rows"] == []


def _correct(monkeypatch, patch, cur):
    from test_correction import _client, _stub_llm
    client = _client(monkeypatch)
    _stub_llm(monkeypatch, patch)
    return client.post("/api/v1/correct", json={"transcript": "BP is now 130 by 80", "current_form": cur}).json()


def test_correct_keeps_typed_vital_it_was_not_asked_about(monkeypatch):
    cur = {"vitals": {"bp": "140/90", "pulse": "88 irregular"}, "rx": []}
    v = _correct(monkeypatch, {"vitals": {"bp": "130/80"}}, cur)["structured"]["vitals"]
    assert v["pulse"] == "88 irregular" and v["bp"] == "130/80"


def test_correct_patch_still_strict(monkeypatch):
    cur = {"vitals": {"bp": "140/90", "pulse": "88 irregular"}, "rx": []}
    v = _correct(monkeypatch, {"vitals": {"pulse": "900"}}, cur)["structured"]["vitals"]
    assert v["pulse"] == "88 irregular" and v["bp"] == "140/90"


def test_format_ai_vitals_stay_strict():
    assert validate_structured({"vitals": {"pulse": "900"}}, "")[0]["vitals"]["pulse"] == ""
