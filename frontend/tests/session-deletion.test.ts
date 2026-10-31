import assert from 'node:assert/strict';
import { test } from 'node:test';
import { deleteSessionBatch } from '../lib/session-deletion';

const target = (id: string, is_recording = false) => ({ id, name: `Lecture ${id}`, is_recording });

test('bulk deletion skips recordings and deletes each session only once', async () => {
  const calls: string[] = [];
  const result = await deleteSessionBatch([target('one'), target('live', true), target('one'), target('two')], async (id) => { calls.push(id); });
  assert.deepEqual(calls, ['one', 'two']);
  assert.deepEqual(result, { deleted: ['one', 'two'], failed: [], skipped: ['live'] });
});

test('partial failures preserve failed session details and continue deleting sequentially', async () => {
  let inFlight = 0;
  let maxInFlight = 0;
  const result = await deleteSessionBatch([target('one'), target('locked'), target('three')], async (id) => {
    inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
    await Promise.resolve();
    inFlight--;
    if (id === 'locked') throw new Error('A recording started; retry after it ends.');
  });
  assert.equal(maxInFlight, 1);
  assert.deepEqual(result.deleted, ['one', 'three']);
  assert.deepEqual(result.failed, [{ id: 'locked', name: 'Lecture locked', message: 'A recording started; retry after it ends.' }]);
});

test('an empty selection sends no deletion requests', async () => {
  const result = await deleteSessionBatch([], async () => { assert.fail('Unexpected deletion'); });
  assert.deepEqual(result, { deleted: [], failed: [], skipped: [] });
});
