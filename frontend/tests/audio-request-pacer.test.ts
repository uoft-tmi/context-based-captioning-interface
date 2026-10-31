import assert from 'node:assert/strict';
import { test } from 'node:test';
import { AudioRequestPacer } from '../lib/audio/request-pacer';

test('first request is immediate, while a backlog cannot cause a request burst', async () => {
  let now = 1000;
  const waits: number[] = [];
  const pacer = new AudioRequestPacer(3200, () => now, async (ms) => { waits.push(ms); now += ms; });
  const sent: number[] = [];
  await pacer.wait(); pacer.markSent(); sent.push(now);
  assert.deepEqual(waits, []);
  // A slow provider leaves multiple completed segments waiting to be sent.
  now = 10000;
  for (let index = 0; index < 3; index++) {
    await pacer.wait(); pacer.markSent(); sent.push(now);
  }
  assert.deepEqual(sent, [1000, 10000, 13200, 16400]);
  assert.deepEqual(waits, [3200, 3200]);
});

test('a slow response that already consumed the interval adds no artificial wait', async () => {
  let now = 0;
  const pacer = new AudioRequestPacer(3200, () => now, async () => { assert.fail('No wait needed'); });
  pacer.markSent();
  now = 4000;
  await pacer.wait();
});

test('zero interval preserves providers without pacing requirements', async () => {
  const pacer = new AudioRequestPacer(0, () => 0, async () => { assert.fail('No wait needed'); });
  pacer.markSent();
  await pacer.wait();
});
