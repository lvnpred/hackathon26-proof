"""Spec 9.3: names belong in doctor fields or the doctors block; the review screen warns on doctor-like lines."""
import json

from doctor_dictation.templates import builder, doctors
from template_fixtures import GOOD_LAYOUT, make_jpeg, tclient  # noqa: F401


def test_prompt_routes_names_to_doctor_fields_and_offers_the_doctors_block():
    text = builder.VISION_SYSTEM
    assert '{"type": "doctors"' in text and '"doctor_hints"' in text
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
