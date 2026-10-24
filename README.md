# Campus IT Operations Platform

A monitoring and incident-management system for campus IT infrastructure. When a server or service goes down, the platform detects the failure, creates an incident, lets an operator approve a repair, runs the fix, and confirms recovery — all with a complete audit trail.

Built with **Zabbix** (monitoring), **Ansible** (automated repair), **FastAPI** (incident backend), and **SQLite** (storage).

![Dashboard screenshot](docs/images/dashboard-local-demo.png)

## How It Works

```
Service fails → Zabbix detects it → Webhook creates an incident
                                            ↓
                                    Operator reviews and approves
                                            ↓
                                    Ansible runs the recovery playbook
                                            ↓
                                    Zabbix confirms service is back
                                            ↓
                                    Incident resolved, audit trail saved
```

A webhook **never** triggers a repair directly. Repairs require human approval. A repair result alone does not close an incident — only a Zabbix recovery confirmation does.

## What's Inside

| Component | What it does |
|-----------|-------------|
| `app/main.py` | FastAPI backend — receives alerts, manages incidents, serves the dashboard |
| `app/db.py` | SQLite database with transactions, schema, and indexes |
| `app/operator.py` | CLI tool that runs approved Ansible playbooks with safety checks |
| `ansible/` | Recovery playbook for nginx, with inventory host restrictions |
| `zabbix/` | JavaScript webhook script for Zabbix alert forwarding |
| `tests/` | 30 automated tests covering the full incident lifecycle |

## Quick Start

**Requirements:** Python 3.11+

```bash
# Set up
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env

# Generate four different secrets (run this four times, paste each into .env)
python -c 'import secrets; print(secrets.token_urlsafe(36))'

# Run
set -a && source .env && set +a
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open:
- **Dashboard:** http://127.0.0.1:8000/ (sign in with your `.env` credentials)
- **API docs:** http://127.0.0.1:8000/docs
- **Simulated demo:** run `bash scripts/demo-api.sh` in another terminal

## Run the Tests

```bash
python -m pytest -v --cov=app
```

All 30 tests pass on Python 3.11, 3.12, and 3.13. GitHub Actions CI runs them automatically on every push.

## End-to-End Incident Flow

The core demonstration covers this scenario:

1. **Failure** — A Linux service (nginx) stops running.
2. **Detection** — Zabbix triggers an alert and sends a webhook.
3. **Incident created** — The backend receives the alert, deduplicates it, and creates an incident (status: `OPEN`).
4. **Approval** — An operator reviews and approves the repair (status: `APPROVED`).
5. **Repair** — Ansible runs a fixed recovery playbook against the approved host (status: `REPAIR_RECORDED` or `REPAIR_FAILED`).
6. **Recovery confirmed** — Zabbix sends an OK notification matching the original problem (status: `RESOLVED`).
7. **Audit complete** — Every step is recorded with timestamps.

Failed repairs require re-approval. Duplicate alerts are detected and ignored. Ambiguous recoveries are rejected unless the original problem ID is provided.

## Docker

```bash
docker compose up --build -d
curl http://127.0.0.1:8000/readyz
```

Binds to localhost only. Runs as non-root with a read-only filesystem.

## Setting Up a Real Lab

To test with actual Zabbix monitoring and Ansible recovery on a Linux VM, follow [docs/LAB_SETUP.md](docs/LAB_SETUP.md).

The operator CLI has built-in safety:
- Only a fixed playbook (`recover-nginx.yml`) can run
- Target hosts must be in `LAB_ALLOWED_HOSTS`
- `--confirm-host` must match the incident's host
- Dry-run is the default; `--execute` is opt-in

```bash
# Dry run (safe, no SSH)
python -m app.operator --incident 1 --inventory ansible/inventory.ini

# Execute (lab environment only)
python -m app.operator --incident 1 --inventory ansible/inventory.ini \
  --execute --confirm-host lab-vm-01
```

## Security Model

- **Four separate tokens** for webhook, viewer API, admin API, and dashboard login
- Weak or shared secrets are rejected at startup
- All alert text is HTML-escaped in the dashboard (XSS protection)
- Security headers: `X-Frame-Options: DENY`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`
- No shell injection — Ansible commands use fixed argv, never `shell=True`
- Concurrent webhook deliveries are serialized with `BEGIN IMMEDIATE`

## Project Structure

```
app/                        FastAPI backend, database, operator CLI
ansible/                    Recovery playbook + example inventory
zabbix/                     Zabbix JavaScript webhook
scripts/                    Demo script + webhook tests
tests/                      30 automated tests
docs/                       Architecture, lab setup, roadmap, skill mapping
.github/workflows/          CI pipeline
Dockerfile, compose.yaml    Container packaging
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — system design and data flow
- [Lab Setup](docs/LAB_SETUP.md) — deploying with real Zabbix and Ansible
- [Skill Mapping](docs/SKILL_MAPPING.md) — which skills this project demonstrates
- [Test Report](docs/TEST_REPORT.md) — what has been tested and what remains
- [Roadmap](docs/ROADMAP.md) — planned improvements
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Changelog](CHANGELOG.md)

## License

Project code: [MIT](LICENSE). Zabbix, Ansible, and FastAPI are independent upstream projects with their own licenses — their source is not included here.
