from doctor_dictation.core import your_usual as U


def rx(name, strength="0.4 mg", dose="0-0-1", timing="At bedtime", duration="30 days", form="Tab."):
    return {"rx": [{"form": form, "name": name, "strength": strength, "dose": dose, "timing": timing, "duration": duration}]}


def test_usual_row_takes_each_field_by_the_d_sh2_rule():
    forms = [rx("Urimax"), rx("urimax"), rx("Urimax", duration="15 days")]
    row = U.usual_row("urimax", "Urimax", "Tamsulosin", 14, forms)
    assert row == U.UsualRow("Tab.", "Urimax", "0.4 mg", "0-0-1", "At bedtime", "30 days", "Tamsulosin", 14)


def test_a_field_without_a_60_percent_value_is_blank_and_no_usual_dose_means_no_row():
    split = [rx("Urimax", duration="30 days"), rx("Urimax", duration="15 days")]
    assert U.usual_row("urimax", "Urimax", "", 2, split).duration == ""
    assert U.usual_row("urimax", "Urimax", "", 2, [rx("Urimax", dose="1-0-0"), rx("Urimax", dose="0-0-1")]) is None
    assert U.usual_row("urimax", "Urimax", "", 2, [rx("Urimax", dose="2-2-2"), rx("Urimax", dose="2-2-2")]) is None   # not an allowed dose


def test_documents_without_the_medicine_or_unreadable_are_skipped():
    assert U.usual_row("urimax", "Urimax", "", 2, [rx("Dolo"), "not a dict", {"rx": "x"}, rx("Urimax")]) is None   # one row is under 2
    assert U.usual_row("urimax", "Urimax", "", 2, [rx("Urimax"), rx("Urimax")]).name == "Urimax"


def test_pick_dedupes_across_lines_and_caps_each_line():
    a = U.UsualRow("Tab.", "Urimax", "0.4 mg", "0-0-1", "", "", "", 14)
    b = U.UsualRow("Tab.", "Dolo", "650 mg", "1-0-1", "", "", "", 3)
    many = [U.UsualRow("Tab.", f"Med{i}", "", "1-0-0", "", "", "", 2) for i in range(7)]
    out = U.pick([(0, [a, b]), (1, [a] + many)])
    assert [g["line"] for g in out] == [0, 1]
    assert [i["name"] for i in out[0]["items"]] == ["Urimax", "Dolo"]
    assert "Urimax" not in [i["name"] for i in out[1]["items"]] and len(out[1]["items"]) == U.MAX_PER_LINE
    assert U.pick([(0, [])]) == []                                    # an empty line is not sent
