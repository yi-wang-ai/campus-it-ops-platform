"""Operator-only, fixed-playbook Ansible launcher.

No remote command or playbook path comes from a Zabbix event. An operator
must approve via the API and explicitly confirm the target hostname locally.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib import error, request

PLAYBOOK = Path(__file__).resolve().parents[1] / "ansible" / "recover-nginx.yml"
HOST_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}\Z")


def api(method: str, path: str, payload=None):
    base = os.environ.get("OPS_API_URL", "http://127.0.0.1:8000").rstrip("/")
    if not (base.startswith("http://127.0.0.1:") or base.startswith("http://localhost:")
            or base.startswith("https://")):
        raise ValueError("OPS_API_URL must use loopback HTTP or HTTPS")
    token_name = "VIEWER_API_TOKEN" if method == "GET" else "ADMIN_API_TOKEN"
    token = os.environ.get(token_name, "")
    if len(token) < 24:
        raise ValueError(f"Configure {token_name}")
    headers = {"X-Viewer-Token" if method == "GET" else "X-Admin-Token": token}
    content = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        content = json.dumps(payload).encode("utf-8")
    req = request.Request(base + path, data=content, headers=headers, method=method)
    with request.urlopen(req, timeout=15) as result:
        return json.load(result)


def build_command(host: str, inventory: Path) -> list[str]:
    if not HOST_RE.fullmatch(host):
        raise ValueError("Invalid inventory host label")
    allowed = {h.strip() for h in os.getenv("LAB_ALLOWED_HOSTS", "").split(",") if h.strip()}
    if not allowed or host not in allowed:
        raise ValueError("Host not in LAB_ALLOWED_HOSTS")
    if not inventory.is_file():
        raise FileNotFoundError(f"Inventory file missing: {inventory}")
    if not PLAYBOOK.is_file():
        raise FileNotFoundError("Fixed nginx recovery playbook missing")
    return ["ansible-playbook", "-i", str(inventory.resolve()), str(PLAYBOOK),
            "--limit", host]


def execute(incident_id: int, *, inventory: Path, run: bool, confirm_host: str | None):
    item = api("GET", f"/api/v1/incidents/{incident_id}")
    if item["status"] != "APPROVED":
        raise ValueError("Incident must be APPROVED before running a playbook")
    host = item["host"]
    command = build_command(host, inventory)
    if not run:
        return {"mode": "dry-run", "incident_id": incident_id, "host": host,
                "command": command, "note": "No Ansible task was executed"}
    if confirm_host != host:
        raise ValueError("Use --confirm-host matching the incident host for execution")
    # Fixed command argv. No shell=True and no remotely supplied script or arguments.
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=180, check=False)
        success = completed.returncode == 0
        detail = "Ansible nginx playbook exit code " + str(completed.returncode)
    except (OSError, subprocess.TimeoutExpired) as exc:
        success = False
        detail = f"Ansible execution failed: {type(exc).__name__}"
    outcome = api("POST", f"/api/v1/incidents/{incident_id}/repair-result",
                  {"success": success, "details": detail})
    return {"mode": "execute", "incident_id": incident_id, "host": host,
            "ansible_success": success, "recorded_status": outcome["status"],
            "note": "Zabbix must confirm recovery before the incident is resolved"}


def main():
    parser = argparse.ArgumentParser(description="Run only the fixed, approved nginx lab repair")
    parser.add_argument("--incident", type=int, required=True)
    parser.add_argument("--inventory", type=Path, default=Path("ansible/inventory.ini"))
    parser.add_argument("--execute", action="store_true", help="Perform real SSH/Ansible repair")
    parser.add_argument("--confirm-host", help="Must exactly match the approved incident hostname")
    args = parser.parse_args()
    try:
        outcome = execute(args.incident, inventory=args.inventory, run=args.execute,
                          confirm_host=args.confirm_host)
        print(json.dumps(outcome, indent=2))
        return 0 if not args.execute or outcome["ansible_success"] else 1
    except (ValueError, OSError, error.HTTPError, error.URLError) as exc:
        print(f"Operator stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
