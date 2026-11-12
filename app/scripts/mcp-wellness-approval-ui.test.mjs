import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../backend/src/main/resources/mcp/wellness-approval.html', import.meta.url), 'utf8');
const script = /<script>([\s\S]*?)<\/script>/.exec(html)?.[1];
assert.ok(script, 'A self-contained iframe script is required');

function widget() {
  const outbound = [];
  const listeners = new Map();
  const nodes = new Map();
  for (const name of ['state', 'details', 'approve', 'reject']) {
    nodes.set(name, {
      textContent: '',
      disabled: name === 'approve' || name === 'reject',
      events: new Map(),
      addEventListener(type, cb) { this.events.set(type, cb); },
      click() {
        if (!this.disabled) this.events.get('click')?.();
      }
    });
  }
  const parent = { postMessage(message) { outbound.push(message); } };
  const window = {
    parent,
    addEventListener(name, cb) { listeners.set(name, cb); }
  };
  const document = { getElementById(name) { return nodes.get(name); } };
  const context = vm.createContext({ window, document });
  vm.runInContext(script, context, { filename: 'prp-mcp-app-card.js', timeout: 5000 });
  function recv(data) {
    listeners.get('message')?.({ source: parent, data });
  }
  async function tick() {
    await new Promise(resolve => setImmediate(resolve));
  }
  function nextCall() {
    const call = outbound.find(x => x.method === 'tools/call' && !x.seen);
    if (call) call.seen = true;
    return call;
  }
  function acknowledge(call, output = { isError: false }) {
    recv({ jsonrpc: '2.0', id: call.id, result: output });
  }
  async function init() {
    const req = outbound.find(x => x.method === 'ui/initialize');
    assert.equal(req?.params?.protocolVersion, '2026-01-26');
    acknowledge(req, { protocolVersion: '2026-01-26', hostCapabilities: { serverTools: {} } });
    await tick();
    assert.equal(outbound.some(x => x.method === 'ui/notifications/initialized'), true);
  }
  return { nodes, outbound, recv, tick, nextCall, acknowledge, init };
}

const breakfast = {
  draftId: 'f00dd1ec-6b3f-4000-a76c-88c700e74923',
  kind: 'WELLNESS_CREATE',
  expiresAt: '2026-11-12T15:00:00',
  values: {
    entity: 'meal',
    after: {
      meal: {
        mealDate: '2026-11-12', mealType: 'BREAKFAST',
        note: '无额外烹调用油', items: [{ foodId: 2, grams: 100 }]
      }
    },
    foods: { 2: { name: '鸡蛋（熟）', calories100g: 144 } }
  }
};

function deliverBreakfast(w) {
  w.recv({
    jsonrpc: '2.0', method: 'ui/notifications/tool-result',
    params: {
      content: [{ type: 'text', text: JSON.stringify(breakfast) }],
      isError: false
    }
  });
}

test('human approval displays calories and performs approval before confirmation', async () => {
  const w = widget();
  await w.init();
  deliverBreakfast(w);
  assert.match(w.nodes.get('details').textContent, /144\.0 千卡/);
  assert.equal(w.nodes.get('approve').disabled, false);
  w.nodes.get('approve').click();
  const approval = w.nextCall();
  assert.equal(approval.params.name, 'prp_chatgpt_wellness_approval');
  assert.equal(approval.params.arguments.decision, 'approve');
  assert.equal(approval.params.arguments.draftId, breakfast.draftId);
  assert.equal(w.nextCall(), undefined, 'cannot confirm before approval returns');
  w.acknowledge(approval);
  await w.tick();
  const commit = w.nextCall();
  assert.equal(commit.params.name, 'prp_confirm_wellness_draft');
  assert.equal(commit.params.arguments.draftId, breakfast.draftId);
  w.acknowledge(commit);
  await w.tick();
  assert.match(w.nodes.get('state').textContent, /已确认保存/);
  assert.equal(w.nodes.get('approve').disabled, true);
  assert.equal(w.nodes.get('reject').disabled, true);
});

test('reject marks draft rejected and never saves a meal', async () => {
  const w = widget();
  await w.init();
  deliverBreakfast(w);
  w.nodes.get('reject').click();
  const approval = w.nextCall();
  assert.equal(approval.params.arguments.decision, 'reject');
  w.acknowledge(approval);
  await w.tick();
  assert.match(w.nodes.get('state').textContent, /已拒绝/);
  assert.equal(w.nextCall(), undefined);
  assert.equal(w.nodes.get('reject').disabled, true);
});

test('unknown or malformed drafts never enable approval buttons', async () => {
  const w = widget();
  await w.init();
  w.recv({ jsonrpc:'2.0', method:'ui/notifications/tool-result',
    params:{ content:[{type:'text', text: JSON.stringify({
      ...breakfast, values: {after:{ metric: {weightKg:70} }}
    })}]} });
  assert.equal(w.nodes.get('approve').disabled, true);
  assert.equal(w.nodes.get('reject').disabled, true);
  assert.equal(w.nextCall(), undefined);
});

test('a failed approval request cannot silently continue to commit', async () => {
  const w = widget();
  await w.init();
  deliverBreakfast(w);
  w.nodes.get('approve').click();
  const approval = w.nextCall();
  w.acknowledge(approval, { isError: true });
  await w.tick();
  assert.match(w.nodes.get('state').textContent, /操作未完成/);
  assert.equal(w.nextCall(), undefined);
  assert.equal(w.nodes.get('approve').disabled, true);
});
