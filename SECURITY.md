# Security policy

This is an **educational, isolated lab**. Do not attach the service to production networks or provide public internet access. The author does not claim security certification or production readiness.

- Keep `.env`, inventory, SSH keys and production details out of Git.
- Keep webhook, viewer, admin and dashboard passwords **distinct** and at least 24 characters.
- Do not use HTTP Basic on unencrypted networks. Default Compose binds only to loopback.
- The dashboard and read endpoints are authenticated, but there is no multi-user RBAC, SSO, rate limiter, WAF, TLS termination or audit-log tamper resistance.
- Incoming webhook events never execute commands; repairs are human initiated only.
- `app/operator.py` uses a fixed playbook and hostname allowlist; `--execute` and `--confirm-host` are required to run it.
- The Ansible playbook uses SSH and sudo; use only owned disposable lab machines and least-privilege sudo configurations.
- SQLite is for single-host training, not horizontal scaling. Back up and protect database files.
- Do not report a simulated workflow as a production recovery.

If publishing on GitHub, report suspected security issues using a private GitHub security advisory if enabled on the repository; otherwise avoid posting credentials or exploit details publicly.
