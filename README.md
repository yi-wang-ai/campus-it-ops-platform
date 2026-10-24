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

![Dashboard](docs/images/dashboard-local-demo.png)

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

## Docs

[Architecture](docs/ARCHITECTURE.md) · [Lab Setup](docs/LAB_SETUP.md) · [Test Report](docs/TEST_REPORT.md) · [Roadmap](docs/ROADMAP.md) · [Skill Mapping](docs/SKILL_MAPPING.md)

## License

[MIT](LICENSE). Zabbix, Ansible, and FastAPI are independent projects with their own licenses.
