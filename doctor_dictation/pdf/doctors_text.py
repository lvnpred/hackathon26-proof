"""Several doctors in one profile: 'A; B' names, 'qualsA; qualsB' qualifications, 'regA; regB' registration numbers.

One pure helper for every renderer (default header, letterhead header and footer, doctors block). Doctor i takes
part i of each field; a field with fewer parts leaves that doctor's line out; text is never moved between doctors.
"""


def parts(value) -> list:
    """``value`` split on ';', each part stripped. Empty parts are KEPT so doctor i keeps part i of every field
    ('A; B' with ' ; MD' pairs B with MD). Blank or non-text values give []."""
    return [p.strip() for p in value.split(";")] if isinstance(value, str) and value.strip() else []


def doctor_groups(name, qualifications, reg_no) -> list:
    """``(name, qualifications, reg_no)`` per doctor, "" where a field has no part for that doctor. The longest field
    decides how many doctors there are; a doctor whose three parts are all empty is skipped."""
    cols = [parts(name), parts(qualifications), parts(reg_no)]
    groups = [tuple(c[i] if i < len(c) else "" for c in cols) for i in range(max(map(len, cols)))]
    return [g for g in groups if any(g)]


def block(group) -> tuple:
    """One doctor as ``(name, qualifications, reg_line)``: line 1 is the name followed by the qualifications on the
    same line, line 2 is 'Reg. No: x' (blank when there is no registration number)."""
    name, quals, reg = group
    return name, quals, f"Reg. No: {reg}" if reg else ""


def group_lines(group) -> list:
    """The printed lines of one doctor as plain text (the footer, which cannot hold a table): at most two."""
    name, quals, reg_line = block(group)
    return [ln for ln in (", ".join(t for t in (name, quals) if t), reg_line) if ln]
