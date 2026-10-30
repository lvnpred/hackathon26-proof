"""Photo regions: SAM finds the boxes, Spark reads the values, and this module pairs them (D1(b)). Pure."""

from __future__ import annotations

from app.morning.strips import parse_strip_text

# R14: the SAM concepts that find the region of each reader. Change here to change what SAM looks for.
READER_CONCEPTS = {"strip": ["blister strip"], "monitor": ["digital display"]}
MONITOR_LABELS = (("sbp", "SBP"), ("dbp", "DBP"), ("hr", "HR"))
ROW_BAND = 0.05


def strips_from(text: str) -> list[dict]:
    """Grounded strips from a reader's text. A reply that does not parse gives no strips."""
    try:
        return parse_strip_text(text)
    except (ValueError, KeyError, TypeError, AttributeError):
        return []


def pair_regions(boxes: list[dict], values: list[dict]) -> list[dict]:
    """Zip boxes (top to bottom, then left to right) with the values in reading order.

    A box with no value gets `label`, `value` and `row` None. A value with no box gets `bbox` None."""
    ordered = sorted(boxes, key=lambda b: (round(b["bbox"][1] / ROW_BAND), b["bbox"][0]))
    out = []
    for i in range(max(len(ordered), len(values))):
        box = ordered[i]["bbox"] if i < len(ordered) else None
        value = values[i] if i < len(values) else None
        out.append({
            "bbox": box,
            "label": value["label"] if value else None,
            "value": value["value"] if value else None,
            "row": i if value else None,
        })
    return out


def monitor_values(read: dict) -> list[dict]:
    """Always three, in reading order: SBP, DBP, HR. A number not read has value None."""
    return [{"label": label, "value": str(read[key]) if key in read else None} for key, label in MONITOR_LABELS]


def strip_values(strips: list[dict]) -> list[dict]:
    """One value per strip in read order: its name and strength."""
    out = []
    for s in strips:
        text = f"{s['name_as_read']} {s['strength']}".strip()
        out.append({"label": text, "value": text})
    return out
