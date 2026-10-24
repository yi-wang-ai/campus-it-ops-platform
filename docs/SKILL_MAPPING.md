# Skills demonstrated — provisional network/operations/backend role

**Note:** The original BOSS job page did not provide a verifiable full job description. This is a skill-category mapping, not a fabricated exact JD checklist.

| Skill | Project artifact | Verification |
| --- | --- | --- |
| Linux service operations | `ansible/recover-nginx.yml`, `docs/LAB_SETUP.md` | Real SSH recovery **pending** |
| Zabbix alerts, incident triage | `zabbix/webhook.js`, `app/main.py` | Simulated tested; live Zabbix **pending** |
| Operational automation | `app/operator.py`, Ansible playbook | CLI tests passed; live target **pending** |
| Python backend / REST | FastAPI routes, Pydantic validation | Automated API tests |
| Data persistence / transactions | SQLite with unique constraints and `BEGIN IMMEDIATE` | Concurrency/idempotency tests |
| Observability | Dashboard, stats API, audit trail | Local tests and screenshot |
| Secure operations | Four distinct credentials, Basic-auth UI, allowlist | Security tests |
| Docker fundamentals | `Dockerfile`, `compose.yaml` | Static review; build/runtime **pending** |
| CI/CD | `.github/workflows/ci.yml` | Workflow authored; GitHub green run **pending** |
| Networking | Monitoring path, webhook transport, SSH inventory | Network debugging lab **pending** |

**Not covered:** Deep routing/switching, firewall administration, large-scale HA, commercial enterprise service operation, C programming, production Kubernetes. Add only what the verified position actually asks for.
