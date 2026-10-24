#!/usr/bin/env bash
# Safe HTTP demo only. NO Linux service is stopped and NO Ansible job is run.
set -euo pipefail
: "${ZABBIX_WEBHOOK_TOKEN:?Load .env first}"
: "${VIEWER_API_TOKEN:?Load .env first}"
: "${ADMIN_API_TOKEN:?Load .env first}"
BASE="${BASE:-http://127.0.0.1:8000}"
EVENT="demo-$(date +%s)-$$"
PAYLOAD=$(printf '{"event_id":"%s","host":"lab-vm-01","trigger_id":"nginx-demo","name":"nginx unavailable (SIMULATED)","state":"PROBLEM","severity":"High"}' "$EVENT")
INCIDENT=$(curl -fsS -H 'Content-Type: application/json' -H "X-Webhook-Token: $ZABBIX_WEBHOOK_TOKEN" -d "$PAYLOAD" "$BASE/api/v1/alerts/zabbix" | python -c 'import json,sys; print(json.load(sys.stdin)["incident_id"])')
echo "Incident created: $INCIDENT"
curl -fsS -X POST -H "X-Admin-Token: $ADMIN_API_TOKEN" "$BASE/api/v1/incidents/$INCIDENT/approve"
echo
curl -fsS -X POST -H "X-Admin-Token: $ADMIN_API_TOKEN" -H 'Content-Type: application/json' -d '{"success":true,"details":"SIMULATED operator action — no Ansible run"}' "$BASE/api/v1/incidents/$INCIDENT/repair-result"
echo
RECOVERY=$(printf '{"event_id":"%s-ok","problem_event_id":"%s","host":"lab-vm-01","trigger_id":"nginx-demo","name":"nginx restored (SIMULATED)","state":"OK","severity":"Info"}' "$EVENT" "$EVENT")
curl -fsS -H 'Content-Type: application/json' -H "X-Webhook-Token: $ZABBIX_WEBHOOK_TOKEN" -d "$RECOVERY" "$BASE/api/v1/alerts/zabbix"
echo
curl -fsS -H "X-Viewer-Token: $VIEWER_API_TOKEN" "$BASE/api/v1/incidents/$INCIDENT" | python -m json.tool
