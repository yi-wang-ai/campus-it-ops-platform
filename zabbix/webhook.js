// Zabbix Media type: Webhook. Use ONLY inside an isolated training lab.
// Expected parameters: url, token, event_id={EVENT.ID},
// recovery_event_id={EVENT.RECOVERY.ID}, event_value={EVENT.VALUE},
// host={HOST.NAME}, trigger_id={TRIGGER.ID}, subject={EVENT.NAME},
// severity={EVENT.SEVERITY}; optional http_proxy.
// In recovery notifications EVENT.ID identifies the original problem event;
// EVENT.RECOVERY.ID identifies the matching OK event (Zabbix 7.4 docs).
try {
    var p = JSON.parse(value);
    if (p.event_value !== '0' && p.event_value !== '1') {
        throw 'event_value must be 0 or 1';
    }
    if (!p.url || !p.token || !p.event_id || !p.host || !p.trigger_id) {
        throw 'Missing required webhook parameter';
    }
    if (String(p.url).indexOf('https://') !== 0 &&
        String(p.url).indexOf('http://') !== 0) {
        throw 'Webhook endpoint must use HTTP(S)';
    }
    var isProblem = p.event_value === '1';
    var recoveryId = String(p.recovery_event_id || '');
    if (!isProblem && (recoveryId === '' || recoveryId.charAt(0) === '{')) {
        // Stable fallback event id for a replay, if the macro is unavailable.
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
    if (p.http_proxy) {
        request.setProxy(p.http_proxy);
    }
    var response = request.post(p.url, JSON.stringify(payload));
    if (request.getStatus() < 200 || request.getStatus() >= 300) {
        throw 'Incident API returned HTTP ' + request.getStatus();
    }
    return 'OK';
} catch (error) {
    Zabbix.log(3, '[CampusOps] webhook failed: ' + error);
    throw error;
}
