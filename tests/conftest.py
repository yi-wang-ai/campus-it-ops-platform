import pytest
from fastapi.testclient import TestClient
from app.main import app

WEBHOOK_SECRET = "test-webhook-only-secret-000001"
VIEWER_SECRET = "test-viewer-only-secret-000002"
ADMIN_SECRET = "test-admin-only-secret-0000003"
DASH_SECRET = "test-dashboard-password-000004"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "incidents.sqlite"))
    monkeypatch.setenv("ZABBIX_WEBHOOK_TOKEN", WEBHOOK_SECRET)
    monkeypatch.setenv("VIEWER_API_TOKEN", VIEWER_SECRET)
    monkeypatch.setenv("ADMIN_API_TOKEN", ADMIN_SECRET)
    monkeypatch.setenv("DASHBOARD_USERNAME", "tester")
    monkeypatch.setenv("DASHBOARD_PASSWORD", DASH_SECRET)
    monkeypatch.setenv("LAB_ALLOWED_HOSTS", "lab-vm-01")
    with TestClient(app) as test_client:
        yield test_client
