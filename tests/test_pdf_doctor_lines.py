"""Several doctors in one profile print as one block per doctor, one field per line, nothing truncated. Pure HTML."""
import re

from doctor_dictation.pdf import build_sheet_html, validate_layout
from doctor_dictation.pdf.doctors_text import block, doctor_groups, group_lines

FORM, META = {"patientName": "Anita"}, {"date": "2026-10-15", "opNo": "OP-1", "patientName": "Anita"}
NAME, QUALS, REG = ("Dr. L. GOWRISANKAR; Dr. VIDYA GOWRISANKAR", "M.S., M.Ch. (AIIMS); M.D., D.G.O.", "82233; 82232")
TWO = {"doctor_name": NAME, "qualifications": QUALS, "reg_no": REG, "clinic_name": "Gowri Clinic",
       "phone": "040 1", "address": "1 Lake Road"}
CELLS = [("Dr. L. GOWRISANKAR", ", M.S., M.Ch. (AIIMS)", "Reg. No: 82233"),
         ("Dr. VIDYA GOWRISANKAR", ", M.D., D.G.O.", "Reg. No: 82232")]


def _cells(html, table_class):
    """(name, qualifications, reg line) of every cell of the doctors table, rows kept: [[cell, cell], ...]."""
    table = html.split(f'<table class="{table_class}"')[1].split("</table>")[0]
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", table):
        row = []
        for td in re.findall(r"<td>(.*?)</td>", tr):
            first = re.findall(r"<span[^>]*>([^<]*)</span>", td)
            reg = re.findall(r"<div[^>]*>(Reg\. No: [^<]*)</div>", td)
            row.append((first[0] if first else "", first[1] if len(first) > 1 else "", reg[0] if reg else ""))
        rows.append(row)
    return rows


def _layout(header=None, footer=None):
    return validate_layout({"header": header or [], "footer": footer or [], "body": {"top": 0.22, "bottom": 0.92},
                            "profile": {}})


FIELDS = [{"type": "text", "field": "doctor_name", "role": "title", "align": "center"},
          {"type": "text", "field": "qualifications", "role": "small", "align": "center"},
          {"type": "text", "field": "reg_no", "role": "small", "align": "center"}]


def test_helper_on_the_users_example_and_the_edge_cases():
    groups = doctor_groups(NAME, QUALS, REG)
    assert [group_lines(g) for g in groups] == [["Dr. L. GOWRISANKAR, M.S., M.Ch. (AIIMS)", "Reg. No: 82233"],
                                                ["Dr. VIDYA GOWRISANKAR, M.D., D.G.O.", "Reg. No: 82232"]]
    assert [block(g) for g in groups] == [("Dr. L. GOWRISANKAR", "M.S., M.Ch. (AIIMS)", "Reg. No: 82233"),
                                          ("Dr. VIDYA GOWRISANKAR", "M.D., D.G.O.", "Reg. No: 82232")]
    assert doctor_groups("Dr A", "MBBS, MD", "TS-1") == [("Dr A", "MBBS, MD", "TS-1")]       # one doctor
    assert doctor_groups("A; B", "qa", "") == [("A", "qa", ""), ("B", "", "")]               # fewer parts: later lines out
    assert group_lines(("B", "", "")) == ["B"] and block(("B", "", "")) == ("B", "", "")
    assert doctor_groups("A", "qa; qb", "") == [("A", "qa", ""), ("", "qb", "")]             # extra parts: extra doctors
    assert doctor_groups("", None, "  ;; ") == [] and doctor_groups(5, [], {}) == []


def test_empty_middle_parts_are_kept_so_the_pairing_holds():
    assert doctor_groups("A; B", " ; MD", "1; 2") == [("A", "", "1"), ("B", "MD", "2")]
    assert doctor_groups("A; ; C", "", "1; ; 3") == [("A", "", "1"), ("C", "", "3")]      # an all-empty doctor is skipped
    assert doctor_groups("; B", "", "") == [("B", "", "")]


def test_default_header_order_is_clinic_address_phone_rule_then_the_doctors_table():
    html = build_sheet_html(FORM, {**META, "profile": TWO})
    head = html.split('<div class="clinic-head">')[1].split("<h1>")[0]
    order = [head.index(m) for m in ('class="clinic-name">Gowri Clinic', 'class="clinic-addr">1 Lake Road',
                                     'class="clinic-meta">Ph: 040 1', '<hr class="clinic-rule">', '<table class="clinic-doctors"')]
    assert order == sorted(order) and "None" not in html
    assert _cells(html, "clinic-doctors") == [list(CELLS)]
    assert head.count("<td>") == 2 and head.count("<tr>") == 1


def test_three_doctors_fill_row_by_row_and_an_odd_row_keeps_two_cells():
    p = {"doctor_name": "A; B; C", "qualifications": "qa; qb; qc", "reg_no": "1; 2; 3"}
    rows = _cells(build_sheet_html(FORM, {**META, "profile": p}), "clinic-doctors")
    assert [[c[0] for c in r] for r in rows] == [["A", "B"], ["C", ""]]
    assert rows[1][1] == ("", "", "")


def test_one_doctor_default_header_is_one_cell_with_two_lines():
    html = build_sheet_html(FORM, {**META, "profile": {"doctor_name": "Dr A", "qualifications": "MBBS", "reg_no": "TS-1"}})
    assert _cells(html, "clinic-doctors") == [[("Dr A", ", MBBS", "Reg. No: TS-1"), ("", "", "")]]
    assert '<hr class="clinic-rule">' not in html                                           # nothing above to separate from


def test_letterhead_field_blocks_collapse_into_one_table_for_several_doctors():
    html = build_sheet_html(FORM, {**META, "profile": TWO}, _layout(FIELDS))
    body = html.split('<div class="lh">')[1].split("<h1>")[0]
    assert body.count('<table class="lh-doctors"') == 1 and body.count("<td>") == 2
    assert _cells(html, "lh-doctors") == [list(CELLS)] and "font-size:20px;font-weight:700" in body   # first block's role


def test_letterhead_with_one_doctor_keeps_each_field_block():
    html = build_sheet_html(FORM, {**META, "profile": {"doctor_name": "Dr A", "qualifications": "MBBS", "reg_no": "TS-1"}},
                            _layout(FIELDS))
    assert 'class="lh-doctors"' not in html and html.count("text-align:center;font-size") == 3


def test_footer_cannot_hold_a_table_so_doctors_stack_two_lines_each():
    html = build_sheet_html(FORM, {**META, "profile": TWO}, _layout(footer=FIELDS))
    assert ('@bottom-center { content:"Dr. L. GOWRISANKAR, M.S., M.Ch. (AIIMS)\\A Reg. No: 82233\\A \\A '
            'Dr. VIDYA GOWRISANKAR, M.D., D.G.O.\\A Reg. No: 82232"') in html


def test_hostile_text_is_escaped_in_both_sinks_after_splitting():
    evil = {"doctor_name": 'A</style>"; B\\22 x', "qualifications": "q1; <b>q2</b>", "reg_no": "r\n1; r2"}
    html = build_sheet_html(FORM, {**META, "profile": evil}, _layout(FIELDS, FIELDS))
    assert html.count("</style>") == 1 and "<b>" not in html and "&lt;b&gt;q2&lt;/b&gt;" in html     # HTML sink
    footer = html.split("@bottom-center")[1].split("}")[0]                                          # CSS sink
    assert "\\3c " in footer and "\\22 " in footer and "\\5c " in footer and "<" not in footer
    assert footer.count('"') == 2                                                                   # only the content quotes


def test_nothing_is_truncated_for_a_long_list_of_long_names():
    names = [f"Dr {c} " + c * 94 for c in "abcd"]                                         # 4 doctors, 100-char names
    quals = [f"MBBS {c}" * 20 for c in "abcd"]
    profile = {"doctor_name": "; ".join(names), "qualifications": "; ".join(quals), "reg_no": "1; 2; 3; 4"}
    for kwargs in ({"header": FIELDS}, {"footer": FIELDS}, {"header": [{"type": "doctors", "role": "normal"}]}):
        html = build_sheet_html(FORM, {**META, "profile": profile}, _layout(**kwargs))
        assert all(n in html for n in names) and all(q in html for q in quals)
    assert all(n in build_sheet_html(FORM, {**META, "profile": profile}) for n in names)


def test_doctors_block_is_the_same_two_column_table_untruncated():
    long = {"name": "Dr " + "n" * 150, "qualifications": "q" * 200, "reg_no": "r" * 80}
    lay = _layout(header=[{"type": "doctors", "role": "normal"}], footer=[{"type": "doctors", "role": "small"}])
    html = build_sheet_html(FORM, {**META, "doctors": [long, TWO_DOCS[0], TWO_DOCS[1]]}, lay)
    rows = _cells(html, "lh-doctors")
    assert rows[0][0] == (long["name"], ", " + long["qualifications"], "Reg. No: " + long["reg_no"])
    assert [c[0] for r in rows for c in r] == [long["name"], "Dr. A. Rao", "Dr. S. Mehta", ""]    # row by row, odd row padded
    assert (long["name"] + ", " + long["qualifications"] + "\\A Reg. No: " + long["reg_no"]) in html   # footer: stacked


TWO_DOCS = [{"name": "Dr. A. Rao", "qualifications": "MBBS", "reg_no": "TS-1"},
            {"name": "Dr. S. Mehta", "qualifications": "DNB", "reg_no": ""}]
