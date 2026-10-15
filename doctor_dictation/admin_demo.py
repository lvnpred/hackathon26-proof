"""``seed-demo``: two fake clinics for the multi-clinic demo (spec sections 11 and 13.2). Demo only.

Rao Clinic (Dr. Rao, Dr. Mehta) and Iyer Clinic (Dr. Iyer) each get clinic details, a few fake patients with
prescriptions saved today (so each clinic has its own "document 1") and an active letterhead: Rao Clinic's
shared pad lists every doctor, Iyer Clinic's prints only the author.

The doctors get FIXED, published passwords with no forced change, so the five-minute demo and
``scripts/demo_browser.py`` sign in repeatably. That is acceptable only because the command refuses unless
``DEMO_MODE=1``, refuses a data folder that already has a clinic (it can never add known-password accounts to a
real installation), and every record is fake.
"""
from __future__ import annotations

import hashlib
import io
import os
from contextlib import closing

from PIL import Image

from doctor_dictation import accounts, clinics
from doctor_dictation import scope as scopemod
from doctor_dictation import db as dbmod
from doctor_dictation.db import details, opno
from doctor_dictation.db import templates as tdb
from doctor_dictation.directory import list_clinics, open_directory
from doctor_dictation.directory.logins import lookup_username
from doctor_dictation.scope import Scope, clinic_dir, data_root, use_scope

DEMO_ENV = "DEMO_MODE"
ACTOR = "seed-demo"
RAO_PAD_LINE = "Open Mon to Sat, 9 am to 1 pm"
IYER_PAD_LINE = "ENT and allergy care, open daily 10 am to 6 pm"

CLINICS = (
    {"slug": "rao", "name": "Rao Clinic", "op_prefix": "RAO", "address": "12 MG Road, Hyderabad",
     "phone": "040 1111 2222", "logo_rgb": (26, 60, 110), "logo_size": (240, 80), "doctors_mode": "all"},
    {"slug": "iyer", "name": "Iyer Clinic", "op_prefix": "IYER", "address": "4 Temple Street, Chennai",
     "phone": "044 3333 4444", "logo_rgb": (11, 110, 79), "logo_size": (200, 90), "doctors_mode": "author"},
)
DOCTORS = (
    {"clinic": "rao", "username": "dr.rao", "password": "demo-rao-pass-1", "display_name": "Dr. Rao",
     "doctor_name": "Dr. A. Rao", "qualifications": "MBBS, MD (General Medicine)", "reg_no": "TSMC 10001"},
    {"clinic": "rao", "username": "dr.mehta", "password": "demo-mehta-pass-1", "display_name": "Dr. Mehta",
     "doctor_name": "Dr. S. Mehta", "qualifications": "MBBS, DCH (Paediatrics)", "reg_no": "TSMC 10002"},
    {"clinic": "iyer", "username": "dr.iyer", "password": "demo-iyer-pass-1", "display_name": "Dr. Iyer",
     "doctor_name": "Dr. K. Iyer", "qualifications": "MBBS, MS (ENT)", "reg_no": "TNMC 20001"},
)
# (clinic, author, patient, age / sex, diagnosis, medicines). Per clinic, the first row becomes document 1.
PRESCRIPTIONS = (
    ("rao", "dr.rao", "Asha Verma", "34 / F", "Viral fever", ("Paracetamol",)),
    ("rao", "dr.mehta", "Ravi Kulkarni", "8 / M", "Allergic rhinitis", ("Cetirizine", "Montelukast")),
    ("rao", "dr.rao", "Lakshmi Narayan", "61 / F", "Hypertension", ("Amlodipine", "Telmisartan")),
    ("iyer", "dr.iyer", "Bharat Menon", "45 / M", "Acute sinusitis", ("Azithromycin", "Levocetirizine")),
    ("iyer", "dr.iyer", "Meena Pillai", "29 / F", "Acid reflux", ("Pantoprazole",)),
)


class DemoError(ValueError):
    """seed-demo refused: not in demo mode, or the data folder is not empty."""


def doctor(username: str) -> dict:
    return next(d for d in DOCTORS if d["username"] == username)


def _snapshot(clinic: dict) -> dict:
    """The layout's stored profile: clinic fields only; doctor fields come from the author at print time."""
    return {"doctor_name": "", "qualifications": "", "reg_no": "", "clinic_name": clinic["name"],
            "address": clinic["address"], "phone": clinic["phone"]}


def rao_pad() -> dict:
    """Rao Clinic's shared letterpad: logo, clinic name, every doctor (the doctors block), a tagline."""
    return {"header": [{"type": "logo", "crop": [0.0, 0.0, 1.0, 1.0], "align": "left"},
                       {"type": "text", "field": "clinic_name", "role": "title", "align": "center", "color": "#1a3c6e"},
                       {"type": "doctors", "role": "normal", "align": "center"},
                       {"type": "text", "text": RAO_PAD_LINE, "role": "small", "align": "center"},
                       {"type": "rule", "color": "#1a3c6e", "thickness": "thin"}],
            "footer": [{"type": "text", "field": "address", "role": "small", "align": "center"},
                       {"type": "text", "field": "phone", "role": "small", "align": "center"}],
            "body": {"top": 0.24, "bottom": 0.92}, "profile": _snapshot(CLINICS[0])}


def iyer_pad() -> dict:
    """Iyer Clinic's own letterhead: the author's name and qualifications, the clinic, a tagline."""
    return {"header": [{"type": "logo", "crop": [0.0, 0.0, 1.0, 1.0], "align": "right"},
                       {"type": "text", "field": "doctor_name", "role": "title", "align": "left", "color": "#0b6e4f"},
                       {"type": "text", "field": "qualifications", "role": "subtitle", "align": "left"},
                       {"type": "text", "field": "clinic_name", "role": "normal", "align": "left"},
                       {"type": "text", "text": IYER_PAD_LINE, "role": "small", "align": "left"},
                       {"type": "rule", "color": "#0b6e4f", "thickness": "medium"}],
            "footer": [{"type": "text", "field": "address", "role": "small", "align": "left"},
                       {"type": "text", "field": "reg_no", "role": "small", "align": "right"}],
            "body": {"top": 0.26, "bottom": 0.92}, "profile": _snapshot(CLINICS[1])}


def _logo_jpeg(rgb, size) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, rgb).save(buf, "JPEG")
    return buf.getvalue()


def _rx(name: str) -> dict:
    return {"form": "Tab.", "name": name, "strength": "", "dose": "1-0-1", "timing": "After food",
            "duration": "5 days", "instructions": "", "status": "verified"}


def _check_can_seed() -> None:
    if os.getenv(DEMO_ENV, "") != "1":
        raise DemoError(f"seed-demo only runs with {DEMO_ENV}=1: it creates fake clinics with published passwords")
    root = data_root()
    default = scopemod.DEFAULT_DATA_DIR.resolve()
    if not os.getenv("DATA_DIR", "").strip() or root == default or (root.exists() and default.exists()
                                                                    and os.path.samefile(root, default)):
        raise DemoError("seed-demo needs DATA_DIR pointed at a NEW empty folder (not the default data folder)")
    if default.is_relative_to(root):
        raise DemoError("seed-demo refuses a folder that contains the default data folder")
    if root.exists() and any(root.iterdir()):
        raise DemoError("seed-demo needs a NEW empty folder: this one already holds files "
                        "(point DATA_DIR at a new folder; a half-seeded folder must be deleted by hand)")
    # Second layer, unreachable while the folder is empty: never trust a directory that somehow lists clinics.
    with closing(open_directory()) as d:
        if list_clinics(d):
            raise DemoError("seed-demo needs an empty data folder; this one already has clinics "
                            "(point DATA_DIR at a new folder; a half-seeded folder must be deleted by hand)")
        taken = [u["username"] for u in DOCTORS if lookup_username(d, u["username"]) is not None]
    if taken:
        raise DemoError(f"usernames already taken: {', '.join(taken)}")


def _set_clinic_details(conn, clinic: dict) -> None:
    """A6: the shared clinic part of the profile (the OP prefix was mirrored by provision_clinic, A13)."""
    details.save_clinic_details(conn, clinic_name=clinic["name"], address=clinic["address"], phone=clinic["phone"])


def _prescription(conn, author_id: int, author: str, patient: str, age_sex: str, diagnosis: str, medicines) -> int:
    """A1, A13: a finalized prescription by ``author_id`` with an OP number in the clinic's prefix. Returns its id."""
    patient_id, op_no = opno.create_patient_with_new_op(conn, patient, age_sex)
    form = {"patientName": patient, "ageSex": age_sex, "opNo": op_no, "diagnosis": [diagnosis], "complaints": [],
            "investigations": [], "rx": [_rx(m) for m in medicines], "advice": ["Plenty of fluids"],
            "review": "Review after 5 days"}
    encounter_id = dbmod.create_encounter(conn, patient_id, doctor_id=author_id, op_no=op_no, status="finalized")
    sha = hashlib.sha256(f"seed-demo:{patient}".encode("utf-8")).hexdigest()
    document_id = dbmod.save_document(conn, encounter_id, sha, form, engine=ACTOR, finalized_by=author_id,
                                      finalized_at=dbmod._utcnow())
    dbmod.log_audit(conn, actor=author, role="doctor", action="finalize", entity="encounter",
                    entity_id=str(encounter_id), detail={"document_id": document_id, "seeded": True})
    return document_id


def _letterhead(conn, clinic: dict, layout: dict) -> int:
    """A8: an active clinic-wide letterhead with its own logo file inside the clinic's templates folder."""
    template_id = tdb.create_template_draft(conn, layout)
    folder = clinic_dir(clinic["slug"]) / "templates"
    folder.mkdir(parents=True, exist_ok=True)
    logo = folder / f"{template_id}_logo.jpg"
    logo.write_bytes(_logo_jpeg(clinic["logo_rgb"], clinic["logo_size"]))
    tdb.set_template_logo(conn, template_id, str(logo))
    tdb.set_template_active(conn, template_id)                     # owner_user_id stays NULL: clinic-wide
    tdb.set_template_doctors(conn, template_id, clinic["doctors_mode"], [])
    return template_id


def seed_demo() -> dict:
    """Create both demo clinics. Returns, per slug: name, users (username -> id), document ids, template id."""
    _check_can_seed()
    out = {}
    for clinic in CLINICS:
        slug = clinic["slug"]
        clinics.provision_clinic(slug, clinic["name"], clinic["op_prefix"])
        users = {}
        for d in (x for x in DOCTORS if x["clinic"] == slug):
            uid, _ = accounts.create_user(slug, d["username"], display_name=d["display_name"],
                                          doctor_name=d["doctor_name"], qualifications=d["qualifications"],
                                          reg_no=d["reg_no"], password=d["password"], actor=ACTOR)
            users[d["username"]] = uid
        with use_scope(Scope(slug, None, ACTOR, "system")), closing(dbmod.get_conn(clinic_dir(slug) / "app.db")) as conn:
            conn.execute("UPDATE users SET must_change_password = 0")      # published demo passwords: no forced change
            conn.commit()
            _set_clinic_details(conn, clinic)
            docs = [_prescription(conn, users[author], author, *rest)
                    for where, author, *rest in PRESCRIPTIONS if where == slug]
            template_id = _letterhead(conn, clinic, rao_pad() if slug == "rao" else iyer_pad())
        out[slug] = {"name": clinic["name"], "users": users, "documents": docs, "template_id": template_id}
    return out


def run(_args) -> int:
    seed_demo()
    print("DEMO ONLY: fake clinics, fake patients and PUBLISHED passwords. Never put real patients in this data folder.")
    print(f"seeded {data_root()}")
    for d in DOCTORS:
        print(f"  {d['clinic']:<5} {d['username']:<9} password: {d['password']}")
    print("start the app with MULTI_CLINIC=1 and the same DATA_DIR, then sign in at /login")
    return 0


def register(sub, commands: dict) -> None:
    """Add ``seed-demo`` to the operator CLI (``admin.main`` calls this once per run)."""
    sub.add_parser("seed-demo", help="DEMO ONLY: two fake clinics, three doctors with published passwords (DEMO_MODE=1)")
    commands["seed-demo"] = run
