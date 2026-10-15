"""Template storage helpers (contract 4.4). Callers own the connection.

A template's scope is ``owner_user_id``: None is the clinic letterhead, a user id is that doctor's own. Each scope
keeps at most one active row; accepting or stopping one scope never touches the other.
"""
import json

from doctor_dictation.db import _utcnow


def create_template_draft(conn, layout: dict, clinic="default", created_at=None) -> int:
    cur = conn.execute(
        "INSERT INTO templates(clinic, layout_json, status, created_at) VALUES (?, ?, 'draft', ?)",
        (clinic, json.dumps(layout, ensure_ascii=False), created_at or _utcnow()))
    conn.commit()
    return cur.lastrowid


def get_template(conn, template_id):
    return conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()


def update_template_layout(conn, template_id, layout: dict) -> bool:
    cur = conn.execute("UPDATE templates SET layout_json = ? WHERE id = ?",
                       (json.dumps(layout, ensure_ascii=False), template_id))
    conn.commit()
    return cur.rowcount > 0


def set_template_logo(conn, template_id, logo_path) -> None:
    conn.execute("UPDATE templates SET logo_path = ? WHERE id = ?", (logo_path, template_id))
    conn.commit()


def set_template_active(conn, template_id, accepted_at=None, owner_user_id=None) -> bool:
    """Draft -> active in one scope (``owner_user_id`` None = the clinic); that scope's previous active row
    becomes archived (one commit)."""
    row = get_template(conn, template_id)
    if row is None or row["status"] != "draft":
        return False
    conn.execute("UPDATE templates SET status = 'archived' WHERE clinic = ? AND status = 'active'"
                 " AND owner_user_id IS ?", (row["clinic"], owner_user_id))
    conn.execute("UPDATE templates SET status = 'active', accepted_at = ?, owner_user_id = ? WHERE id = ?",
                 (accepted_at or _utcnow(), owner_user_id, template_id))
    conn.commit()
    return True


def delete_template(conn, template_id) -> bool:
    cur = conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    conn.commit()
    return cur.rowcount > 0


def purge_expired_drafts(conn, cutoff_iso: str) -> list:
    """Delete drafts created before ``cutoff_iso``; return the deleted rows (id, logo_path)."""
    rows = conn.execute("SELECT id, logo_path FROM templates WHERE status = 'draft' AND created_at < ?",
                        (cutoff_iso,)).fetchall()
    conn.execute("DELETE FROM templates WHERE status = 'draft' AND created_at < ?", (cutoff_iso,))
    conn.commit()
    return rows


def count_uploads_since(conn, clinic: str, since_iso: str) -> int:
    """Uploads are counted from audit_log, so discarding or purging a draft cannot reset the quota."""
    return conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE action = 'template_upload'"
        " AND json_extract(detail, '$.clinic') = ? AND at >= ?", (clinic, since_iso)).fetchone()[0]


def get_active_template(conn, clinic="default", owner_user_id=None):
    """The active row of one scope (``owner_user_id`` None = the clinic letterhead), or None."""
    return conn.execute("SELECT * FROM templates WHERE clinic = ? AND status = 'active' AND owner_user_id IS ?",
                        (clinic, owner_user_id)).fetchone()


def deactivate_templates(conn, clinic="default", owner_user_id=None) -> int:
    """Active -> archived for one scope (drafts and the other scope are untouched); returns the rows changed."""
    cur = conn.execute("UPDATE templates SET status = 'archived' WHERE clinic = ? AND status = 'active'"
                       " AND owner_user_id IS ?", (clinic, owner_user_id))
    conn.commit()
    return cur.rowcount


def set_template_doctors(conn, template_id, mode: str, ids: list) -> bool:
    """Store which doctors the letterhead lists (the caller validated ``mode`` and ``ids``)."""
    cur = conn.execute("UPDATE templates SET doctors_mode = ?, doctors_ids = ? WHERE id = ?",
                       (mode, json.dumps(ids), template_id))
    conn.commit()
    return cur.rowcount > 0


def clinic_doctors(conn) -> list:
    """Active users with the doctor role, oldest account first: the stable order a letterhead lists them in."""
    return conn.execute("SELECT id, username, display_name, doctor_name, qualifications, reg_no FROM users"
                        " WHERE is_active = 1 AND role = 'doctor' ORDER BY id").fetchall()
