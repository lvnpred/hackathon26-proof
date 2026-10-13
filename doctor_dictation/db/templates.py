"""Template storage helpers (contract 4.4). Callers own the connection."""
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


def set_template_active(conn, template_id, accepted_at=None) -> bool:
    """Draft -> active; the clinic's previous active row becomes archived (one commit)."""
    row = get_template(conn, template_id)
    if row is None or row["status"] != "draft":
        return False
    conn.execute("UPDATE templates SET status = 'archived' WHERE clinic = ? AND status = 'active'",
                 (row["clinic"],))
    conn.execute("UPDATE templates SET status = 'active', accepted_at = ? WHERE id = ?",
                 (accepted_at or _utcnow(), template_id))
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


def get_active_template(conn, clinic="default"):
    return conn.execute("SELECT * FROM templates WHERE clinic = ? AND status = 'active'", (clinic,)).fetchone()


def deactivate_templates(conn, clinic="default") -> int:
    """Active -> archived for the clinic (drafts are untouched); returns the rows changed."""
    cur = conn.execute("UPDATE templates SET status = 'archived' WHERE clinic = ? AND status = 'active'", (clinic,))
    conn.commit()
    return cur.rowcount
