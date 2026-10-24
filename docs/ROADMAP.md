# Roadmap and acceptance criteria

## v1.0 — locally implemented and automated tests available

- [x] Zabbix webhook parser + synthetic PROBLEM/OK tests.
- [x] FastAPI with incident lifecycle and durable single-process SQLite.
- [x] Token-protected webhook, read endpoints, admin actions, Basic-auth dashboard.
- [x] Idempotent problem/recovery, exact correlation and ambiguous-recovery rejection.
- [x] Approval gate, audit records, human-only allowlisted repair CLI.
- [x] Fixed nginx recovery playbook and safe simulation script.
- [x] Automated API tests and GitHub Actions configuration.
- [x] GitHub README, architecture, security, issue templates and demo screenshot.

## v1.1 — requires YOUR Ubuntu/Zabbix test environment

- [ ] Actual Zabbix PROBLEM and recovery operation reaches webhook.
- [ ] Real Ansible playbook repairs lab nginx over SSH.
- [ ] Failure/retry scenario reproduced with incident logs and timestamps.
- [ ] Docker build/start/healthcheck confirmed on a machine with Docker.
- [ ] CI status confirmed green in your published GitHub repository.
- [ ] Screenshots/video replaced or extended with real lab infrastructure evidence.

## Future enhancements (ONLY if actual job requires them)

- [ ] PostgreSQL with migrations and backup/restore drills.
- [ ] OAuth2/SSO, role-based authorization, TLS termination and alert rate limiting.
- [ ] Alert queue and retry handling for multi-instance deployments.
- [ ] AWX approvals if the role explicitly involves operational orchestration.
- [ ] Containerlab/FRRouting if JD lists routing, VLANs, firewalls, switching.
- [ ] Java/Spring Boot incident backend if JD explicitly requires Java.

## Definition of interview-ready

The operator can reproduce a lab fault, observe an authenticated alert, approve a repair, run Ansible, watch recovery and explain: event correlation, idempotency, trust boundaries, transaction handling, SSH inventory restrictions, and why a repair success does not by itself imply monitoring recovery.
