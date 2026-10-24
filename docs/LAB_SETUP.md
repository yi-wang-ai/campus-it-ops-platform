# Real lab setup — manual validation required

Only use virtual machines and services you own or have permission to test. **Do not stop real university or production systems.** The following steps are a lab recipe, **not** a claim that this end-to-end deployment was executed in the build environment.

## Topology

- Operator workstation: Python, Ansible, this FastAPI app.
- VM: Ubuntu with systemd, nginx, Zabbix Agent, SSH/sudo access for a controlled Ansible account.
- Zabbix server: self-hosted lab Zabbix 7.4 or a compatible supported version, able to reach the FastAPI webhook over a secure private path.

Zabbix and FastAPI cannot communicate across containers using each other's `127.0.0.1`. If using Docker, create an explicit shared private Docker network or proxy the endpoint through authenticated TLS. Keep the operator API off the public internet.

## Step 1 — nginx and monitoring

On the disposable Ubuntu VM:

```bash
sudo apt-get update
sudo apt-get install -y nginx
sudo systemctl enable --now nginx
systemctl is-active nginx
curl -f http://127.0.0.1/
```

Install and configure the Zabbix Agent according to your Zabbix server version and your operating system. Add a Zabbix host whose name **exactly matches** the corresponding Ansible inventory label (for example `lab-vm-01`). Configure an HTTP service item or an equivalent Zabbix check and a trigger for nginx unavailability. Verify that Zabbix can display the host's actual monitoring data first.

## Step 2 — Zabbix webhook

Create a webhook media type, paste [`zabbix/webhook.js`](../zabbix/webhook.js), and add parameters:

| Parameter | Example value |
| --- | --- |
| `url` | `https://YOUR-PRIVATE-LAB-ENDPOINT/api/v1/alerts/zabbix` |
| `token` | `ZABBIX_WEBHOOK_TOKEN` secret (actual value, not literal name) |
| `event_id` | `{EVENT.ID}` |
| `recovery_event_id` | `{EVENT.RECOVERY.ID}` |
| `host` | `{HOST.NAME}` |
| `trigger_id` | `{TRIGGER.ID}` |
| `subject` | `{EVENT.NAME}` |
| `event_value` | `{EVENT.VALUE}` |
| `severity` | `{EVENT.SEVERITY}` |
| `http_proxy` | optional; empty unless your lab needs it |

Configure a Zabbix action that sends **both problem and recovery operations**, with a recipient that uses the media type. Validate macro values with test notifications. For recovery notifications, the original problem ID should be `EVENT.ID`, and `EVENT.RECOVERY.ID` should identify the recovery event. Official references: [Zabbix webhook guidelines](https://www.zabbix.com/documentation/guidelines/en/webhooks) and [Zabbix macro documentation](https://www.zabbix.com/documentation/7.4/en/manual/config/macros/supported_by_location).

## Step 3 — Ansible inventory and dry-run

On the operator Linux host:

```bash
cp ansible/inventory.ini.example ansible/inventory.ini
# Edit the inventory with an actual private VM address and SSH user.
ansible -i ansible/inventory.ini webservers -m ping
ansible-playbook -i ansible/inventory.ini ansible/recover-nginx.yml --syntax-check
```

Set `LAB_ALLOWED_HOSTS` to the exact inventory hostname(s); change from `lab-vm-01` only if your own lab inventory uses a different name. Ensure the SSH user has reviewed, appropriately limited sudo access.

## Step 4 — controlled failure, approval and restoration

1. Start Zabbix monitoring while nginx is healthy; show a green state.
2. On **that lab VM only**, run `sudo systemctl stop nginx`.
3. Wait for a Zabbix PROBLEM event and verify the FastAPI incident is `OPEN`.
4. Review the alert and approve it via Swagger, using `X-Admin-Token`, or via a documented API request.
5. Run `python -m app.operator --incident <ID> --inventory ansible/inventory.ini` first, with no `--execute`.
6. Execute **only after approval**, adding `--execute --confirm-host lab-vm-01`.
7. Verify nginx using `systemctl is-active nginx` and `curl -f http://127.0.0.1/` on the lab VM.
8. Wait for Zabbix to send its OK notification. The incident must be `RESOLVED`, with recovery event ID and audit trail.

Capture timestamps/screenshots from this actual run. If any check fails, log the error and stop rather than inventing a successful result. Test one failed repair (e.g. deliberately disconnect the isolated lab VM), then use a new approval before retrying.

## Security note

The lab service is not a general repair agent. It accepts no remote shell command or arbitrary playbook upload. Do not put SSH keys in the container, dashboard, repository or webhook configuration.
