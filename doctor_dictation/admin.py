"""Operator command line: ``python -m doctor_dictation.admin <command>``. Run on the host, never over HTTP.

Commands: create-clinic, list-clinics, migrate-all, adopt-existing, create-user, reset-password.
create-clinic and adopt-existing take ``--first-user``. A temporary password is printed once on stdout
and is never logged or audited.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from doctor_dictation import accounts, clinics
from doctor_dictation import db as dbmod
from doctor_dictation.directory import DirectoryError, check_clinic_fields, create_clinic, get_clinic, list_clinics, open_directory
from doctor_dictation.directory.logins import lookup_username
from doctor_dictation.scope import clinic_dir


def _precheck_username(username) -> None:
    """Fail before anything is created or moved when the username is invalid or already taken."""
    accounts.check_username(username)
    with closing(open_directory()) as d:
        if lookup_username(d, username) is not None:
            raise accounts.AccountError("that username is already taken")


def _print_password(username, password) -> None:
    print(f"user '{username}' created; temporary password: {password}")
    print("(shown once; the user must change it at first sign-in)")


def _create(args) -> int:
    if args.first_user:
        _precheck_username(args.first_user)
    clinics.provision_clinic(args.slug, args.name, args.op_prefix)
    print(f"created clinic '{args.slug}' ({args.name}) at {clinic_dir(args.slug)}")
    if args.first_user:
        _, pw = accounts.create_user(args.slug, args.first_user, display_name=args.display_name or "", actor="operator")
        _print_password(args.first_user, pw)
    return 0


def _create_user(args) -> int:
    _, pw = accounts.create_user(args.clinic, args.username, display_name=args.display_name or "", role=args.role,
                                 actor="operator")
    _print_password(args.username, pw)
    return 0


def _reset_password(args) -> int:
    pw = accounts.reset_password(args.user, actor="operator")
    print(f"temporary password: {pw}")
    print("(shown once; the user must change it at next sign-in and any open sessions have ended)")
    return 0


def _list(_args) -> int:
    with closing(open_directory()) as d:
        rows = list_clinics(d)
    if not rows:
        print("no clinics yet")
    for r in rows:
        print(f"{r['slug']:<20} {r['name']:<30} {r['status']:<9} {r['op_prefix']}")
    return 0


def _migrate_all(_args) -> int:
    done, failed = clinics.migrate_all()
    for slug, applied in done.items():
        print(f"{slug}: {', '.join(applied) if applied else 'up to date'}")
    for slug, why in failed.items():
        print(f"{slug}: FAILED {why}", file=sys.stderr)
    return 1 if failed else 0


def _prepare_source(src_db: Path) -> str:
    """Flush the write-ahead log into app.db (refusing if the database is busy) and return the saved clinic name."""
    conn = sqlite3.connect(str(src_db))
    try:
        busy = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
        if busy:
            raise DirectoryError("the database is in use: stop the app, then run this again")
        try:
            row = conn.execute("SELECT clinic_name FROM clinic_profile WHERE id = 1").fetchone()
        except sqlite3.Error:
            row = None
        return (row[0] if row else "") or ""
    finally:
        conn.close()


def _rewrite_paths(db_file: Path, old_dir: Path, new_dir: Path) -> None:
    """Point stored absolute paths (documents.pdf_path, templates.logo_path) at the clinic folder.

    Uses substr comparison rather than LIKE so ``%`` and ``_`` in a path are not wildcards.
    """
    old, new = str(old_dir), str(new_dir)
    conn = sqlite3.connect(str(db_file))
    try:
        for table, column, sub in (("documents", "pdf_path", "pdfs"), ("templates", "logo_path", "templates")):
            o, n = str(old_dir / sub), str(new_dir / sub)
            conn.execute(
                f"UPDATE {table} SET {column} = ? || substr({column}, ?) WHERE substr({column}, 1, ?) = ?",
                (n, len(o) + 1, len(o), o),
            )
        conn.commit()
    finally:
        conn.close()


def _saved_doctor_fields(db_file: Path) -> dict:
    """doctor_name, qualifications and reg_no from the saved clinic profile; empty when there is none."""
    conn = sqlite3.connect(str(db_file))
    try:
        row = conn.execute("SELECT doctor_name, qualifications, reg_no FROM clinic_profile WHERE id = 1").fetchone()
    except sqlite3.Error:
        row = None
    finally:
        conn.close()
    return dict(zip(("doctor_name", "qualifications", "reg_no"), (v or "" for v in row))) if row else {}


def _adopt(args) -> int:
    src_db = Path(os.getenv(dbmod.DB_PATH_ENV) or dbmod.DEFAULT_DB_PATH)
    src_root = src_db.parent
    if not src_db.is_file():
        raise DirectoryError(f"no database at {src_db}")
    check_clinic_fields(args.slug, args.name or args.slug)
    if args.first_user:
        _precheck_username(args.first_user)
    target = clinic_dir(args.slug)
    with closing(open_directory()) as d:
        if get_clinic(d, args.slug) is not None:
            raise DirectoryError(f"clinic '{args.slug}' already exists")
    if target.exists():
        raise DirectoryError(f"{target} already exists")
    saved_name = _prepare_source(src_db)          # also flushes the WAL; refuses when busy
    name = args.name or saved_name.strip() or args.slug
    check_clinic_fields(args.slug, name)          # validate the FINAL name before anything is created or moved
    wal = Path(f"{src_db}-wal")
    if wal.exists() and wal.stat().st_size > 0:   # a writer arrived after the checkpoint: its data would be stranded
        raise DirectoryError("the database is in use: stop the app, then run this again")
    target.mkdir(parents=True)
    shutil.move(str(src_db), str(target / "app.db"))
    try:
        for sub in ("pdfs", "templates"):
            if (src_root / sub).exists():
                shutil.move(str(src_root / sub), str(target / sub))
        _rewrite_paths(target / "app.db", src_root, target)
        clinics.migrate_clinic(args.slug)
        with closing(open_directory()) as d:
            create_clinic(d, args.slug, name)
    except (OSError, sqlite3.Error) as exc:
        print(
            f"error: {exc}\nthe database was already moved to {target}; finish the move by hand "
            f"(pdfs/ and templates/ from {src_root}, stored paths in app.db), then register it with: "
            f"python -m doctor_dictation.admin create-clinic --slug {args.slug} --name \"{name}\"",
            file=sys.stderr,
        )
        return 1
    print(f"adopted {src_db} as clinic '{args.slug}' ({name}) at {target}")
    if args.first_user:
        try:
            _, pw = accounts.create_user(args.slug, args.first_user, display_name=args.display_name or "",
                                         actor="operator", **_saved_doctor_fields(target / "app.db"))
        except (ValueError, sqlite3.Error) as exc:
            print(f"error: {exc}\nthe clinic was adopted but its first user was not created; create it with: "
                  f"python -m doctor_dictation.admin create-user --clinic {args.slug} --username {args.first_user}",
                  file=sys.stderr)
            return 1
        _print_password(args.first_user, pw)
    print("next: start the app with MULTI_CLINIC=1 (and stop any single-database instance; "
          "it would re-create an empty app.db at the old path)")
    return 0


COMMANDS = {"create-clinic": _create, "list-clinics": _list, "migrate-all": _migrate_all, "adopt-existing": _adopt,
            "create-user": _create_user, "reset-password": _reset_password}


def main(argv=None) -> int:
    load_dotenv(find_dotenv(usecwd=True))      # same .env the app reads, found from where the operator runs this
    parser = argparse.ArgumentParser(prog="python -m doctor_dictation.admin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-clinic", help="create a clinic folder, database and directory entry")
    c.add_argument("--slug", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--op-prefix", default="OP")
    c.add_argument("--first-user", help="also create this user and print a temporary password once")
    c.add_argument("--display-name", help="display name for --first-user")
    u = sub.add_parser("create-user", help="add a user to a clinic and print a temporary password once")
    u.add_argument("--clinic", required=True)
    u.add_argument("--username", required=True)
    u.add_argument("--display-name")
    u.add_argument("--role", choices=accounts.ROLES, default="doctor")
    r = sub.add_parser("reset-password", help="set a new temporary password and end the user's sessions")
    r.add_argument("--user", required=True)
    sub.add_parser("list-clinics", help="list registered clinics")
    sub.add_parser("migrate-all", help="apply pending migrations to every clinic")
    a = sub.add_parser("adopt-existing", help="move today's single database, pdfs/ and templates/ into a clinic (stop the app first)")
    a.add_argument("--slug", required=True)
    a.add_argument("--name", help="clinic name (default: the saved profile's clinic name, else the slug)")
    a.add_argument("--first-user", help="also create this user from the saved profile and print a temporary password once")
    a.add_argument("--display-name", help="display name for --first-user")
    args = parser.parse_args(argv)
    try:
        return COMMANDS[args.cmd](args)
    except ValueError as exc:      # DirectoryError and an invalid slug from clinic_dir
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
