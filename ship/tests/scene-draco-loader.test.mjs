import test from 'node:test';
import assert from 'node:assert/strict';
import { setImmediate as nextTurn } from 'node:timers/promises';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { SceneDracoLoader } from '../src/scene-draco-loader.mjs';

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const config = { attributeIDs: { position: 'POSITION' }, attributeTypes: { position: 'Float32Array' } };
const geometryData = () => ({ attributes: [{ name: 'position', itemSize: 3, stride: 3,
  array: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]) }] });

// Only browser primitives are replaced in this isolated test file. Decoder
// initialization, worker scheduling, callbacks and geometry creation are the
// actual locked DRACOLoader implementation, not a fake loader/parsed result.
function browser(t) {
  const workers = [], created = [], revoked = [];
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'Worker');
  class WorkerDouble {
    constructor(url) { this.url = url; this.messages = []; this.terminations = 0; workers.push(this); }
    postMessage(message) { this.messages.push(message); }
    terminate() { this.terminations++; }
    finish(message = this.messages.find(row => row.type === 'decode')) {
      this.onmessage?.({ data: { type: 'decode', id: message.id, geometry: geometryData() } });
    }
  }
  Object.defineProperty(globalThis, 'Worker', { configurable: true, writable: true, value: WorkerDouble });
  t.after(() => { if (previous) Object.defineProperty(globalThis, 'Worker', previous); else delete globalThis.Worker; });
  t.mock.method(URL, 'createObjectURL', () => { const value = `blob:scene-decoder-${created.length + 1}`; created.push(value); return value; });
  t.mock.method(URL, 'revokeObjectURL', value => revoked.push(value));
  return { workers, created, revoked };
}

function transfers({ delayed = false } = {}) {
  const requests = [];
  const fetchImpl = (url, options) => {
    const task = deferred();
    const row = { url, signal: options.signal, ...task,
      finish() { task.resolve(new Response(url.endsWith('.wasm') ? new Uint8Array([0]) : '// decoder fixture')); } };
    requests.push(row);
    if (!delayed) row.finish();
    return task.promise; // Deliberately ignores abort so late responses are tested.
  };
  return { requests, fetchImpl };
}

function loader(t, options) {
  const result = new SceneDracoLoader(options).setDecoderPath('https://example.invalid/draco/').setWorkerLimit(2);
  assert.ok(result instanceof DRACOLoader);
  t.after(() => result.dispose());
  return result;
}

test('cancellation during decoder JS/WASM initialization prevents late workers and blob URLs', async t => {
  const browserState = browser(t), transfer = transfers({ delayed: true }), controller = new AbortController();
  const decoder = loader(t, { signal: controller.signal, fetchImpl: transfer.fetchImpl });
  const first = decoder.decodeGeometry(new ArrayBuffer(8), config);
  const second = decoder.decodeGeometry(new ArrayBuffer(9), config);
  const rejected = Promise.all([assert.rejects(first, { name: 'AbortError' }), assert.rejects(second, { name: 'AbortError' })]);
  assert.equal(transfer.requests.length, 2); // One shared JS/WASM initialization per owner.
  controller.abort(); await rejected;
  assert.ok(transfer.requests.every(row => row.signal.aborted));
  for (const row of transfer.requests) row.finish();
  await nextTurn();
  assert.deepEqual(browserState.workers, []); assert.deepEqual(browserState.created, []);
  assert.equal(decoder.workerSourceURL, ''); assert.equal(decoder._pendingLibraries.size, 0);
  await assert.rejects(decoder.decodeGeometry(new ArrayBuffer(10), config), { name: 'AbortError' });
  assert.equal(transfer.requests.length, 2);
});

test('an already cancelled owner requests neither libraries nor workers', async t => {
  const browserState = browser(t), transfer = transfers(), controller = new AbortController();
  controller.abort();
  const decoder = loader(t, { signal: controller.signal, fetchImpl: transfer.fetchImpl });
  await assert.rejects(decoder.decodeGeometry(new ArrayBuffer(8), config), { name: 'AbortError' });
  assert.deepEqual(transfer.requests, []); assert.deepEqual(browserState.created, []); assert.deepEqual(browserState.workers, []);
});

test('cancellation across resolved-library microtasks leaves no worker or blob URL alive', async t => {
  const browserState = browser(t);
  for (let turns = 0; turns < 16; turns++) {
    const transfer = transfers(), decoder = loader(t, { fetchImpl: transfer.fetchImpl });
    const pending = decoder.decodeGeometry(new ArrayBuffer(8), config);
    const rejected = assert.rejects(pending, { name: 'AbortError' });
    for (let i = 0; i < turns; i++) await Promise.resolve();
    decoder.dispose(); await rejected; await nextTurn();
    assert.equal(decoder.workerPool.length, 0); assert.equal(decoder.workerSourceURL, '');
  }
  assert.ok(browserState.workers.every(worker => worker.terminations === 1));
  assert.deepEqual(browserState.revoked.slice().sort(), browserState.created.slice().sort());
});

test('cancelling active parses rejects both tasks and terminates each owned worker once', async t => {
  const browserState = browser(t), transfer = transfers(), controller = new AbortController();
  const decoder = loader(t, { signal: controller.signal, fetchImpl: transfer.fetchImpl });
  const first = decoder.decodeGeometry(new ArrayBuffer(8), config);
  const second = decoder.decodeGeometry(new ArrayBuffer(9), config);
  const rejected = Promise.all([assert.rejects(first, { name: 'AbortError' }), assert.rejects(second, { name: 'AbortError' })]);
  await nextTurn();
  assert.equal(browserState.workers.length, 2);
  assert.ok(browserState.workers.every(worker => worker.messages.some(message => message.type === 'decode')));
  controller.abort(); await rejected; await nextTurn(); decoder.dispose();
  assert.ok(browserState.workers.every(worker => worker.terminations === 1 && worker.onmessage === null));
  assert.ok(browserState.workers.every(worker => Object.keys(worker._callbacks).length === 0));
  assert.equal(decoder.workerPool.length, 0); assert.equal(decoder.workerSourceURL, '');
  assert.equal(browserState.created.length, 1); assert.deepEqual(browserState.revoked, browserState.created);
});

test('a queued decode completion after cancellation disposes its actual late geometry once', async t => {
  const browserState = browser(t), transfer = transfers(), decoder = loader(t, { fetchImpl: transfer.fetchImpl });
  const geometries = [], original = decoder._createGeometry.bind(decoder);
  decoder._createGeometry = value => {
    const geometry = original(value), row = { geometry, disposals: 0 };
    geometry.addEventListener('dispose', () => row.disposals++); geometries.push(row); return geometry;
  };
  const pending = decoder.decodeGeometry(new ArrayBuffer(8), config), rejected = assert.rejects(pending, { name: 'AbortError' });
  await nextTurn();
  browserState.workers[0].finish(); // Resolves the worker callback; geometry creation is a queued microtask.
  decoder.dispose(); await rejected; await nextTurn(); decoder.dispose();
  assert.equal(geometries.length, 1); assert.equal(geometries[0].disposals, 1);
  assert.equal(browserState.workers[0].terminations, 1); assert.deepEqual(browserState.revoked, browserState.created);
});

test('successful geometry transfers to the scene owner and is not double-disposed by decoder cleanup', async t => {
  const browserState = browser(t), transfer = transfers(), decoder = loader(t, { fetchImpl: transfer.fetchImpl });
  const pending = decoder.decodeGeometry(new ArrayBuffer(8), config);
  await nextTurn(); browserState.workers[0].finish();
  const geometry = await pending; let disposals = 0;
  geometry.addEventListener('dispose', () => disposals++);
  assert.equal(geometry.getAttribute('position').count, 3);
  decoder.dispose(); decoder.dispose(); assert.equal(disposals, 0);
  geometry.dispose(); assert.equal(disposals, 1);
  assert.equal(browserState.workers[0].terminations, 1); assert.deepEqual(browserState.revoked, browserState.created);
});

test('a retry owns fresh decoder requests and survives late responses from the cancelled owner', async t => {
  const browserState = browser(t), firstTransfer = transfers({ delayed: true }), nextTransfer = transfers();
  const first = loader(t, { fetchImpl: firstTransfer.fetchImpl });
  const stale = first.decodeGeometry(new ArrayBuffer(8), config), rejected = assert.rejects(stale, { name: 'AbortError' });
  first.dispose(); await rejected;
  const second = loader(t, { fetchImpl: nextTransfer.fetchImpl });
  const fresh = second.decodeGeometry(new ArrayBuffer(9), config);
  await nextTurn();
  assert.deepEqual(firstTransfer.requests.map(row => row.url), nextTransfer.requests.map(row => row.url));
  assert.ok(firstTransfer.requests.every(row => row.signal.aborted));
  assert.ok(nextTransfer.requests.every(row => !row.signal.aborted));
  for (const row of firstTransfer.requests) row.finish(); await nextTurn();
  assert.equal(browserState.workers.length, 1); assert.equal(browserState.created.length, 1);
  assert.equal(browserState.workers[0].terminations, 0);
  browserState.workers[0].finish(); const geometry = await fresh; geometry.dispose(); second.dispose();
  assert.deepEqual(browserState.revoked, browserState.created);
});
