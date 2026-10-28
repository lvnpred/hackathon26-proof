"""One cleaner for typed free text (names, qualifications, addresses) before it is stored or printed."""
import re
import unicodedata

# Format characters that hide or reorder text; U+200C/U+200D are NOT listed: Indic scripts need them.
_DELETE = {0x200B, 0xFEFF, *range(0x202A, 0x202F), *range(0x2066, 0x206A)}
_SPACE = {"Cc", "Zl", "Zp"}


def clean_text(value) -> str:
    """Control and line/paragraph separators become spaces, hidden format characters are deleted, runs of
    spaces collapse and the ends are trimmed. Anything that is not a string gives ''."""
    if not isinstance(value, str):
        return ""
    out = "".join(" " if unicodedata.category(ch) in _SPACE else ch for ch in value if ord(ch) not in _DELETE)
    return re.sub(r" {2,}", " ", out).strip()
