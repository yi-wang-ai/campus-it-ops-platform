// Run with: node scripts/test-webhook.cjs; no Zabbix installation needed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const script = fs.readFileSync('zabbix/webhook.js', 'utf8');
let received;
function HttpRequest() {
  this.addHeader = () => {};
  this.post = (_url, body) => { received = JSON.parse(body); return '{}'; };
  this.getStatus = () => 200;
}
function run(parameters) {
  received = null;
  const sandbox = {value: JSON.stringify(parameters), HttpRequest, Zabbix: {log() {}}};
  assert.equal(vm.runInNewContext(`(function () { ${script} })()`, sandbox), 'OK');
  return received;
}
const base = {
  url: 'http://127.0.0.1:8000/api/v1/alerts/zabbix', token: 'some-token',
  event_id: 'problem-9', recovery_event_id: '{EVENT.RECOVERY.ID}',
  host: 'lab-vm-01', trigger_id: 'trigger-3', subject: 'nginx down', severity: 'High'
};
let problem = run({...base, event_value: '1'});
assert.equal(problem.state, 'PROBLEM');
assert.equal(problem.event_id, 'problem-9');
assert.equal(problem.problem_event_id, null);
let recovered = run({...base, event_value: '0', recovery_event_id: 'ok-10'});
assert.equal(recovered.state, 'OK');
assert.equal(recovered.problem_event_id, 'problem-9');
assert.equal(recovered.event_id, 'ok-10');
let fallback = run({...base, event_value: '0'});
assert.equal(fallback.event_id, 'problem-9-recovery');
assert.throws(() => run({...base, event_value: 'invalid'}));
console.log('Zabbix webhook tests: 4 passed');
