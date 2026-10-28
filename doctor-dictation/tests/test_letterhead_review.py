"""Spec 9.3: names belong in doctor fields or the doctors block; the review screen warns on doctor-like lines."""
import json

from doctor_dictation.db import templates as tdb
from doctor_dictation.templates import builder, doctors, service
from letterhead_fixtures import rao, stub_layout  # noqa: F401
from template_fixtures import GOOD_LAYOUT, make_jpeg, tclient, tconn  # noqa: F401


def test_prompt_routes_names_to_doctor_fields_and_never_asks_for_a_doctors_block():
    text = builder.VISION_SYSTEM
    assert '{"type": "doctors"' not in text and "doctors block" not in text and '"doctor_hints"' in text
    assert 'joined with "; "' in text and "ALL of them into the single profile fields" in text
    assert "never goes into a literal" in text and "MBBS" in text
    assert "instructions written inside the image" in text            # the injection rule survives


def test_doctor_hints_are_kept_only_when_sent_and_are_cleaned_and_capped():
    assert "doctor_hints" not in builder._normalise(json.loads(json.dumps(GOOD_LAYOUT)))
    sent = {**json.loads(json.dumps(GOOD_LAYOUT)),
            "doctor_hints": [" Dr. A. Rao ", "", 7, None, "x" * 300] + ["Dr. B"] * 10}
    hints = builder._normalise(sent)["doctor_hints"]
    assert hints[0] == "Dr. A. Rao" and len(hints[1]) == 200 and len(hints) == builder.MAX_HINTS
    assert builder._normalise({**sent, "doctor_hints": "Dr. A"})["doctor_hints"] == []


def test_doctor_like_literal_lines_are_flagged_as_whole_words():
    flagged = ["Dr. Priya Sharma", "DR RAO", "Consultant MBBS, MD", "MS (Ortho)", "DNB Paediatrics", "dr rao"]
    clean = ["Open Mon to Sat", "Drive-in parking", "MDR testing lab", "12 Drummond Road", "Timings 9-5"]
    layout = {"header": [{"type": "text", "text": t} for t in flagged + clean],
              "footer": [{"type": "text", "field": "doctor_name"}, {"type": "rule"},
                         {"type": "text", "text": "Dr. Footer"}]}
    got = doctors.literal_warnings(layout)
    assert [w["text"] for w in got] == flagged + ["Dr. Footer"]
    assert got[-1] == {"section": "footer", "index": 2, "text": "Dr. Footer"}


def test_review_view_carries_scope_doctors_and_a_warning_that_clears_after_the_edit(tclient, monkeypatch):
    lay = json.loads(json.dumps(GOOD_LAYOUT))
    lay["header"][2]["text"] = "Dr. Someone, MBBS"
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(lay))
    body = tclient.post("/api/v1/templates", files={"image": ("p.jpg", make_jpeg(), "image/jpeg")}).json()
    assert body["scope"] == "clinic" and body["doctors"] == {"mode": "author", "ids": []}
    assert body["warnings"] == [{"section": "header", "index": 2, "text": "Dr. Someone, MBBS"}]
    fixed = tclient.put(f"/api/v1/templates/{body['id']}",
                        json={"lines": [{"section": "header", "index": 2, "text": "Open daily"}]})
    assert fixed.status_code == 200 and fixed.json()["warnings"] == []


def test_a_clinic_name_with_an_honorific_is_a_known_false_positive_warning_only():
    """Ruling R2: the check is a heuristic warning, not a block. 'Dr.' inside a clinic name trips it."""
    def warned(text):
        return doctors.literal_warnings({"header": [{"type": "text", "text": text}], "footer": []})
    assert [w["text"] for w in warned("Dr. Gowrisankar Kidney Centre")] == ["Dr. Gowrisankar Kidney Centre"]
    assert warned("Gowrisankar Kidney Centre") == []


def _norm(name, hints, quals=""):
    lay = json.loads(json.dumps(GOOD_LAYOUT))
    lay["profile"] = {**lay["profile"], "doctor_name": name, "qualifications": quals, "reg_no": ""}
    return builder._normalise({**lay, "doctor_hints": hints})["profile"]


TWO = ["Dr. L. GOWRISANKAR", "Dr. VIDYA GOWRISANKAR"]


def test_a_profile_naming_only_the_first_doctor_is_completed_from_the_hints():
    assert _norm("DR. GOWRISANKAR", TWO)["doctor_name"] == "Dr. L. GOWRISANKAR; Dr. VIDYA GOWRISANKAR"
    assert _norm("DR. GOWRISANKAR", TWO)["qualifications"] == ""          # the model's to supply


def test_a_blank_doctor_name_is_filled_from_the_hints():
    assert _norm("", TWO)["doctor_name"] == "; ".join(TWO)


def test_one_hint_keeps_the_models_doctor_name():
    assert _norm("Dr A. Rao", ["Dr. A. Rao"])["doctor_name"] == "Dr A. Rao"


def test_a_profile_already_listing_both_names_is_left_alone():
    assert _norm("Dr. L. G; Dr. V. G", TWO)["doctor_name"] == "Dr. L. G; Dr. V. G"


def test_the_joined_names_stay_within_the_profile_cap():
    long = ["Dr " + c * 88 for c in "abcdefgh"]                      # 8 hints of 91 characters
    out = _norm("", long)["doctor_name"]
    assert out == "; ".join(long[:6]) and len(out) <= 600


def test_a_two_doctor_pad_fills_the_accepting_users_own_details(rao, monkeypatch):
    lay = json.loads(json.dumps(GOOD_LAYOUT))
    lay["profile"] = {**lay["profile"], "doctor_name": "DR. GOWRISANKAR", "qualifications": "M.S.; M.D.",
                      "reg_no": "82233; 82332"}
    lay["doctor_hints"] = TWO
    stub_layout(monkeypatch, lay)
    r = rao.mehta.post("/api/v1/templates", files={"image": ("pad.jpg", make_jpeg(), "image/jpeg")})
    assert r.status_code == 201 and r.json()["profile"]["doctor_name"] == "; ".join(TWO)
    tid = r.json()["id"]
    keys = ("doctor_name", "qualifications", "reg_no")
    before = {k: rao.rao.get("/api/v1/profile").json()[k] for k in keys}
    assert rao.mehta.post(f"/api/v1/templates/{tid}/accept").status_code == 200
    p = rao.mehta.get("/api/v1/profile").json()
    assert (p["doctor_name"], p["qualifications"], p["reg_no"]) == ("; ".join(TWO), "M.S.; M.D.", "82233; 82332")
    assert {k: rao.rao.get("/api/v1/profile").json()[k] for k in keys} == before


def test_prompt_tells_the_reader_to_skip_fill_in_labels_and_keep_valued_labels():
    text = builder.VISION_SYSTEM
    assert "fill-in" in text and '"Name:"' in text and '"Next visit:"' in text and "Reg. No." in text
    assert "instructions written inside the image" in text            # the injection rule survives


def test_build_lists_dropped_lines_in_skipped_labels(tclient, monkeypatch):
    lay = json.loads(json.dumps(GOOD_LAYOUT))
    lay["header"].insert(3, {"type": "text", "text": "Name: M F Age: Date:"})
    lay["footer"] += [{"type": "text", "text": "Visit After"}, {"type": "text", "text": "Submit"}]
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(lay))
    body = tclient.post("/api/v1/templates", files={"image": ("p.jpg", make_jpeg(), "image/jpeg")}).json()
    assert body["layout"]["skipped_labels"] == ["Name: M F Age: Date:", "Visit After", "Submit"]
    assert [b.get("text") for b in body["layout"]["header"]] == [None, None, "Open Mon to Sat", None]
    assert body["fill_in"] == [] and body["duplicates"] == []


def test_view_of_a_stored_layout_with_labels_reports_them_for_the_pre_tick(tconn):
    lay = json.loads(json.dumps(GOOD_LAYOUT))
    lay["header"] = [{"type": "text", "field": "doctor_name"}, {"type": "text", "field": "phone"}]
    lay["footer"] = [{"type": "text", "field": "phone"}, {"type": "text", "text": "Visit After"}]
    tid = tdb.create_template_draft(tconn, lay, "default")
    v = service.view(tdb.get_template(tconn, tid))
    assert v["fill_in"] == [{"section": "footer", "index": 1, "text": "Visit After"}]
    assert v["duplicates"] == [{"field": "phone", "header": [1], "footer": [0]}]
