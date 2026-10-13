"""The API surface is unchanged by the router split.

Run:  .venv/bin/python -m pytest tests/test_api_app.py -q
"""
import ast
from pathlib import Path

from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.config import override_settings

EXPECTED_ROUTES = {
    ("GET", "/api/health"), ("GET", "/health"),
    ("POST", "/api/transcribe"), ("POST", "/api/format"), ("POST", "/api/v1/correct"),
    ("GET", "/api/v1/profile"), ("PUT", "/api/v1/profile"),
    ("GET", "/api/v1/patients"), ("POST", "/api/v1/patients"),
    ("GET", "/api/v1/encounters"), ("POST", "/api/v1/encounters"),
    ("GET", "/api/v1/encounters/today"),
    ("POST", "/api/v1/documents"), ("GET", "/api/v1/documents/{document_id}"),
    ("POST", "/api/v1/templates"), ("GET", "/api/v1/templates/active"), ("POST", "/api/v1/templates/deactivate"),
    ("GET", "/api/v1/templates/{template_id}/preview.pdf"), ("PUT", "/api/v1/templates/{template_id}"),
    ("POST", "/api/v1/templates/{template_id}/accept"), ("DELETE", "/api/v1/templates/{template_id}"),
}


def _route_table(app):
    # The OpenAPI schema is stable across FastAPI versions; newer ones wrap included routers.
    return {(m.upper(), path) for path, ops in app.openapi()["paths"].items() for m in ops}


def test_route_table_is_unchanged():
    assert _route_table(M.app) == EXPECTED_ROUTES


def test_create_app_builds_independent_apps_with_static_mount_last():
    from doctor_dictation.api.app import create_app

    a, b = create_app(), create_app()
    assert a is not b
    assert _route_table(a) == EXPECTED_ROUTES
    assert a.routes[-1].name == "frontend"  # mounted last so it cannot shadow /api


def test_health_reads_settings_on_every_request(monkeypatch):
    client = TestClient(M.app)
    override_settings(monkeypatch, openai_api_key="sk-call-time-secret")
    on = client.get("/api/health")
    assert on.json()["openai_configured"] is True
    assert "sk-call-time-secret" not in on.text
    override_settings(monkeypatch, openai_api_key="")
    assert client.get("/api/health").json()["openai_configured"] is False


def test_no_module_level_settings_in_api_or_main():
    root = Path(M.__file__).parent
    offenders = []
    for path in [root / "main.py", *sorted((root / "api").glob("*.py"))]:
        for node in ast.parse(path.read_text()).body:
            value = getattr(node, "value", None)
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr)) and value is not None:
                for sub in ast.walk(value):
                    if isinstance(sub, ast.Call):
                        fn = getattr(sub.func, "id", getattr(sub.func, "attr", ""))
                        if fn == "get_settings":
                            offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
