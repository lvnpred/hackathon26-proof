"""validate_layout: the vocabulary gate between a (possibly LLM-written) layout and the renderer."""
import copy

import pytest

from doctor_dictation.pdf import DEFAULT_LAYOUT, LayoutError, validate_layout

GOOD = {"header": [{"type": "logo", "crop": [0.05, 0.02, 0.2, 0.1]}, {"type": "text", "field": "doctor_name", "color": "#1a3c6e"},
                   {"type": "text", "text": "Open 9 to 5"}, {"type": "rule"}],
        "footer": [{"type": "text", "field": "address", "role": "small", "align": "center"}],
        "body": {"top": 0.22, "bottom": 0.92}, "profile": {"doctor_name": "Dr. A. Rao"}}

def test_valid_layout_is_normalised_with_defaults_filled():
    layout = validate_layout(GOOD)
    assert layout.body_top == 0.22 and layout.profile["address"] == "" and layout.header[2]["align"] == "left"
    assert DEFAULT_LAYOUT.header[0]["field"] == "doctor_name"

@pytest.mark.parametrize("change", [
    lambda r: r["header"].append({"type": "html", "html": "<b>x</b>"}),
    lambda r: r["header"][0].update(crop=[0.1, 0.1, 1.2, 0.5]),
    lambda r: r["body"].update(top=0.9, bottom=0.5),
    lambda r: r["body"].update(bottom=True),
    lambda r: r["body"].update(top=0, bottom=0.02),      # ~291 mm bottom margin
    lambda r: r["body"].update(top=0.98, bottom=1),       # page one blank
    lambda r: r["body"].update(top=0.6, bottom=0.9),
    lambda r: r["body"].update(top=0.1, bottom=0.4),
    lambda r: r["header"][1].update(color="red"),
    lambda r: r["header"][3].update(color="#fff;background:url(x)"),
    lambda r: r["header"][2].update(text="x" * 201),
    lambda r: r["header"][1].update(text="both"),
    lambda r: r["header"].extend([{"type": "rule"}] * 12),
    lambda r: r["footer"].append({"type": "logo", "crop": [0, 0, 1, 1]}),
    lambda r: r["profile"].update(phone="9" * 601),
])
def test_invalid_layouts_raise(change):
    raw = copy.deepcopy(GOOD)
    change(raw)
    with pytest.raises(LayoutError):
        validate_layout(raw)


def test_default_and_good_body_ranges_and_the_edges_are_accepted():
    assert validate_layout(GOOD).body_bottom == 0.92 and DEFAULT_LAYOUT.body_top == 0.18
    for top, bottom in ((0, 0.5), (0.5, 1), (0, 1)):
        raw = copy.deepcopy(GOOD)
        raw["body"] = {"top": top, "bottom": bottom}
        assert validate_layout(raw).body_top == top
