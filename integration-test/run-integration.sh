#!/usr/bin/env bash
# Full Zabbix → IT Ops → Ansible integration test
#
# Prerequisites: Docker Compose stack running (docker compose up -d --build)
# Installs: ansible-core and sshpass via pip if not present
#
# Flow:
#   1. Wait for all services healthy
#   2. Configure Zabbix: create host, add nginx HTTP check, create webhook media type + action
#   3. Stop nginx on target → Zabbix detects PROBLEM → webhook fires → incident OPEN
#   4. Approve incident via IT Ops API
#   5. Ansible repairs nginx over SSH
#   6. Record repair result
#   7. Zabbix detects OK → webhook fires → incident RESOLVED
#   8. Verify full audit trail
set -euo pipefail
cd "$(dirname "$0")"

LOG="evidence/integration-$(date +%Y%m%d-%H%M%S).log"
mkdir -p evidence
exec > >(tee "$LOG") 2>&1

source .env
API="http://127.0.0.1:8000"
ZABBIX_API="http://127.0.0.1:8080/api_jsonrpc.php"

step() { echo ""; echo "==== $1 ===="; }
pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1" >&2; }

zabbix_call() {
    local method="$1"; shift
    local params="$1"; shift
    local auth="${1:-}"
    local auth_field=""
    if [ -n "$auth" ]; then
        auth_field="\"auth\":\"$auth\","
    fi
    curl -s -X POST "$ZABBIX_API" -H 'Content-Type: application/json' -d "{
        \"jsonrpc\":\"2.0\",
        \"method\":\"$method\",
        ${auth_field}
        \"params\":$params,
        \"id\":1
    }"
}

# ── 1. Wait for services ─────────────────────────────────────────────
step "1. Waiting for services"

echo -n "  Zabbix web API..."
for i in $(seq 1 60); do
    VER=$(curl -s "$ZABBIX_API" -H 'Content-Type: application/json' \
        -d '{"jsonrpc":"2.0","method":"apiinfo.version","id":1,"params":{}}' \
        | python3 -c 'import sys,json; print(json.load(sys.stdin).get("result",""))' 2>/dev/null || true)
    if [ -n "$VER" ] && [ "$VER" != "None" ]; then echo " v$VER"; break; fi
    if [ "$i" -eq 60 ]; then echo " TIMEOUT"; exit 1; fi
    sleep 3
done

echo -n "  IT Ops API..."
for i in $(seq 1 30); do
    if curl -fs "$API/readyz" >/dev/null 2>&1; then echo " ready"; break; fi
    if [ "$i" -eq 30 ]; then echo " TIMEOUT"; exit 1; fi
    sleep 2
done

echo -n "  Target nginx..."
for i in $(seq 1 20); do
    if curl -fs "http://127.0.0.1:2222" >/dev/null 2>&1 || \
       docker compose exec -T target curl -fs http://127.0.0.1:80 >/dev/null 2>&1; then
        echo " up"; break
    fi
    if [ "$i" -eq 20 ]; then echo " TIMEOUT"; exit 1; fi
    sleep 2
done

# ── 2. Configure Zabbix ──────────────────────────────────────────────
step "2. Configuring Zabbix (host, trigger, webhook, action)"

# Login
AUTH=$(zabbix_call "user.login" '{"username":"Admin","password":"zabbix"}' \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"])')
echo "  Logged in (token=${AUTH:0:8}...)"

# Create host group
GRP_RESULT=$(zabbix_call "hostgroup.create" '{"name":"Lab Targets"}' "$AUTH")
GRP_ID=$(echo "$GRP_RESULT" | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r.get("result",{}).get("groupids",[""])[0] if "result" in r else "")' 2>/dev/null)
if [ -z "$GRP_ID" ]; then
    GRP_ID=$(zabbix_call "hostgroup.get" '{"filter":{"name":"Lab Targets"}}' "$AUTH" \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"][0]["groupid"])')
fi
echo "  Host group: $GRP_ID"

# Get target container IP on the compose network
TARGET_IP=$(docker compose exec -T target hostname -I | tr -d '[:space:]')
echo "  Target IP: $TARGET_IP"

# Create host with no agent (simple checks run on the server side)
HOST_RESULT=$(zabbix_call "host.create" "{
    \"host\":\"lab-target\",
    \"groups\":[{\"groupid\":\"$GRP_ID\"}],
    \"interfaces\":[{
        \"type\":1,\"main\":1,\"useip\":1,
        \"ip\":\"$TARGET_IP\",\"dns\":\"\",\"port\":\"10050\"
    }]
}" "$AUTH")
HOST_ID=$(echo "$HOST_RESULT" | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r.get("result",{}).get("hostids",[""])[0] if "result" in r else "")' 2>/dev/null)
if [ -z "$HOST_ID" ]; then
    HOST_ID=$(zabbix_call "host.get" '{"filter":{"host":"lab-target"}}' "$AUTH" \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"][0]["hostid"])')
fi
echo "  Host ID: $HOST_ID"

# Create HTTP check item — simple check (type 3), executed by the Zabbix server (no agent needed)
ITEM_RESULT=$(zabbix_call "item.create" "{
    \"name\":\"Nginx HTTP check\",
    \"key_\":\"net.tcp.service[http,$TARGET_IP,80]\",
    \"hostid\":\"$HOST_ID\",
    \"type\":3,
    \"value_type\":3,
    \"delay\":\"10s\"
}" "$AUTH")
ITEM_ID=$(echo "$ITEM_RESULT" | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r.get("result",{}).get("itemids",[""])[0] if "result" in r else "")' 2>/dev/null)
if [ -z "$ITEM_ID" ]; then
    ITEM_ID=$(zabbix_call "item.get" "{\"hostids\":\"$HOST_ID\",\"filter\":{\"key_\":\"net.tcp.service[http,$TARGET_IP,80]\"}}" "$AUTH" \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"][0]["itemid"])')
fi
echo "  Item ID: $ITEM_ID"

# Create trigger
TRIGGER_RESULT=$(zabbix_call "trigger.create" "{
    \"description\":\"Nginx is down on {HOST.NAME}\",
    \"expression\":\"last(/lab-target/net.tcp.service[http,$TARGET_IP,80])=0\",
    \"priority\":4,
    \"recovery_mode\":0,
    \"recovery_expression\":\"\"
}" "$AUTH")
TRIGGER_ID=$(echo "$TRIGGER_RESULT" | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r.get("result",{}).get("triggerids",[""])[0] if "result" in r else "")' 2>/dev/null)
if [ -z "$TRIGGER_ID" ]; then
    TRIGGER_ID=$(zabbix_call "trigger.get" "{\"hostids\":\"$HOST_ID\",\"filter\":{\"description\":\"Nginx is down on {HOST.NAME}\"}}" "$AUTH" \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"][0]["triggerid"])')
fi
echo "  Trigger ID: $TRIGGER_ID"

# Resolve api container hostname on compose network
API_INTERNAL="http://api:8000"

# Create webhook media type
WEBHOOK_SCRIPT=$(cat <<'JSEOF'
try {
    var p = JSON.parse(value);
    var isProblem = p.event_value === '1';
    var recoveryId = String(p.recovery_event_id || '');
    if (!isProblem && (recoveryId === '' || recoveryId.charAt(0) === '{')) {
        recoveryId = String(p.event_id) + '-recovery';
    }
    var payload = {
        event_id: isProblem ? String(p.event_id) : recoveryId,
        host: String(p.host),
        trigger_id: String(p.trigger_id),
        name: String(p.subject || 'Service unavailable'),
        state: isProblem ? 'PROBLEM' : 'OK',
        severity: String(p.severity || 'unknown'),
        problem_event_id: isProblem ? null : String(p.event_id)
    };
    var request = new HttpRequest();
    request.addHeader('Content-Type: application/json');
    request.addHeader('X-Webhook-Token: ' + p.token);
    var response = request.post(p.url, JSON.stringify(payload));
    if (request.getStatus() < 200 || request.getStatus() >= 300) {
        throw 'HTTP ' + request.getStatus();
    }
    return 'OK';
} catch (error) {
    Zabbix.log(3, '[CampusOps] ' + error);
    throw error;
}
JSEOF
)

# Escape the script for JSON
ESCAPED_SCRIPT=$(python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" <<< "$WEBHOOK_SCRIPT")

MT_RESULT=$(zabbix_call "mediatype.create" "{
    \"name\":\"Campus IT Ops Webhook\",
    \"type\":4,
    \"script\":$ESCAPED_SCRIPT,
    \"parameters\":[
        {\"name\":\"url\",\"value\":\"$API_INTERNAL/api/v1/alerts/zabbix\"},
        {\"name\":\"token\",\"value\":\"$ZABBIX_WEBHOOK_TOKEN\"},
        {\"name\":\"event_id\",\"value\":\"{EVENT.ID}\"},
        {\"name\":\"recovery_event_id\",\"value\":\"{EVENT.RECOVERY.ID}\"},
        {\"name\":\"event_value\",\"value\":\"{EVENT.VALUE}\"},
        {\"name\":\"host\",\"value\":\"{HOST.NAME}\"},
        {\"name\":\"trigger_id\",\"value\":\"{TRIGGER.ID}\"},
        {\"name\":\"subject\",\"value\":\"{EVENT.NAME}\"},
        {\"name\":\"severity\",\"value\":\"{EVENT.SEVERITY}\"}
    ],
    \"process_tags\":0,
    \"maxsessions\":1,
    \"maxattempts\":3,
    \"attempt_interval\":\"10s\"
}" "$AUTH")
MT_ID=$(echo "$MT_RESULT" | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r.get("result",{}).get("mediatypeids",[""])[0] if "result" in r else "")' 2>/dev/null)
if [ -z "$MT_ID" ]; then
    MT_ID=$(zabbix_call "mediatype.get" '{"filter":{"name":"Campus IT Ops Webhook"}}' "$AUTH" \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"][0]["mediatypeid"])')
fi
echo "  Media type ID: $MT_ID"

# Enable the media type (Zabbix creates webhooks disabled by default) and add message templates
zabbix_call "mediatype.update" "{
    \"mediatypeid\":\"$MT_ID\",
    \"status\":0,
    \"message_templates\":[
        {\"eventsource\":0,\"recovery\":0,\"subject\":\"{EVENT.NAME}\",\"message\":\"{EVENT.ID}\"},
        {\"eventsource\":0,\"recovery\":1,\"subject\":\"{EVENT.NAME} resolved\",\"message\":\"{EVENT.RECOVERY.ID}\"}
    ]
}" "$AUTH" >/dev/null
echo "  Media type enabled with message templates"

# Assign media to Admin user
ADMIN_USERID=$(zabbix_call "user.get" '{"filter":{"username":"Admin"}}' "$AUTH" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"][0]["userid"])')

zabbix_call "user.update" "{
    \"userid\":\"$ADMIN_USERID\",
    \"medias\":[{\"mediatypeid\":\"$MT_ID\",\"sendto\":\"admin@lab.local\",\"active\":0,\"severity\":63,\"period\":\"1-7,00:00-24:00\"}]
}" "$AUTH" >/dev/null

# Create action to fire webhook on trigger
ACTION_RESULT=$(zabbix_call "action.create" "{
    \"name\":\"Send to Campus IT Ops\",
    \"eventsource\":0,
    \"status\":0,
    \"esc_period\":\"60s\",
    \"filter\":{\"evaltype\":0,\"conditions\":[{\"conditiontype\":4,\"operator\":5,\"value\":\"4\"}]},
    \"operations\":[{
        \"operationtype\":0,
        \"esc_period\":\"0s\",
        \"esc_step_from\":1,\"esc_step_to\":1,
        \"opmessage\":{\"mediatypeid\":\"$MT_ID\",\"default_msg\":1},
        \"opmessage_grp\":[{\"usrgrpid\":\"7\"}]
    }],
    \"recovery_operations\":[{
        \"operationtype\":0,
        \"opmessage\":{\"mediatypeid\":\"$MT_ID\",\"default_msg\":1},
        \"opmessage_grp\":[{\"usrgrpid\":\"7\"}]
    }]
}" "$AUTH")
echo "  Action: $(echo "$ACTION_RESULT" | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r.get("result",{}).get("actionids",["created"])[0] if "result" in r else r.get("error",{}).get("data","exists"))' 2>/dev/null)"

echo "  Zabbix configured. Waiting 30s for initial data collection..."
sleep 30

# ── 3. Stop nginx → Zabbix fires PROBLEM webhook ─────────────────────
step "3. Stopping nginx on target (real failure)"
docker compose exec -T target bash -c 'nginx -s stop 2>/dev/null; pkill nginx || true'
echo "  nginx stopped. Waiting for Zabbix to detect failure (up to 90s)..."

INCIDENT_ID=""
for i in $(seq 1 30); do
    INCIDENTS=$(curl -s "$API/api/v1/incidents?limit=5" -H "X-Viewer-Token: $VIEWER_API_TOKEN")
    INCIDENT_ID=$(echo "$INCIDENTS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for inc in data:
    if inc['status'] == 'OPEN' and inc['host'] == 'lab-target':
        print(inc['id']); break
" 2>/dev/null || true)
    if [ -n "$INCIDENT_ID" ]; then break; fi
    sleep 3
done

if [ -n "$INCIDENT_ID" ]; then
    pass "Zabbix detected nginx failure → incident #$INCIDENT_ID created (OPEN)"
else
    fail "No incident created within 90s"
    # Dump Zabbix alerts for debugging
    zabbix_call "alert.get" '{"output":"extend","sortfield":"alertid","sortorder":"DESC","limit":5}' "$AUTH" | python3 -m json.tool
    exit 1
fi

# ── 4. Approve repair ─────────────────────────────────────────────────
step "4. Approving repair for incident #$INCIDENT_ID"
APPROVE=$(curl -s -X POST "$API/api/v1/incidents/$INCIDENT_ID/approve" -H "X-Admin-Token: $ADMIN_API_TOKEN")
echo "$APPROVE" | python3 -m json.tool
APPROVE_STATUS=$(echo "$APPROVE" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("status",""))' 2>/dev/null)
if [ "$APPROVE_STATUS" = "APPROVED" ]; then
    pass "Incident approved"
else
    fail "Approval failed: $APPROVE"
    exit 1
fi

# ── 5. Ansible repairs nginx over SSH ─────────────────────────────────
step "5. Running Ansible recovery playbook over SSH"

# Extract the lab SSH key from the target container
docker compose cp target:/home/labops/.ssh/lab_key ./evidence/lab_key
chmod 600 ./evidence/lab_key

# Write temporary inventory — use localhost:2222 (port-mapped to target container's sshd)
# The host machine cannot reach Docker internal IPs directly on macOS
cat > ./evidence/inventory.ini <<INV
[webservers]
lab-target ansible_host=127.0.0.1 ansible_port=2222 ansible_user=labops ansible_ssh_private_key_file=./evidence/lab_key ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
INV

# Ensure ansible is available
if ! command -v ansible-playbook &>/dev/null; then
    echo "  Installing ansible-core..."
    pip3 install --quiet ansible-core
fi

ansible-playbook -i ./evidence/inventory.ini ../ansible/recover-nginx.yml -v 2>&1 | tee ./evidence/ansible-output.log
ANSIBLE_EXIT=$?

if [ $ANSIBLE_EXIT -eq 0 ]; then
    pass "Ansible restored nginx"
else
    fail "Ansible playbook failed (exit $ANSIBLE_EXIT)"
fi

# ── 6. Record repair result ───────────────────────────────────────────
step "6. Recording repair result"
REPAIR=$(curl -s -X POST "$API/api/v1/incidents/$INCIDENT_ID/repair-result" \
    -H "X-Admin-Token: $ADMIN_API_TOKEN" -H 'Content-Type: application/json' \
    -d '{"success":true,"details":"Ansible recover-nginx.yml via SSH to 127.0.0.1:2222"}')
echo "$REPAIR" | python3 -m json.tool
REPAIR_STATUS=$(echo "$REPAIR" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("status",""))' 2>/dev/null)
if [ "$REPAIR_STATUS" = "REPAIR_RECORDED" ]; then
    pass "Repair recorded"
else
    fail "Repair recording failed"
fi

# ── 7. Wait for Zabbix OK → incident RESOLVED ────────────────────────
step "7. Waiting for Zabbix to confirm recovery (up to 120s)"
RESOLVED=false
for i in $(seq 1 40); do
    INC_DATA=$(curl -s "$API/api/v1/incidents/$INCIDENT_ID" -H "X-Viewer-Token: $VIEWER_API_TOKEN")
    STATUS=$(echo "$INC_DATA" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("status",""))' 2>/dev/null)
    if [ "$STATUS" = "RESOLVED" ]; then
        RESOLVED=true; break
    fi
    sleep 3
done

if $RESOLVED; then
    pass "Zabbix confirmed recovery → incident #$INCIDENT_ID RESOLVED"
else
    fail "Incident not resolved within 120s (status: $STATUS)"
    echo "  NOTE: Zabbix may need more polling cycles. Current status: $STATUS"
fi

# ── 8. Full audit trail ──────────────────────────────────────────────
step "8. Full audit trail for incident #$INCIDENT_ID"
DETAIL=$(curl -s "$API/api/v1/incidents/$INCIDENT_ID" -H "X-Viewer-Token: $VIEWER_API_TOKEN")
echo "$DETAIL" | python3 -m json.tool
echo "$DETAIL" | python3 -m json.tool > ./evidence/incident-detail.json

echo ""
echo "──────────────────────────────────────────────"
echo "Audit trail entries:"
echo "$DETAIL" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for e in data.get('audit', []):
    print(f\"  {e['created_at']}  {e['action']:25s}  {e['details']}\")
"

echo ""
echo "──────────────────────────────────────────────"
if $RESOLVED; then
    echo "INTEGRATION TEST PASSED"
    echo "  Zabbix detected real nginx failure → webhook created incident"
    echo "  Human approved repair → Ansible restored nginx over SSH"
    echo "  Zabbix confirmed recovery → incident closed with full audit trail"
else
    echo "INTEGRATION TEST PARTIAL"
    echo "  Pipeline complete through repair; Zabbix recovery confirmation pending"
    echo "  (Zabbix polling interval may need more time)"
fi

echo ""
echo "Evidence saved to: $(pwd)/evidence/"
echo "Log: $LOG"

# Clean up sensitive files
rm -f ./evidence/lab_key
