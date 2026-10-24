# Verification report — v1.0.0

**Executed:** 2026-10-24, in the supplied Linux development container.

## Completed checks

| Check | Actual result |
| --- | --- |
| Python API, authorization, state machine, duplicate delivery, ambiguous recovery and operator tests | **30 passed** (pytest) |
| Python statement coverage, `app/` | **93%** (pytest-cov) |
| Zabbix webhook JavaScript simulation | **4 passed** (Node 22) |
| Python module compilation | **Passed** (`python -m compileall -q app`) |
| Python package build | **Passed** (`pip wheel --no-deps --no-build-isolation`) |
| YAML syntax: Compose, GitHub Actions and Ansible playbook | **Passed** (`yaml.safe_load`, static syntax only) |
| JavaScript syntax | **Passed** (`node --check`) |
| Live localhost HTTP flow via uvicorn + curl | **Passed** (simulated incident created, approved, repair recorded, and Zabbix-style OK event resolved it) |
| Live localhost stats API via HTTPX | **Passed** (1 simulated incident, 1 resolved) |
| HTML dashboard and incident detail screenshot | **Rendered from real application HTML, synthetic data** (Chromium) |

Example test output:

```text
30 passed
TOTAL 270 statements, 19 missed, 93% coverage
Zabbix webhook tests: 4 passed
Live localhost demo: incident created → approved → repair recorded → RESOLVED
```

The screenshot browser rendered HTML returned by the running application; the headless browser did **not** connect directly to localhost because the container's Chromium policy blocks that address. This distinction does not affect the HTTP API result but is recorded for reproducibility.

## Not executed in this environment

- **Docker build/runtime:** No Docker daemon or CLI was available. YAML was parsed and Dockerfile reviewed, not tested as a running container.
- **Real Zabbix server/agent:** Not installed or reachable. JavaScript webhook tested with a deterministic JavaScript stub, not the Zabbix server engine.
- **Ansible syntax/execution:** `ansible-playbook` was not installed locally. The playbook YAML parses, and CI is configured to perform a real syntax check; no SSH execution was performed.
- **External networking / real VM outage:** No real service was stopped. The demo posts simulated failure and recovery messages.
- **GitHub Actions CI:** The workflow is authored; its real status can only be confirmed after the repository is published and Actions runs.

## Reproduce locally

```bash
python -m pip install -e '.[dev]'
python -m pytest -q --cov=app --cov-report=term-missing
node scripts/test-webhook.cjs
python -m compileall -q app
# After configuring local secrets and starting uvicorn:
bash scripts/demo-api.sh
```

The 93% figure is **unit/integration statement coverage**, not 93% match to a job or 93% proven infrastructure reliability. Do not claim end-to-end real Zabbix/Ansible success until the real lab procedure in `LAB_SETUP.md` is performed.
