from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sqlite3

import pytest

from app.db import database_path
from .conftest import WEBHOOK_SECRET, VIEWER_SECRET, ADMIN_SECRET, DASH_SECRET

WEBHOOK = {"X-Webhook-Token": WEBHOOK_SECRET}
VIEWER = {"X-Viewer-Token": VIEWER_SECRET}
ADMIN = {"X-Admin-Token": ADMIN_SECRET}
AUTH = ("tester", DASH_SECRET)
URL = "/api/v1/alerts/zabbix"


def event(state="PROBLEM", event_id="problem-100", *, host="lab-vm-01",
          trigger_id="trg-7", problem_event_id=None, name="nginx unavailable"):
    return {"event_id": event_id, "host": host, "trigger_id": trigger_id,
            "name": name, "state": state, "severity": "High",
            "problem_event_id": problem_event_id}


def post(client, payload=None):
    return client.post(URL, json=payload or event(), headers=WEBHOOK)


def incident(client, id):
    return client.get(f"/api/v1/incidents/{id}", headers=VIEWER).json()


def approve(client, id):
    return client.post(f"/api/v1/incidents/{id}/approve", headers=ADMIN)


def repair(client, id, success=True, details="Ansible playbook exit code 0"):
    return client.post(f"/api/v1/incidents/{id}/repair-result", headers=ADMIN,
                       json={"success": success, "details": details})


def test_health_and_readiness(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}
    assert client.get("/api/v1/incidents", headers=VIEWER).json() == []


@pytest.mark.parametrize("headers", [{}, {"X-Webhook-Token": "wrong"}, VIEWER, ADMIN])
def test_webhook_rejects_invalid_token(client, headers):
    assert client.post(URL, json=event(), headers=headers).status_code == 401


def test_private_reads_require_viewer_token(client):
    id = post(client).json()["incident_id"]
    for path in ("/api/v1/incidents", f"/api/v1/incidents/{id}", "/api/v1/stats"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=ADMIN).status_code == 401
        assert client.get(path, headers=VIEWER).status_code == 200


def test_basic_auth_dashboard_and_security_headers(client):
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("tester", "wrong")).status_code == 401
    ok = client.get("/", auth=AUTH)
    assert ok.status_code == 200 and "Recent incidents" in ok.text
    assert ok.headers["X-Frame-Options"] == "DENY"
    assert ok.headers["Cache-Control"] == "no-store"
    assert ok.headers["X-Content-Type-Options"] == "nosniff"


def test_end_to_end_incident_flow(client):
    first = post(client)
    assert first.status_code == 200
    id = first.json()["incident_id"]
    assert first.json()["status"] == "OPEN"
    assert post(client).json() == {"incident_id": id, "status": "OPEN", "duplicate": True}
    assert approve(client, id).json()["status"] == "APPROVED"
    assert repair(client, id).json()["status"] == "REPAIR_RECORDED"
    assert incident(client, id)["status"] == "REPAIR_RECORDED"
    recovered = post(client, event("OK", "recovery-101", problem_event_id="problem-100"))
    assert recovered.json() == {"incident_id": id, "status": "RESOLVED", "duplicate": False}
    assert post(client, event("OK", "recovery-101", problem_event_id="problem-100")).json() == {
        "incident_id": id, "status": "RESOLVED", "duplicate": True}
    record = incident(client, id)
    assert record["resolved_at"] is not None
    assert [e["action"] for e in record["audit"]] == [
        "PROBLEM_RECEIVED", "REPAIR_APPROVED", "REPAIR_RECORDED", "RECOVERY_CONFIRMED"]
    assert post(client).json()["status"] == "RESOLVED"
    assert approve(client, id).status_code == 409
    assert repair(client, id).status_code == 409


def test_automatic_restoration_closes_without_repair(client):
    id = post(client).json()["incident_id"]
    assert post(client, event("OK", "rec-1", problem_event_id="problem-100")).json()["status"] == "RESOLVED"
    assert [e["action"] for e in incident(client, id)["audit"]] == ["PROBLEM_RECEIVED", "RECOVERY_CONFIRMED"]


def test_unknown_or_mismatched_recovery_never_closes(client):
    id = post(client).json()["incident_id"]
    for payload in (
        event("OK", "r1", trigger_id="different"),
        event("OK", "r2", problem_event_id="not-a-real-problem"),
        event("OK", "r3", host="another-host", problem_event_id="problem-100"),
    ):
        assert post(client, payload).json()["status"] == "NO_OPEN_INCIDENT"
    assert incident(client, id)["status"] == "OPEN"


def test_ambiguous_recovery_requires_explicit_problem_id(client):
    first_id = post(client).json()["incident_id"]
    second_id = post(client, event(event_id="problem-200")).json()["incident_id"]
    assert post(client, event("OK", "r201")).status_code == 409
    assert incident(client, first_id)["status"] == "OPEN"
    assert incident(client, second_id)["status"] == "OPEN"
    assert post(client, event("OK", "r202", problem_event_id="problem-200")).json()["incident_id"] == second_id
    assert post(client, event("OK", "r203")).json()["incident_id"] == first_id


def test_single_unambiguous_recovery_fallback(client):
    id = post(client).json()["incident_id"]
    assert post(client, event("OK", "r4")).json()["incident_id"] == id


def test_failed_repair_requires_reapproval_before_retry(client):
    id = post(client).json()["incident_id"]
    assert repair(client, id).status_code == 409
    assert approve(client, id).status_code == 200
    assert repair(client, id, success=False).json()["status"] == "REPAIR_FAILED"
    assert repair(client, id).status_code == 409
    assert approve(client, id).status_code == 200
    assert repair(client, id).json()["status"] == "REPAIR_RECORDED"


def test_admin_changes_require_correct_admin_token(client):
    id = post(client).json()["incident_id"]
    for headers in ({}, VIEWER, WEBHOOK, {"X-Admin-Token": "bad"}):
        assert client.post(f"/api/v1/incidents/{id}/approve", headers=headers).status_code == 401
        assert client.post(f"/api/v1/incidents/{id}/repair-result", headers=headers,
                           json={"success": True}).status_code == 401


def test_filters_pagination_and_stats(client):
    for i in range(5):
        post(client, event(event_id=f"evt-{i}", host=f"host-{i}"))
    records = client.get("/api/v1/incidents?limit=2&offset=1", headers=VIEWER).json()
    assert [r["source_event_id"] for r in records] == ["evt-3", "evt-2"]
    assert len(client.get("/api/v1/incidents?status=RESOLVED", headers=VIEWER).json()) == 0
    stats = client.get("/api/v1/stats", headers=VIEWER).json()
    assert stats["total"] == 5 and stats["by_status"]["OPEN"] == 5
    assert client.get("/api/v1/incidents?limit=999", headers=VIEWER).status_code == 422
    assert client.get("/api/v1/incidents?status=NOT_REAL", headers=VIEWER).status_code == 422


def test_payload_validation_rejects_extra_and_invalid_fields(client):
    assert post(client, {**event(), "unexpected": True}).status_code == 422
    assert post(client, {**event(), "state": "BAD"}).status_code == 422
    assert post(client, {**event(), "host": ""}).status_code == 422
    id = post(client).json()["incident_id"]
    assert repair(client, id, details="x" * 1001).status_code == 422
    assert client.get("/api/v1/incidents/999999", headers=VIEWER).status_code == 404


def test_dashboard_escapes_untrusted_alert_text(client):
    id = post(client, event(name="<script>alert('XSS')</script>")).json()["incident_id"]
    body = client.get("/", auth=AUTH).text
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body
    body = client.get(f"/incidents/{id}", auth=AUTH).text
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body


def test_webhook_database_uniqueness_under_concurrent_posts(client):
    # BEGIN IMMEDIATE serializes workers accessing this shared test DB.
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda _: post(client).json(), range(8)))
    assert len({r["incident_id"] for r in results}) == 1
    assert sum(not r["duplicate"] for r in results) == 1
    with closing(sqlite3.connect(database_path())) as db:
        assert db.execute("SELECT count(*) FROM incidents").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 1


def test_sequential_recovery_replay_does_not_duplicate_audit(client):
    id = post(client).json()["incident_id"]
    recovery = event("OK", "r5", problem_event_id="problem-100")
    post(client, recovery)
    post(client, recovery)
    assert [x["action"] for x in incident(client, id)["audit"]].count("RECOVERY_CONFIRMED") == 1


def test_dashboard_detail_requires_basic_auth(client):
    id = post(client).json()["incident_id"]
    assert client.get(f"/incidents/{id}").status_code == 401
    assert client.get(f"/incidents/{id}", auth=AUTH).status_code == 200
    assert client.get("/incidents/12345", auth=AUTH).status_code == 404


def test_no_recovery_receipt_for_unmatched_event(client):
    unmatched = event("OK", "r-early", problem_event_id="problem-100")
    assert post(client, unmatched).json()["status"] == "NO_OPEN_INCIDENT"
    id = post(client).json()["incident_id"]
    assert post(client, unmatched).json()["incident_id"] == id
    assert incident(client, id)["status"] == "RESOLVED"
