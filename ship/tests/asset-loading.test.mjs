import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { setImmediate as nextTurn } from 'node:timers/promises';
import { ASSET_LOAD_LIMITS, runAssetLoad } from '../src/asset-loading.mjs';
import { verifiedBytes } from '../src/resources.mjs';

function fakeTimers() {
  let now = 0, nextId = 0;
  const pending = new Map();
  return {
    setTimeout(callback, delay) { const id = ++nextId; pending.set(id, { callback, time: now + delay }); return id; },
    clearTimeout(id) { pending.delete(id); },
    get pending() { return pending.size; },
    get now() { return now; },
    async advance(duration) {
      const end = now + duration;
      while (true) {
        const first = [...pending].filter(([, task]) => task.time <= end).sort((a, b) => a[1].time - b[1].time)[0];
        if (!first) break;
        const [id, task] = first;
        now = task.time; pending.delete(id); task.callback(); await nextTurn();
      }
      now = end; await nextTurn();
    },
  };
}
const descriptor = bytes => ({ bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') });
function streamedResponse() {
  let controller, cancelled, cancelCount = 0;
  const body = new ReadableStream({
    start(value) { controller = value; },
    cancel(reason) { cancelled = reason; cancelCount++; },
  });
  // Totals must come from the trusted descriptor, even with a misleading header.
  return { response: new Response(body, { headers: { 'Content-Length': '999' } }), controller,
    get cancelled() { return cancelled; }, get cancelCount() { return cancelCount; } };
}

test('continuous slow transfer succeeds beyond the old 30-second limit with pinned progress totals', async () => {
  const timers = fakeTimers(), bytes = Uint8Array.of(1, 2, 3), stream = streamedResponse(), progress = [];
  const pending = verifiedBytes('/ship.glb', descriptor(bytes), undefined, {
    timers, fetchImpl: async () => stream.response, onProgress: value => progress.push(value),
  });
  await nextTurn();
  for (const byte of bytes) {
    await timers.advance(20000);
    stream.controller.enqueue(Uint8Array.of(byte)); await nextTurn();
  }
  stream.controller.close();
  assert.deepEqual(new Uint8Array(await pending), bytes);
  assert.equal(timers.now, 60000);
  assert.deepEqual(progress.filter(value => value.phase === 'downloading').map(value => value.loaded), [0, 1, 2, 3]);
  assert.ok(progress.every(value => value.total === bytes.length));
  assert.equal(progress.at(-1).phase, 'verifying');
  assert.equal(timers.pending, 0);
  assert.equal(stream.response.body.locked, false);
  assert.equal(stream.cancelCount, 0);
});

test('a stalled response header is bounded and aborts its request', async () => {
  const timers = fakeTimers(); let requestSignal;
  const pending = verifiedBytes('/ship.glb', descriptor(Uint8Array.of(1)), undefined, {
    timers, fetchImpl: (_, { signal }) => { requestSignal = signal; return new Promise(() => {}); },
  });
  const rejected = assert.rejects(pending, error => error.code === 'ASSET_IDLE_TIMEOUT');
  await nextTurn(); await timers.advance(ASSET_LOAD_LIMITS.idleTimeoutMs);
  await rejected;
  assert.equal(requestSignal.aborted, true);
  assert.equal(timers.pending, 0);
});

test('a stream that stops progressing is cancelled and releases its reader', async () => {
  const timers = fakeTimers(), stream = streamedResponse();
  const pending = verifiedBytes('/archive.glb', descriptor(Uint8Array.of(1, 2)), undefined, {
    timers, fetchImpl: async () => stream.response,
  });
  const rejected = assert.rejects(pending, error => error.code === 'ASSET_IDLE_TIMEOUT');
  await nextTurn(); await timers.advance(30000);
  stream.controller.enqueue(Uint8Array.of(1)); await nextTurn();
  await timers.advance(ASSET_LOAD_LIMITS.idleTimeoutMs - 1);
  assert.equal(stream.cancelCount, 0);
  await timers.advance(1); await rejected;
  assert.equal(stream.cancelCount, 1);
  assert.equal(stream.cancelled.code, 'ASSET_IDLE_TIMEOUT');
  assert.equal(stream.response.body.locked, false);
  assert.equal(timers.pending, 0);
});

test('empty chunks do not extend the idle deadline', async () => {
  const timers = fakeTimers(), stream = streamedResponse();
  const pending = verifiedBytes('/archive.glb', descriptor(Uint8Array.of(1)), undefined, {
    timers, fetchImpl: async () => stream.response,
  });
  const rejected = assert.rejects(pending, error => error.code === 'ASSET_IDLE_TIMEOUT');
  await nextTurn(); await timers.advance(30000);
  stream.controller.enqueue(new Uint8Array()); await nextTurn();
  await timers.advance(15000); await rejected;
  assert.equal(stream.cancelCount, 1);
});

test('sustained download progress cannot extend the overall deadline', async () => {
  const timers = fakeTimers(), stream = streamedResponse();
  const pending = verifiedBytes('/ship.glb', descriptor(new Uint8Array(10)), undefined, {
    timers, fetchImpl: async () => stream.response,
  });
  const rejected = assert.rejects(pending, error => error.code === 'ASSET_TOTAL_TIMEOUT');
  await nextTurn();
  for (let i = 0; i < 7; i++) {
    await timers.advance(40000); stream.controller.enqueue(Uint8Array.of(0)); await nextTurn();
  }
  await timers.advance(20000); await rejected;
  assert.equal(timers.now, ASSET_LOAD_LIMITS.totalTimeoutMs);
  assert.equal(stream.cancelled.code, 'ASSET_TOTAL_TIMEOUT');
  assert.equal(timers.pending, 0);
});

test('cancellation rejects promptly, closes the body and permits an independent retry', async () => {
  const timers = fakeTimers(), stream = streamedResponse(), controller = new AbortController(), progress = [];
  const bytes = Uint8Array.of(1, 2);
  const pending = verifiedBytes('/archive.glb', descriptor(bytes), controller.signal, {
    timers, fetchImpl: async () => stream.response, onProgress: value => progress.push(value),
  });
  const rejected = assert.rejects(pending, error => error.name === 'AbortError');
  await nextTurn(); stream.controller.enqueue(bytes.subarray(0, 1)); await nextTurn();
  controller.abort(); await rejected; await nextTurn();
  const progressAtAbort = progress.length;
  await timers.advance(ASSET_LOAD_LIMITS.totalTimeoutMs);
  assert.equal(progress.length, progressAtAbort);
  assert.equal(stream.cancelCount, 1);
  assert.equal(stream.response.body.locked, false);
  assert.equal(timers.pending, 0);
  const retried = await verifiedBytes('/archive.glb', descriptor(bytes), undefined, {
    timers, fetchImpl: async () => new Response(bytes),
  });
  assert.deepEqual(new Uint8Array(retried), bytes);
  assert.equal(timers.pending, 0);
});

test('an already cancelled request never starts downloading', async () => {
  const timers = fakeTimers(), controller = new AbortController(); controller.abort();
  let calls = 0;
  await assert.rejects(verifiedBytes('/ship.glb', descriptor(Uint8Array.of(1)), controller.signal, {
    timers, fetchImpl: () => { calls++; }, onProgress: () => { calls++; },
  }), error => error.name === 'AbortError');
  assert.equal(calls, 0); assert.equal(timers.pending, 0);
});

test('a late response after cancellation is closed without progress or verification', async () => {
  const timers = fakeTimers(), controller = new AbortController(), stream = streamedResponse(), progress = [];
  let resolveFetch;
  const pending = verifiedBytes('/ship.glb', descriptor(Uint8Array.of(1)), controller.signal, {
    timers, fetchImpl: () => new Promise(resolve => { resolveFetch = resolve; }), onProgress: value => progress.push(value),
  });
  const rejected = assert.rejects(pending, error => error.name === 'AbortError');
  await nextTurn(); controller.abort(); await rejected;
  resolveFetch(stream.response); await nextTurn();
  assert.equal(stream.cancelCount, 1);
  assert.deepEqual(progress.map(value => value.phase), ['downloading']);
});

test('size and SHA pins still fail closed, with oversized streams cancelled immediately', async () => {
  const bytes = Uint8Array.of(1, 2, 3), expected = descriptor(bytes);
  for (const wrong of [bytes.subarray(0, 2), Uint8Array.of(1, 2, 3, 4)]) {
    const timers = fakeTimers();
    await assert.rejects(verifiedBytes('/ship.glb', expected, undefined, {
      timers, fetchImpl: async () => new Response(wrong),
    }), /Asset size mismatch/);
    assert.equal(timers.pending, 0);
  }
  const timers = fakeTimers(), stream = streamedResponse();
  const pending = verifiedBytes('/ship.glb', expected, undefined, { timers, fetchImpl: async () => stream.response });
  const rejected = assert.rejects(pending, /Asset size mismatch/);
  await nextTurn(); stream.controller.enqueue(Uint8Array.of(1, 2, 3, 4)); await rejected;
  assert.equal(stream.cancelCount, 1); assert.equal(stream.response.body.locked, false);
  await assert.rejects(verifiedBytes('/ship.glb', expected, undefined, {
    timers, fetchImpl: async () => new Response(Uint8Array.of(3, 2, 1)),
  }), /Asset identity mismatch/);
  assert.equal(timers.pending, 0);
});

test('HTTP errors close their bodies and retain their status', async () => {
  const timers = fakeTimers(), stream = streamedResponse();
  const response = new Response(stream.response.body, { status: 503 });
  await assert.rejects(verifiedBytes('/ship.glb', descriptor(Uint8Array.of(1)), undefined, {
    timers, fetchImpl: async () => response,
  }), /Asset HTTP 503/);
  assert.equal(stream.cancelCount, 1); assert.equal(timers.pending, 0);
});

test('verification and decoding share the overall deadline without a download idle timeout', async () => {
  for (const phase of ['verifying', 'decoding']) {
    const timers = fakeTimers(); let activeSignal, finish;
    const pending = runAssetLoad(async load => {
      activeSignal = load.signal;
      load.reportProgress({ phase, loaded: 1, total: 1 });
      return new Promise(resolve => { finish = resolve; });
    }, { timers });
    const rejected = assert.rejects(pending, error => error.code === 'ASSET_TOTAL_TIMEOUT');
    await nextTurn(); await timers.advance(ASSET_LOAD_LIMITS.idleTimeoutMs + 1);
    assert.equal(activeSignal.aborted, false);
    await timers.advance(ASSET_LOAD_LIMITS.totalTimeoutMs - timers.now); await rejected;
    assert.equal(activeSignal.aborted, true); assert.equal(timers.pending, 0);
    finish(); await nextTurn();
  }
});

test('caller cancellation stops a decoding task promptly and suppresses late progress', async () => {
  const timers = fakeTimers(), controller = new AbortController(), progress = [];
  let finish, activeSignal, publish;
  const pending = runAssetLoad(async load => {
    activeSignal = load.signal; publish = load.reportProgress;
    load.reportProgress({ phase: 'decoding', loaded: 1, total: 1 });
    return new Promise(resolve => { finish = resolve; });
  }, { timers, signal: controller.signal, onProgress: value => progress.push(value) });
  const rejected = assert.rejects(pending, error => error.name === 'AbortError');
  await nextTurn(); controller.abort(); await rejected;
  publish({ phase: 'decoding', loaded: 1, total: 1 }); finish(); await nextTurn();
  assert.equal(activeSignal.aborted, true); assert.equal(progress.length, 1); assert.equal(timers.pending, 0);
});
