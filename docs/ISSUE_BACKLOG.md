# Suggested GitHub issues (remaining real-lab work)

These are **not complete**. Create GitHub issues after publishing the repository, then attach genuine test logs or screenshots for each acceptance criterion.

1. **Validate Zabbix 7.4 real webhook event correlation** — configure media/actions, document `{EVENT.ID}` and `{EVENT.RECOVERY.ID}` values, demonstrate both notifications and duplicate delivery behavior.
2. **Repair owned nginx VM with Ansible** — verify SSH inventory, syntax-check, approved run, nginx service health and correct no-repair-without-approval behavior.
3. **Reproduce repair failure and retry** — disconnect owned VM, record `REPAIR_FAILED`, reapprove and recover safely.
4. **Validate Docker runtime** — run `docker compose config`, build, start with new secrets, restart, verify persistence and capture logs.
5. **Confirm GitHub Actions green** — run Python matrix, JavaScript tests and Ansible syntax check on GitHub, fix any environment-specific failures.
6. **Create real showcase video** — record failure→Zabbix alert→dashboard→approval→Ansible recovery→Zabbix OK. Clearly label synthetic vs real environment.
7. **Optional production study** — PostgreSQL, external TLS reverse proxy, SSO/RBAC, migration/backups and multi-node job queue, only if the employer actually requires them.
