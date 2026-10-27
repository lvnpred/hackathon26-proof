"""Hand-written demo drug map. About twenty names. Not a formulary."""

from __future__ import annotations

# generic -> class. Aliases point at the generic.
_GENERICS: dict[str, str] = {
    "metoprolol": "beta-blocker",
    "amlodipine": "calcium-channel blocker",
    "lignocaine": "local anaesthetic",
    "bupivacaine": "local anaesthetic",
    "propofol": "anaesthetic",
    "fentanyl": "opioid",
    "morphine": "opioid",
    "ondansetron": "antiemetic",
    "ceftriaxone": "antibiotic",
    "paracetamol": "analgesic",
    "pantoprazole": "proton-pump inhibitor",
    "atorvastatin": "statin",
    "aspirin": "antiplatelet",
    "insulin": "antidiabetic",
    "salbutamol": "bronchodilator",
    "midazolam": "benzodiazepine",
    "ketamine": "anaesthetic",
    "atropine": "anticholinergic",
    "heparin": "anticoagulant",
    "dexamethasone": "steroid",
}

ALIASES = {
    "lidocaine": "lignocaine",
    "xylocaine": "lignocaine",
}


def ground(name: str) -> dict:
    key = " ".join(name.lower().split())
    generic = ALIASES.get(key, key)
    drug_class = _GENERICS.get(generic)
    if drug_class is None:
        return {"grounded": False, "generic": None, "drug_class": None, "as_heard": name.strip()}
    return {"grounded": True, "generic": generic, "drug_class": drug_class, "as_heard": name.strip()}


def known_names() -> list[str]:
    return sorted(set(_GENERICS) | set(ALIASES))
