"""Clinic lifecycle: provision, migrate, iterate. Used by the operator command and app startup;
request code never imports this. ``migrate_clinic`` takes an explicit path so it works whether or
not ``MULTI_CLINIC`` is on (the operator runs it from a shell)."""
from __future__ import annotations

from contextlib import closing

from doctor_dictation import db as dbmod
from doctor_dictation.db import opno
from doctor_dictation.directory import DirectoryError, check_clinic_fields, create_clinic, get_clinic, list_clinics, open_directory
from doctor_dictation.scope import Scope, clinic_dir, use_scope


def migrate_clinic(slug: str, create: bool = True) -> list[str]:
    """Apply pending migrations; create the folder and database first unless ``create`` is False.

    ``migrate_all`` passes ``create=False`` so a registered clinic whose files were lost is
    reported instead of silently replaced by an empty database.
    """
    path = clinic_dir(slug) / "app.db"
    if not create and not path.is_file():
        raise FileNotFoundError(f"folder missing: {path} does not exist")
    return dbmod.init_db(path)


def _mirror_prefix(slug: str, op_prefix: str) -> None:
    """Copy the directory's OP prefix into the clinic's own profile row, which is what OP numbers read."""
    with closing(dbmod.get_conn(clinic_dir(slug) / "app.db")) as conn:
        opno.set_op_prefix(conn, op_prefix)


def provision_clinic(slug: str, name: str, op_prefix: str = "OP") -> int:
    """Validate, refuse duplicates before touching the disk, build the clinic, then register it.

    A crash between the database and the registration leaves an unregistered folder; running the
    same command again succeeds because the migration is idempotent.
    """
    check_clinic_fields(slug, name, op_prefix)
    with closing(open_directory()) as d:
        if get_clinic(d, slug) is not None:
            raise DirectoryError(f"clinic '{slug}' already exists")
        migrate_clinic(slug)
        _mirror_prefix(slug, op_prefix)
        return create_clinic(d, slug, name, op_prefix)


def migrate_all() -> tuple[dict[str, list[str]], dict[str, str]]:
    """Migrate every registered clinic (disabled ones too, so re-enabling works).

    Returns ``(done, failed)``: slug to versions applied, slug to error text. One clinic's
    failure never stops the others.
    """
    with closing(open_directory()) as d:
        rows = [(r["slug"], r["op_prefix"]) for r in list_clinics(d)]
    done, failed = {}, {}
    for slug, op_prefix in rows:
        try:
            applied = migrate_clinic(slug, create=False)
            _mirror_prefix(slug, op_prefix)        # the directory is the record; this also fills pre-M4 clinics
            done[slug] = applied
        except Exception as exc:  # noqa: BLE001 - report and carry on with the other clinics
            failed[slug] = f"{type(exc).__name__}: {exc}"
    return done, failed


def for_each_clinic():
    """Yield each active clinic's slug with its ``Scope`` set for the body of the loop.

    The only legitimate way to run clinic work outside a request (startup purge, maintenance).
    Meaningful in multi-clinic mode; with the flag off ``db_path()`` ignores the scope.
    """
    with closing(open_directory()) as d:
        slugs = [r["slug"] for r in list_clinics(d, active_only=True)]
    for slug in slugs:
        with use_scope(Scope(slug)):
            yield slug
