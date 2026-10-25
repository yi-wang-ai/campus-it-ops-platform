# Campus IT Operations Platform

## The Problem

A campus runs dozens of servers. When one goes down at 2 AM, someone has to notice, log in, figure out what broke, fix it, and write up what happened. This is slow, error-prone, and leaves no reliable record.

## The Solution

This platform automates the detection-to-recovery pipeline:

```
Server fails → Zabbix detects it → Incident created automatically
                                          ↓
                                   Operator approves repair
                                          ↓
                                   Ansible fixes the server
                                          ↓
                                   Zabbix confirms recovery → Incident closed
```

Every step is recorded. No repair runs without human approval. No incident closes until monitoring confirms the service is actually back.

![Dashboard](docs/images/dashboard-docker-demo.jpg)

![Incident detail with audit trail](docs/images/incident-detail-demo.jpg)

## Tech Stack

- **Zabbix** — monitors servers and detects failures
- **FastAPI** — receives alerts, tracks incidents, serves the dashboard
- **Ansible** — runs recovery playbooks on approved hosts
- **SQLite** — stores incidents and audit trails
- **Docker** — packages everything for deployment

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
# Edit .env — replace the four placeholder secrets with random values

set -a && source .env && set +a
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 for the dashboard. Run `bash scripts/demo-api.sh` to simulate a full incident cycle.

## Tests

```bash
python -m pytest -v
```

30 tests cover the full lifecycle: alert ingestion, deduplication, approval, repair, recovery, concurrency, auth, and XSS protection. CI runs on every push.

## Project Structure

```
app/           Backend API, database, operator CLI
ansible/       Recovery playbook + inventory
zabbix/        Webhook script for Zabbix
tests/         30 automated tests
docs/          Architecture, lab setup, roadmap
```

## Key Design Decisions

- **Webhooks never trigger repairs.** An alert creates an incident; a human must approve before anything runs.
- **Repair ≠ resolved.** Recording a successful Ansible run does not close the incident. Only a Zabbix OK signal does.
- **Failed repairs need re-approval.** No silent retries.
- **Four separate secrets** for webhook, viewer, admin, and dashboard — rejected at startup if weak or duplicated.

## Verified Results

### Unit Tests (30 tests, CI)

30 tests cover the full lifecycle: alert ingestion, deduplication, approval, repair, recovery, concurrency, auth, and XSS protection. CI runs on every push.

### Containerized Integration Test (Zabbix + Ansible)

Tested on macOS with Docker Desktop. Five containers (Zabbix server + PostgreSQL + web frontend + nginx target + IT Ops API) run the full detection-to-recovery pipeline:

```
cd integration-test && docker compose up -d --build && bash run-integration.sh
```

**Verified end-to-end pipeline:**

1. Zabbix server-side simple check (`net.tcp.service[http]`) detects real nginx failure
2. Zabbix webhook fires → IT Ops API creates incident (OPEN)
3. Operator approves repair via API → APPROVED
4. Ansible restores nginx over SSH (key-based auth, port 2222) → REPAIR_RECORDED
5. Zabbix detects recovery → webhook fires OK → incident RESOLVED

**Audit trail from a real run (2026-10-25):**

```
05:24:51Z  PROBLEM_RECEIVED      event_id=27
05:24:51Z  REPAIR_APPROVED       Human operator authorization
05:24:53Z  REPAIR_RECORDED       Ansible recover-nginx.yml via SSH to 127.0.0.1:2222
05:25:01Z  RECOVERY_CONFIRMED    event_id=28
```

Evidence: [`integration-test/evidence/`](integration-test/evidence/)

### Limitations

- **Container target, not bare-metal.** Ansible manages a Docker container (no systemd — falls back to direct `nginx` command). On a real host with systemd the playbook uses `systemd_service` natively.
- **ARM64 Mac: no Zabbix agent.** Uses server-side simple checks instead. On x86 Linux, a Zabbix agent2 on the target would provide richer metrics.
- **SQLite only.** Suitable for a single-campus deployment; production at scale would need PostgreSQL.

## Docs

[Architecture](docs/ARCHITECTURE.md) · [Lab Setup](docs/LAB_SETUP.md) · [Test Report](docs/TEST_REPORT.md) · [Roadmap](docs/ROADMAP.md) · [Skill Mapping](docs/SKILL_MAPPING.md)

## Ownership

This project was designed and built by Yi Wang as a portfolio demonstration. The application code, tests, Ansible playbook, Zabbix webhook script, Docker configuration, and documentation are original work. It uses the following upstream software: FastAPI, SQLite, Zabbix (webhook integration only), and Ansible — each with their own licenses.

## License

[MIT](LICENSE). Zabbix, Ansible, and FastAPI are independent projects with their own licenses.
