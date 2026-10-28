"""Import gate (plan I1-g simple, Task 5): ordinary clinical sentences are not rewritten into brand names.

Runs on the LIVE lexicon (no frozen copy), so run it after a real import and refuse to commit the import if it fails.
A one-slip ordinary word ("garden" -> "Arden", "epigastrium" -> "Gastrium") must stay as dictated. Offline."""
import pytest

from doctor_dictation.core.determinism import normalize_transcript

# The words the review measured as rewritten after the first import, in a sentence each.
REVIEWED = [
    "epigastric tenderness and epigastrium pain after meals",
    "echo shows dilated left atrium",
    "limited range of movement in the shoulder",
    "ventral hernia noted on examination",
    "scar of 6 mm diameter on the forearm",
    "blister on the right heel",
    "works in the garden, allergic rhinitis",
    "skin grafting done last year",
    "he accepted the proposal for surgery",
    "family rumor of diabetes",
    "singular episode of chest pain",
    "twice daily after food",
    "Tab Paracetamol 650 mg twice daily after food",
    "take once daily after food for 5 days",
    "take thrice daily before food",
]
ORDINARY = [
    "patient complains of fever for 3 days with body ache",
    "chest pain since morning, radiating to left arm",
    "take once at night before sleeping",
    "take on empty stomach early morning",
    "follow up after 5 days with reports",
    "avoid oily and spicy food",
    "drink warm water and take steam inhalation",
    "gargle with warm salt water thrice daily",
    "apply the cream locally twice a day",
    "stop if rash or itching appears",
    "dry cough worse at night",
    "loose motions 4 times since yesterday",
    "burning micturition for 2 days",
    "pain abdomen after meals",
    "acidity and bloating after dinner",
    "knee pain while climbing stairs",
    "lower back pain since lifting weight",
    "giddiness on standing up suddenly",
    "breathlessness on exertion",
    "swelling of both feet in the evening",
    "loss of appetite and weight loss",
    "red eyes with watering since yesterday",
    "ear pain and discharge from right ear",
    "sore throat with difficulty in swallowing",
    "runny nose and sneezing in the morning",
    "chest is clear on auscultation",
    "abdomen soft and non tender",
    "no pallor no icterus no cyanosis",
    "advised complete blood count and urine routine",
    "advised chest x ray and ECG",
    "advised ultrasound abdomen",
    "echocardiogram shows mild mitral regurgitation",
    "mitral valve prolapse seen on echo",
    "aortic stenosis with calcified valve",
    "right atrium and right ventricle normal in size",
    "inguinal hernia repair planned next month",
    "umbilical hernia reducible and non tender",
    "gastric ulcer healed on endoscopy",
    "gastritis with antral erosions",
    "colonoscopy showed sigmoid diverticulosis",
    "appendectomy done 10 years ago",
    "cholecystectomy for gallstones",
    "skin graft taken from the thigh",
    "bone grafting after the fracture",
    "wound dressing changed daily",
    "blisters on both palms",
    "fluid filled blister over the shin",
    "eczema on the elbow and behind the knee",
    "allergic rhinitis with sneezing",
    "chronic sinusitis with post nasal drip",
    "bronchial asthma with wheeze",
    "singular finding on x ray chest",
    "limited mouth opening",
    "limited neck movement",
    "diameter of the wound is about 2 cm",
    "pupils equal and reactive",
    "tonsils enlarged with exudate",
    "thyroid gland not palpable",
    "lymph nodes not enlarged",
    "liver and spleen not palpable",
    "bowel sounds present",
    "reflexes are brisk and symmetrical",
    "power is full in all 4 limbs",
    "gait is normal",
    "plantar response flexor on both sides",
    "fundus examination is normal",
    "hearing is normal on tuning fork test",
    "family history of hypertension",
    "no history of drug allergy",
    "history of appendicitis in childhood",
    "garden work worsens the cough",
    "ardent desire to quit smoking",
    "proposal of surgery was discussed with the family",
    "rumor of fever in the village",
    "garden soil exposure and rash on the hands",
    "advised rest and plenty of oral fluids",
    "avoid heavy lifting for 6 weeks",
    "review with reports after 1 week",
    "keep the wound clean and dry",
    "do not skip meals",
    "walk for 30 minutes every day",
    "reduce salt intake",
    "continue the same medicines for 1 month",
    "come back if the swelling increases",
    "sugar fasting and post prandial tomorrow",
    "get HbA1c done next visit",
    "blood pressure is well controlled",
]
KNOWN_PRE_EXISTING = {"take calcium supplements after lunch": "take Calcium Carbonate supplements after lunch"}   # before any import
SENTENCES = [(s, s) for s in [*REVIEWED, *ORDINARY]] + list(KNOWN_PRE_EXISTING.items())


def test_the_list_has_at_least_eighty_sentences():
    assert len(SENTENCES) >= 80 and len({s for s, _ in SENTENCES}) == len(SENTENCES)


@pytest.mark.parametrize("text,expected", SENTENCES)
def test_ordinary_sentences_are_not_rewritten_on_the_live_lexicon(text, expected):
    assert normalize_transcript(text) == expected


def test_format_of_works_in_the_garden_gives_no_arden_row(monkeypatch, tmp_path):
    """Offline /api/format, rules path: the phantom row 'Arden' (verified, Paracetamol) must not appear."""
    from test_determinism import _client
    client = _client(monkeypatch)
    resp = client.post("/api/format", json={"transcript": "works in the garden, allergic rhinitis"})
    assert resp.status_code == 200
    names = [row["name"] for row in resp.json()["structured"]["rx"]]
    assert "Arden" not in names and not any("arden" in n.lower() for n in names)
