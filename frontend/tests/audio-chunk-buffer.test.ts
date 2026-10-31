import assert from 'node:assert/strict';
import { test } from 'node:test';
import { AudioChunkBuffer } from '../lib/audio/chunk-buffer';

const values = (length: number, offset = 0) => Float32Array.from({ length }, (_, index) => offset + index);

test('emits the first second without waiting for a full steady-state segment', () => {
  const buffer = new AudioChunkBuffer(1000, 3200, 1000);
  assert.equal(buffer.push(values(900), 900).length, 0);
  const first = buffer.push(values(100, 900), 1000);
  assert.equal(first.length, 1);
  assert.equal(first[0].samples.length, 1000);
  assert.equal(first[0].capturedAtMs, 0);
  assert.equal(buffer.push(values(3199, 1000), 4199).length, 0);
  const second = buffer.push(values(1, 4199), 4200);
  assert.equal(second[0].samples.length, 3200);
  assert.equal(second[0].capturedAtMs, 1000);
});

test('variable input frames and final flush preserve every sample in order', () => {
  const buffer = new AudioChunkBuffer(1000, 3200, 1000);
  const segments = [];
  let offset = 0;
  for (const length of [128, 2048, 17, 4500, 6]) {
    segments.push(...buffer.push(values(length, offset), offset + length));
    offset += length;
  }
  const last = buffer.flush();
  assert.ok(last);
  segments.push(last);
  assert.deepEqual(segments.map((segment) => segment.samples.length), [1000, 3200, 2499]);
  assert.deepEqual(segments.flatMap((segment) => Array.from(segment.samples)), Array.from(values(offset)));
  assert.deepEqual(segments.map((segment) => segment.capturedAtMs), [0, 1000, 4200]);
  assert.equal(buffer.flush(), null);
});

test('preserves constant chunk sizes for providers without an initial interval', () => {
  const buffer = new AudioChunkBuffer(16000, 2500);
  const ready = buffer.push(new Float32Array(80000), 5000);
  assert.deepEqual(ready.map((segment) => segment.samples.length), [40000, 40000]);
  assert.equal(buffer.flush(), null);
});

test('one continuous recording stays within 20 calls in any minute including its stop flush', () => {
  const buffer = new AudioChunkBuffer(1000, 3200, 1000);
  const requests: number[] = [];
  for (let elapsed = 100; elapsed <= 180000; elapsed += 100) {
    buffer.push(new Float32Array(100), elapsed).forEach(() => requests.push(elapsed));
  }
  if (buffer.flush()) requests.push(180000);
  for (const now of requests) {
    assert.ok(requests.filter((at) => at > now - 60000 && at <= now).length <= 20);
  }
  assert.equal(requests[0], 1000);
});

test('invalid timing parameters cannot create a non-terminating chunk loop', () => {
  for (const duration of [0, -1, NaN, Infinity]) {
    assert.throws(() => new AudioChunkBuffer(16000, duration), /must be positive/);
  }
});
