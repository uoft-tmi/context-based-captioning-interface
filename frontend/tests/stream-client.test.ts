import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CaptionStream } from '../lib/stream-client';

class FakeSocket {
  readyState = 1;
  sent: (string | Blob)[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  send(value: string | Blob) { this.sent.push(value); }
  close() { this.readyState = 3; this.onclose?.(); }
  message(value: object) { this.onmessage?.({ data: JSON.stringify(value) } as MessageEvent); }
}
function setup(timeout = 1000) {
  const socket = new FakeSocket();
  const captions: string[] = [];
  const latencies: number[] = [];
  const finals: string[] = [];
  const warnings: string[] = [];
  const errors: Error[] = [];
  const stream = new CaptionStream({
    onCaption: (text, _index, latency) => { assert.ok(latency >= 0); captions.push(text); latencies.push(latency); },
    onFinal: (text) => finals.push(text), onWarning: (text) => warnings.push(text), onError: (error) => errors.push(error),
  }, () => socket as unknown as WebSocket, timeout, timeout);
  return { stream, socket, captions, latencies, finals, warnings, errors };
}
const chunk = (index: number) => ({ chunk_index: index, audio_b64: 'YQ==', mime: 'audio/wav' as const });


test('waits for model readiness and acknowledges each ordered caption', async () => {
  const { stream, socket, captions } = setup();
  let ready = false;
  const connected = stream.connect('ws://test/?access_token=secret').then(() => { ready = true; });
  await Promise.resolve();
  assert.equal(ready, false);
  await assert.rejects(stream.sendChunk(chunk(0)), /not accepting/);
  socket.message({ type: 'ready' });
  await connected;
  for (let index = 0; index < 2; index++) {
    const pending = stream.sendChunk(chunk(index));
    socket.message({ type: 'caption', text: `line ${index}`, chunk_index: index });
    await pending;
  }
  assert.deepEqual(captions, ['line 0', 'line 1']);
  stream.close();
});


test('stop leaves the socket open until durable final acknowledgement', async () => {
  const { stream, socket, finals } = setup();
  const ready = stream.connect('ws://test');
  socket.message({ type: 'ready' }); await ready;
  let finished = false;
  const completion = stream.finish().then((text) => { finished = true; return text; });
  assert.deepEqual(JSON.parse(socket.sent[0] as string), { type: 'stop' });
  assert.equal(socket.readyState, 1);
  await Promise.resolve(); assert.equal(finished, false);
  socket.message({ type: 'final', text: 'the full transcript', done: true, transcript_saved: true });
  assert.equal(await completion, 'the full transcript');
  assert.deepEqual(finals, ['the full transcript']);
  socket.close();
});


test('backend errors reject readiness without exposing the socket URL', async () => {
  const { stream, socket, errors } = setup();
  const ready = stream.connect('ws://test/?access_token=secret');
  socket.message({ type: 'error', text: 'Session not found' });
  await assert.rejects(ready, /Session not found/);
  assert.equal(errors.length, 1);
  assert.ok(!errors[0].message.includes('secret'));
});


test('warnings acknowledge a dropped chunk so later audio can continue', async () => {
  const { stream, socket, warnings } = setup();
  const ready = stream.connect('ws://test'); socket.message({ type: 'ready' }); await ready;
  const pending = stream.sendChunk(chunk(0));
  socket.message({ type: 'warning', text: 'Chunk failed', chunk_index: 0 }); await pending;
  const next = stream.sendChunk(chunk(1));
  socket.message({ type: 'caption', text: 'next chunk', chunk_index: 1 }); await next;
  assert.deepEqual(warnings, ['Chunk failed']);
  stream.close();
});


test('unsaved final transcript rejects completion', async () => {
  const { stream, socket, finals } = setup();
  const ready = stream.connect('ws://test'); socket.message({ type: 'ready' }); await ready;
  const finished = stream.finish();
  socket.message({ type: 'final', text: 'not saved', transcript_saved: false });
  await assert.rejects(finished, /could not be saved/);
  assert.equal(finals.length, 0);
});


test('unexpected disconnect rejects pending audio and completion', async () => {
  const { stream, socket, errors } = setup();
  const ready = stream.connect('ws://test'); socket.message({ type: 'ready' }); await ready;
  const pending = stream.sendChunk(chunk(0));
  const finished = stream.finish();
  socket.close();
  await assert.rejects(pending, /closed before/);
  await assert.rejects(finished, /closed before/);
  assert.equal(errors.length, 1);
});


test('a chunk timeout fails the stream instead of building an unbounded backlog', async () => {
  const { stream, socket, errors } = setup(10);
  const ready = stream.connect('ws://test'); socket.message({ type: 'ready' }); await ready;
  await assert.rejects(stream.sendChunk(chunk(0)), /Timed out/);
  assert.equal(errors.length, 1);
  assert.equal(socket.readyState, 3);
});


test('server duration limit finalizes and finish remains idempotent', async () => {
  const { stream, socket, finals } = setup();
  const ready = stream.connect('ws://test'); socket.message({ type: 'ready' }); await ready;
  socket.message({ type: 'final', text: '', transcript_saved: true });
  assert.equal(await stream.finish(), '');
  assert.deepEqual(finals, ['']);
  stream.close();
});


test('sends original WAV bytes without base64 and measures from capture, not send', async () => {
  const { stream, socket, captions, latencies } = setup();
  const ready = stream.connect('ws://test'); socket.message({ type: 'ready' }); await ready;
  const audio = new Blob([new Uint8Array([82, 73, 70, 70])], { type: 'audio/wav' });
  const capturedAtMs = performance.now() - 1000;
  const pending = stream.sendChunk({ chunk_index: 0, audio, capturedAtMs });
  assert.strictEqual(socket.sent[0], audio);
  assert.deepEqual(Array.from(new Uint8Array(await audio.arrayBuffer())), [82, 73, 70, 70]);
  socket.message({ type: 'caption', text: 'live phrase', chunk_index: 0 });
  await pending;
  assert.ok(latencies[0] >= 1000);
  assert.deepEqual(captions, ['live phrase']);
  stream.close();
});


test('binary transport rejects skipped and duplicate chunk numbers', async () => {
  const { stream, socket } = setup();
  const ready = stream.connect('ws://test'); socket.message({ type: 'ready' }); await ready;
  const audio = new Blob(['wav']);
  await assert.rejects(stream.sendChunk({ chunk_index: 1, audio }), /Expected audio chunk 0/);
  const first = stream.sendChunk({ chunk_index: 0, audio });
  await assert.rejects(stream.sendChunk({ chunk_index: 0, audio }), /Expected audio chunk 1/);
  socket.message({ type: 'caption', text: 'first', chunk_index: 0 }); await first;
  const second = stream.sendChunk({ chunk_index: 1, audio });
  socket.message({ type: 'caption', text: 'second', chunk_index: 1 }); await second;
  assert.equal(socket.sent.length, 2);
  stream.close();
});


test('recording allowance comes from the server readiness acknowledgement', async () => {
  const socket = new FakeSocket();
  const limits: number[] = [];
  const stream = new CaptionStream({
    onReady: (seconds) => limits.push(seconds),
    onCaption: () => {}, onFinal: () => {}, onWarning: () => {}, onError: () => {},
  }, () => socket as unknown as WebSocket);
  const ready = stream.connect('ws://test');
  socket.message({type:'ready',recording_limit_seconds:30});
  await ready;
  assert.deepEqual(limits,[30]);
  stream.close();
});
