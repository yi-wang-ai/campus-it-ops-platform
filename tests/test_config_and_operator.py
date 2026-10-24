import os
import subprocess

import pytest

from app.main import check_config, validated_secret
from app import operator
from .conftest import VIEWER_SECRET, ADMIN_SECRET


def test_weak_secret_fails_closed(monkeypatch):
    monkeypatch.setenv("ZABBIX_WEBHOOK_TOKEN", "weak")
    with pytest.raises(RuntimeError, match="ZABBIX_WEBHOOK_TOKEN"):
        check_config()


def test_shared_secrets_refused(monkeypatch):
    monkeypatch.setenv("ZABBIX_WEBHOOK_TOKEN", "a" * 30)
    monkeypatch.setenv("VIEWER_API_TOKEN", "a" * 30)
    monkeypatch.setenv("ADMIN_API_TOKEN", "b" * 30)
    monkeypatch.setenv("DASHBOARD_PASSWORD", "c" * 30)
    monkeypatch.setenv("DASHBOARD_USERNAME", "operator")
    with pytest.raises(RuntimeError, match="distinct"):
        check_config()


def test_build_command_restricts_inventory_host(tmp_path, monkeypatch):
    inventory = tmp_path / "inventory.ini"
    inventory.write_text("[webservers]\nlab-vm-01\n")
    monkeypatch.setenv("LAB_ALLOWED_HOSTS", "lab-vm-01")
    command = operator.build_command("lab-vm-01", inventory)
    assert command[-2:] == ["--limit", "lab-vm-01"]
    for host in ("other", "anything;rm -rf /", "-bad"):
        with pytest.raises(ValueError):
            operator.build_command(host, inventory)


def test_operator_requires_approval_and_host_confirmation(tmp_path, monkeypatch):
    inventory = tmp_path / "inventory.ini"
    inventory.write_text("[webservers]\nlab-vm-01\n")
    posts = []
    record = {"status": "OPEN", "host": "lab-vm-01"}

    def fake_api(method, path, payload=None):
        if method == "GET":
            return record
        posts.append(payload)
        return {"status": "REPAIR_RECORDED"}

    monkeypatch.setattr(operator, "api", fake_api)
    monkeypatch.setenv("LAB_ALLOWED_HOSTS", "lab-vm-01")
    with pytest.raises(ValueError, match="APPROVED"):
        operator.execute(12, inventory=inventory, run=True, confirm_host="lab-vm-01")
    record["status"] = "APPROVED"
    dry = operator.execute(12, inventory=inventory, run=False, confirm_host=None)
    assert dry["mode"] == "dry-run" and posts == []
    with pytest.raises(ValueError, match="confirm-host"):
        operator.execute(12, inventory=inventory, run=True, confirm_host="incorrect")
    assert posts == []

    def success_run(*args, **kwargs):
        assert args[0][-2:] == ["--limit", "lab-vm-01"]
        assert kwargs["check"] is False and kwargs["timeout"] == 180
        return subprocess.CompletedProcess(args[0], 0, stdout="ok", stderr="")

    monkeypatch.setattr(operator.subprocess, "run", success_run)
    result = operator.execute(12, inventory=inventory, run=True, confirm_host="lab-vm-01")
    assert result["ansible_success"] is True
    assert posts[-1]["success"] is True


def test_operator_failure_is_recorded(tmp_path, monkeypatch):
    inventory = tmp_path / "inventory.ini"
    inventory.write_text("[webservers]\nlab-vm-01\n")
    monkeypatch.setenv("LAB_ALLOWED_HOSTS", "lab-vm-01")
    monkeypatch.setattr(operator, "api", lambda method, path, payload=None: (
        {"status": "APPROVED", "host": "lab-vm-01"} if method == "GET"
        else {"status": "REPAIR_FAILED"}))
    monkeypatch.setattr(operator.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 2))
    result = operator.execute(1, inventory=inventory, run=True, confirm_host="lab-vm-01")
    assert result["recorded_status"] == "REPAIR_FAILED"


def test_operator_rejects_plain_http_nonlocal(monkeypatch):
    monkeypatch.setenv("OPS_API_URL", "http://example.org:8000")
    monkeypatch.setenv("VIEWER_API_TOKEN", VIEWER_SECRET)
    with pytest.raises(ValueError, match="loopback HTTP"):
        operator.api("GET", "/api/v1/incidents/1")


def test_operator_api_sends_role_specific_headers(monkeypatch):
    import io
    import json
    from urllib import request

    monkeypatch.setenv("OPS_API_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("VIEWER_API_TOKEN", VIEWER_SECRET)
    monkeypatch.setenv("ADMIN_API_TOKEN", ADMIN_SECRET)
    observed = []

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *a):
            self.close()

    def fake_urlopen(req, timeout):
        observed.append((req.get_method(), dict(req.header_items()), req.data))
        return FakeResponse(json.dumps({"status": "APPROVED"}).encode())

    monkeypatch.setattr(request, "urlopen", fake_urlopen)
    assert operator.api("GET", "/api/v1/incidents/1")["status"] == "APPROVED"
    assert operator.api("POST", "/api/v1/incidents/1/repair-result",
                        {"success": True})["status"] == "APPROVED"
    assert observed[0][1]["X-viewer-token"] == VIEWER_SECRET
    assert observed[1][1]["X-admin-token"] == ADMIN_SECRET
    assert b'"success": true' in observed[1][2]


def test_operator_timeout_records_failure(tmp_path, monkeypatch):
    inventory = tmp_path / "inventory.ini"
    inventory.write_text("[webservers]\nlab-vm-01\n")
    monkeypatch.setenv("LAB_ALLOWED_HOSTS", "lab-vm-01")
    posted = []
    def fake_api(method, path, payload=None):
        if method == "GET":
            return {"status": "APPROVED", "host": "lab-vm-01"}
        posted.append(payload)
        return {"status": "REPAIR_FAILED"}
    monkeypatch.setattr(operator, "api", fake_api)
    def timeout(*a, **kw):
        raise subprocess.TimeoutExpired("ansible-playbook", 180)
    monkeypatch.setattr(operator.subprocess, "run", timeout)
    assert operator.execute(10, inventory=inventory, run=True,
                            confirm_host="lab-vm-01")["ansible_success"] is False
    assert posted[0]["success"] is False
    assert "TimeoutExpired" in posted[0]["details"]


def test_dashboard_config_needs_username(monkeypatch):
    monkeypatch.setenv("ZABBIX_WEBHOOK_TOKEN", "a" * 30)
    monkeypatch.setenv("VIEWER_API_TOKEN", "b" * 30)
    monkeypatch.setenv("ADMIN_API_TOKEN", "c" * 30)
    monkeypatch.setenv("DASHBOARD_PASSWORD", "d" * 30)
    monkeypatch.delenv("DASHBOARD_USERNAME", raising=False)
    with pytest.raises(RuntimeError, match="DASHBOARD_USERNAME"):
        check_config()
