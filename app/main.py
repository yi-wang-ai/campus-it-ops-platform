"""Secure-by-default incident API for a LOCAL training lab.

An inbound alert never triggers shell/SSH. Repairs require a separate human step.
"""
import hmac
import os
from contextlib import asynccontextmanager
from html import escape
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, ConfigDict, Field

from app.db import connection, init_db

NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
STATUSES = ("OPEN", "APPROVED", "REPAIR_RECORDED", "REPAIR_FAILED", "RESOLVED")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ZabbixAlert(StrictModel):
    event_id: str = Field(min_length=1, max_length=128)
    host: str = Field(min_length=1, max_length=200)
    trigger_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=500)
    state: Literal["PROBLEM", "OK"]
    severity: str = Field(default="unknown", max_length=50)
    # On recovery Zabbix can include the original problem ID. Prefer it for precise correlation.
    problem_event_id: str | None = Field(default=None, min_length=1, max_length=128)


class RepairResult(StrictModel):
    success: bool
    details: str = Field(default="", max_length=1000)


def validated_secret(env_name: str) -> str:
    secret = os.getenv(env_name, "")
    if len(secret) < 24 or secret.startswith("replace-"):
        raise RuntimeError(f"Configure a strong {env_name} (24+ characters)")
    return secret


def check_config():
    secrets = [validated_secret(k) for k in (
        "ZABBIX_WEBHOOK_TOKEN", "VIEWER_API_TOKEN", "ADMIN_API_TOKEN", "DASHBOARD_PASSWORD")]
    if len(set(secrets)) != len(secrets):
        raise RuntimeError("All API and dashboard secrets must be distinct")
    if not os.getenv("DASHBOARD_USERNAME", "").strip():
        raise RuntimeError("DASHBOARD_USERNAME is required")


@asynccontextmanager
async def lifespan(_: FastAPI):
    check_config()
    init_db()
    yield


app = FastAPI(title="Campus IT Operations Platform", version="1.0.0", lifespan=lifespan)
basic = HTTPBasic(auto_error=False)


def require_token(received: str | None, env_name: str):
    expected = validated_secret(env_name)
    if not received or not hmac.compare_digest(received, expected):
        raise HTTPException(status_code=401, detail="Invalid credentials")


def viewer(x_viewer_token: str | None = Header(default=None)):
    require_token(x_viewer_token, "VIEWER_API_TOKEN")


def admin(x_admin_token: str | None = Header(default=None)):
    require_token(x_admin_token, "ADMIN_API_TOKEN")


def webhook(x_webhook_token: str | None = Header(default=None)):
    require_token(x_webhook_token, "ZABBIX_WEBHOOK_TOKEN")


def dashboard_auth(credentials: HTTPBasicCredentials | None = Depends(basic)):
    valid = bool(credentials) and (
        hmac.compare_digest(credentials.username, os.getenv("DASHBOARD_USERNAME", ""))
        and hmac.compare_digest(credentials.password, validated_secret("DASHBOARD_PASSWORD"))
    )
    if not valid:
        raise HTTPException(status_code=401, detail="Authentication required",
                            headers={"WWW-Authenticate": 'Basic realm="Campus Ops Lab"'})


def get_incident(db, incident_id: int):
    record = db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    if record is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return record


def audit(db, incident_id: int, action: str, details: str = ""):
    db.execute("INSERT INTO audit_events (incident_id, action, details) VALUES (?, ?, ?)",
               (incident_id, action, details))


def set_status(db, incident_id: int, status: str, *, extra_sql: str = "", params=()):
    db.execute(f"UPDATE incidents SET status=?, updated_at={NOW}{extra_sql} WHERE id=?",
               (status, *params, incident_id))


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz")
def healthz():
    # Liveness only, not a credential or database health report.
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    try:
        with connection() as db:
            db.execute("SELECT COUNT(*) FROM incidents").fetchone()
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status": "ready"}


@app.post("/api/v1/alerts/zabbix", dependencies=[Depends(webhook)])
def receive_zabbix_alert(alert: ZabbixAlert):
    with connection(write=True) as db:
        if alert.state == "PROBLEM":
            existing = db.execute(
                "SELECT id, status FROM incidents WHERE source_event_id = ?", (alert.event_id,)
            ).fetchone()
            if existing:
                return {"incident_id": existing["id"], "status": existing["status"], "duplicate": True}
            cursor = db.execute(
                "INSERT INTO incidents (source_event_id, host, trigger_id, title, severity) "
                "VALUES (?, ?, ?, ?, ?)",
                (alert.event_id, alert.host, alert.trigger_id, alert.name, alert.severity),
            )
            incident_id = cursor.lastrowid
            audit(db, incident_id, "PROBLEM_RECEIVED", "event_id=" + alert.event_id)
            return {"incident_id": incident_id, "status": "OPEN", "duplicate": False}

        prior_recovery = db.execute(
            "SELECT incident_id FROM recovery_events WHERE event_id=?", (alert.event_id,)
        ).fetchone()
        if prior_recovery:
            old = get_incident(db, prior_recovery["incident_id"])
            return {"incident_id": old["id"], "status": old["status"], "duplicate": True}

        if alert.problem_event_id:
            # Explicit correlation: never fall back if the declared problem is absent.
            target = db.execute(
                "SELECT * FROM incidents WHERE source_event_id=? AND host=? AND trigger_id=? "
                "AND status != 'RESOLVED'",
                (alert.problem_event_id, alert.host, alert.trigger_id),
            ).fetchone()
            matches = [target] if target else []
        else:
            matches = db.execute(
                "SELECT * FROM incidents WHERE host=? AND trigger_id=? AND status != 'RESOLVED'",
                (alert.host, alert.trigger_id),
            ).fetchall()
            if len(matches) > 1:
                raise HTTPException(status_code=409, detail="Ambiguous recovery; send problem_event_id")

        if not matches:
            return {"incident_id": None, "status": "NO_OPEN_INCIDENT", "duplicate": False}
        incident_id = matches[0]["id"]
        set_status(db, incident_id, "RESOLVED",
                   extra_sql=f", recovery_event_id=?, resolved_at={NOW}", params=(alert.event_id,))
        db.execute("INSERT INTO recovery_events (event_id, incident_id) VALUES (?, ?)",
                   (alert.event_id, incident_id))
        audit(db, incident_id, "RECOVERY_CONFIRMED", "event_id=" + alert.event_id)
        return {"incident_id": incident_id, "status": "RESOLVED", "duplicate": False}


@app.get("/api/v1/incidents", dependencies=[Depends(viewer)])
def list_incidents(limit: int = Query(50, ge=1, le=100),
                   offset: int = Query(0, ge=0),
                   status: Literal["OPEN", "APPROVED", "REPAIR_RECORDED", "REPAIR_FAILED", "RESOLVED"] | None = None):
    with connection() as db:
        if status is None:
            rows = db.execute("SELECT * FROM incidents ORDER BY id DESC LIMIT ? OFFSET ?",
                              (limit, offset)).fetchall()
        else:
            rows = db.execute("SELECT * FROM incidents WHERE status=? ORDER BY id DESC LIMIT ? OFFSET ?",
                              (status, limit, offset)).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/v1/incidents/{incident_id}", dependencies=[Depends(viewer)])
def read_incident(incident_id: int):
    with connection() as db:
        item = dict(get_incident(db, incident_id))
        item["audit"] = [dict(row) for row in db.execute(
            "SELECT action, details, created_at FROM audit_events WHERE incident_id=? ORDER BY id",
            (incident_id,),
        ).fetchall()]
        return item


@app.get("/api/v1/stats", dependencies=[Depends(viewer)])
def stats():
    with connection() as db:
        grouped = {r["status"]: r["count"] for r in db.execute(
            "SELECT status, COUNT(*) as count FROM incidents GROUP BY status").fetchall()}
    return {"total": sum(grouped.values()), "by_status": {k: grouped.get(k, 0) for k in STATUSES}}


@app.post("/api/v1/incidents/{incident_id}/approve", dependencies=[Depends(admin)])
def approve_repair(incident_id: int):
    with connection(write=True) as db:
        item = get_incident(db, incident_id)
        if item["status"] not in ("OPEN", "REPAIR_FAILED"):
            raise HTTPException(status_code=409, detail="Only OPEN or REPAIR_FAILED may be approved")
        set_status(db, incident_id, "APPROVED", extra_sql=f", approved_at={NOW}")
        audit(db, incident_id, "REPAIR_APPROVED", "Human operator authorization")
    return {"incident_id": incident_id, "status": "APPROVED",
            "next_step": "Run the allowlisted Ansible playbook from an operator workstation"}


@app.post("/api/v1/incidents/{incident_id}/repair-result", dependencies=[Depends(admin)])
def record_repair_result(incident_id: int, result: RepairResult):
    with connection(write=True) as db:
        item = get_incident(db, incident_id)
        if item["status"] != "APPROVED":
            raise HTTPException(status_code=409, detail="Repair must be approved first")
        status = "REPAIR_RECORDED" if result.success else "REPAIR_FAILED"
        set_status(db, incident_id, status)
        audit(db, incident_id, status, result.details)
    return {"incident_id": incident_id, "status": status,
            "note": "Only a matching Zabbix recovery event resolves the incident"}


STYLES = """
:root{color-scheme:dark}*{box-sizing:border-box}body{background:#0b1220;color:#e8effa;
font:15px/1.5 system-ui,-apple-system,sans-serif;margin:0}header{padding:28px max(24px,calc((100vw - 1120px)/2));
background:#111c30;border-bottom:1px solid #29364c}h1{margin:0;font-size:27px;letter-spacing:-.5px}
.sub{color:#98a9c2;margin:6px 0 0}main{max-width:1168px;padding:28px 24px;margin:auto}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin:0 0 25px}
.card,.panel{background:#142137;border:1px solid #293b55;border-radius:13px;padding:19px}
.count{font-size:27px;font-weight:750;display:block;margin:5px 0}.label{color:#9fb0ca;font-size:13px}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;text-align:left;min-width:750px}
th,td{padding:13px;border-bottom:1px solid #2a3951;vertical-align:top}th{color:#95a9c3}
a{color:#87c3ff}a:hover{color:white}.pill{display:inline-block;padding:3px 9px;border-radius:20px;
background:#293955;color:#e0eafb;font-size:12px}code{color:#c7e3ff}footer{padding:22px;color:#95a9c3}
"""


def page(body: str, title: str):
    return HTMLResponse("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
                        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                        f"<title>{escape(title)}</title><style>{STYLES}</style></head><body>"
                        "<header><h1>Campus IT Operations</h1>"
                        "<p class='sub'>Zabbix alerts · Human-approved Ansible recovery · Incident audit</p>"
                        "</header><main>" + body + "</main>"
                        "<footer>Isolated training lab · All incident times UTC</footer></body></html>")


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(dashboard_auth)])
def dashboard():
    with connection() as db:
        incidents = db.execute("SELECT * FROM incidents ORDER BY id DESC LIMIT 50").fetchall()
        grouped = {r["status"]: r["c"] for r in db.execute(
            "SELECT status, COUNT(*) c FROM incidents GROUP BY status").fetchall()}
    cards = "".join(f"<div class='card'><span class='label'>{escape(k)}</span>"
                    f"<span class='count'>{grouped.get(k, 0)}</span></div>" for k in STATUSES)
    rows = "".join(
        "<tr><td><a href='/incidents/" + str(item["id"]) + "'>#" + str(item["id"]) + "</a></td>"
        + "".join(f"<td>{escape(str(item[k]))}</td>" for k in
                  ("host", "title", "severity"))
        + f"<td><span class='pill'>{escape(item['status'])}</span></td>"
        + f"<td>{escape(item['created_at'])}</td></tr>" for item in incidents
    )
    if not rows:
        rows = "<tr><td colspan='6'>No alerts yet. Run the safe simulated demo.</td></tr>"
    return page(f"<div class='cards'>{cards}</div><section class='panel'><h2>Recent incidents</h2>"
                f"<p class='sub'>Read-only dashboard · <a href='/docs'>API documentation</a></p>"
                "<div class='scroll'><table><thead><tr><th>ID</th><th>Host</th><th>Problem</th>"
                "<th>Severity</th><th>Status</th><th>Created</th></tr></thead>"
                f"<tbody>{rows}</tbody></table></div></section>", "Incident dashboard")


@app.get("/incidents/{incident_id}", response_class=HTMLResponse,
         dependencies=[Depends(dashboard_auth)])
def dashboard_detail(incident_id: int):
    with connection() as db:
        incident = get_incident(db, incident_id)
        audit_rows = db.execute("SELECT * FROM audit_events WHERE incident_id=? ORDER BY id",
                                (incident_id,)).fetchall()
    info = "".join(f"<tr><th>{escape(k)}</th><td>{escape(str(incident[k]))}</td></tr>"
                   for k in ("id", "source_event_id", "host", "trigger_id", "title",
                             "severity", "status", "created_at", "approved_at", "resolved_at"))
    history = "".join(f"<tr><td>{escape(r['created_at'])}</td><td>{escape(r['action'])}</td>"
                      f"<td>{escape(r['details'])}</td></tr>" for r in audit_rows)
    return page("<p><a href='/'>← Dashboard</a></p><section class='panel'><h2>Incident detail</h2>"
                f"<div class='scroll'><table>{info}</table></div><h2>Audit trail</h2>"
                f"<div class='scroll'><table><tr><th>UTC</th><th>Action</th><th>Details</th></tr>"
                f"{history}</table></div></section>", f"Incident {incident_id}")
