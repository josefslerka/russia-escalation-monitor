const { test } = require('node:test');
const assert = require('node:assert/strict');
const core = require('../site/assets/signals-core.js');
const state = { area: 'all', topic: 'all', status: 'all', direction: 'all', basis: 'publication', from: '2026-10-22', to: '2026-10-27', undated: false };
const record = (id, areas, event, publication) => ({ id, areas, topics: ['hybrid'], status: 'confirmed', direction: 'up', times: { event, publication } });
const dated = (start, end = start) => ({ start, end, precision: 'day' });

test('new attribution of an old fire is not a new October event', () => {
  const item = record('fire', ['ROU', 'POL'], dated('2026-09-14'), dated('2026-10-26'));
  assert.equal(core.filterRecords([item], state).length, 1);
  assert.equal(core.filterRecords([item], { ...state, basis: 'event' }).length, 0);
});
test('multiple countries never duplicate a ledger record', () => {
  const item = record('fire', ['ROU', 'POL'], dated('2026-09-14'), dated('2026-10-26'));
  const selected = core.filterRecords([item], state);
  assert.equal(selected.length, 1);
  assert.deepEqual([...core.countryCounts(selected, { ROU: { kind: 'country' }, POL: { kind: 'country' } })], [['ROU', 1], ['POL', 1]]);
});
test('general NATO warnings cannot become Estonian incidents', () => {
  const item = record('warning', ['NATO'], dated('2026-10-23'), dated('2026-10-23'));
  assert.equal(core.matchesArea(item, 'EST'), false);
  assert.equal(core.countryCounts([item], { NATO: { kind: 'region' } }).size, 0);
});
test('interval filters use overlap, not only their first day', () => {
  const item = record('interval', ['UKR'], dated('2026-10-17', '2026-10-24'), dated('2026-10-26'));
  assert.equal(core.filterRecords([item], { ...state, basis: 'event' }).length, 1);
});
test('unknown dates require an explicit choice', () => {
  const item = record('undated', [], dated(null, null), dated(null, null));
  assert.equal(core.filterRecords([item], state).length, 0);
  assert.equal(core.filterRecords([item], { ...state, undated: true }).length, 1);
});
test('date validation rejects impossible calendar days', () => {
  assert.equal(core.validDay('2026-02-30'), false);
  assert.equal(core.validDay('2026-10-27'), true);
});
