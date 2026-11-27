import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { setImmediate as nextTurn } from 'node:timers/promises';
import * as THREE from 'three';
import { ASSET_LOAD_LIMITS } from '../src/asset-loading.mjs';
import { loadSceneAssets } from '../src/scene-loading.mjs';
import { verifiedBytes, disposeObject } from '../src/resources.mjs';

function fakeTimers() {
  let now = 0, nextId = 0;
  const tasks = new Map();
  return {
    setTimeout(callback, delay) { const id = ++nextId; tasks.set(id, { callback, at: now + delay }); return id; },
    clearTimeout(id) { tasks.delete(id); },
    get pending() { return tasks.size; },
    async advance(duration) {
      const end = now + duration;
      for (;;) {
        const first = [...tasks].filter(([, row]) => row.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!first) break;
        const [id, row] = first; now = row.at; tasks.delete(id); row.callback(); await nextTurn();
      }
      now = end; await nextTurn();
    },
  };
}
const entries = [{ key: 'exterior', bytes: 6 }, { key: 'archive', bytes: 4 }];
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
function parsed(key) {
  return { key, disposed: 0 };
}
function controlled(options = {}) {
  const transfers = {}, disposals = [], progress = [], timers = fakeTimers();
  const promise = loadSceneAssets(entries, {
    timers, onProgress: value => progress.push(value), dispose: value => { value.disposed++; disposals.push(value.key); },
    load: (key, context) => {
      const task = deferred(); transfers[key] = { ...task, ...context };
      context.reportProgress({ phase: 'downloading', loaded: 0, total: entries.find(entry => entry.key === key).bytes });
      return task.promise;
    }, ...options,
  });
  return { transfers, disposals, progress, timers, promise };
}

test('both assets start together and the scene waits for both parsed results with one byte total', async () => {
  const task = controlled(); let ready = false;
  task.promise.then(() => { ready = true; }); await nextTurn();
  assert.deepEqual(Object.keys(task.transfers), ['exterior', 'archive']);
  task.transfers.exterior.reportProgress({ phase: 'downloading', loaded: 3, total: 999 });
  task.transfers.archive.reportProgress({ phase: 'downloading', loaded: 2, total: 999 });
  assert.equal(task.progress.at(-1).loaded, 5); assert.equal(task.progress.at(-1).total, 10);
  assert.equal(task.progress.at(-1).scope, 'scene');
  const exterior = parsed('exterior'), archive = parsed('archive');
  task.transfers.exterior.resolve(exterior); await nextTurn();
  assert.equal(ready, false); assert.equal(task.progress.at(-1).phase, 'downloading');
  assert.equal(task.progress.at(-1).loaded, 8);
  task.transfers.archive.reportProgress({ phase: 'verifying', loaded: 4, total: 4 });
  assert.equal(task.progress.at(-1).phase, 'verifying');
  task.transfers.archive.reportProgress({ phase: 'decoding', loaded: 4, total: 4 });
  assert.equal(task.progress.at(-1).phase, 'decoding');
  task.transfers.archive.resolve(archive);
  assert.deepEqual(await task.promise, { exterior, archive });
  assert.equal(ready, true); assert.ok(task.progress.every(value => value.total === 10));
  assert.equal(task.progress.at(-1).loaded, 10); assert.deepEqual(task.disposals, []); assert.equal(task.timers.pending, 0);
});

test('aggregate phase stays downloading while either transfer is receiving bytes', async () => {
  const task = controlled(); await nextTurn();
  task.transfers.exterior.reportProgress({ phase: 'decoding', loaded: 6, total: 6 });
  task.transfers.archive.reportProgress({ phase: 'downloading', loaded: 1, total: 4 });
  assert.equal(task.progress.at(-1).phase, 'downloading'); assert.equal(task.progress.at(-1).loaded, 7);
  task.transfers.archive.reportProgress({ phase: 'verifying', loaded: 4, total: 4 });
  assert.equal(task.progress.at(-1).phase, 'verifying');
  task.transfers.exterior.resolve(parsed('exterior')); task.transfers.archive.resolve(parsed('archive')); await task.promise;
});

test('failure of either asset cancels its peer and disposes that peer even if its parser completes later', async () => {
  for (const failing of ['exterior', 'archive']) {
    const task = controlled(), rejected = assert.rejects(task.promise, /broken asset/); await nextTurn();
    const peer = failing === 'exterior' ? 'archive' : 'exterior';
    task.transfers[failing].reject(Error('broken asset')); await rejected;
    assert.equal(task.transfers[peer].signal.aborted, true);
    const late = parsed(peer), count = task.progress.length;
    task.transfers[peer].reportProgress({ phase: 'decoding', loaded: 4, total: 4 });
    task.transfers[peer].resolve(late); await nextTurn();
    assert.equal(late.disposed, 1); assert.deepEqual(task.disposals, [peer]);
    assert.equal(task.progress.length, count); assert.equal(task.timers.pending, 0);
  }
});

test('a verified and parsed peer is released when the other asset fails', async () => {
  const task = controlled(), rejected = assert.rejects(task.promise, /Asset identity mismatch/); await nextTurn();
  const exterior = parsed('exterior'); task.transfers.exterior.resolve(exterior); await nextTurn();
  task.transfers.archive.reject(Error('Asset identity mismatch')); await rejected;
  assert.equal(exterior.disposed, 1); assert.deepEqual(task.disposals, ['exterior']); assert.equal(task.timers.pending, 0);
});

test('one cancellation stops both requests promptly; retry has fresh owners and ignores late results', async () => {
  const controller = new AbortController(), first = controlled({ signal: controller.signal });
  const rejected = assert.rejects(first.promise, error => error.name === 'AbortError'); await nextTurn();
  controller.abort(); await rejected;
  assert.ok(Object.values(first.transfers).every(row => row.signal.aborted));
  const second = controlled(); await nextTurn();
  const stale = [parsed('exterior'), parsed('archive')];
  stale.forEach(value => first.transfers[value.key].resolve(value)); await nextTurn();
  assert.ok(stale.every(value => value.disposed === 1)); assert.deepEqual(second.disposals, []);
  const fresh = [parsed('exterior'), parsed('archive')]; fresh.forEach(value => second.transfers[value.key].resolve(value));
  assert.deepEqual(await second.promise, Object.fromEntries(fresh.map(value => [value.key, value])));
  assert.ok(fresh.every(value => value.disposed === 0)); assert.equal(first.timers.pending + second.timers.pending, 0);
});

test('cancellation frees an already prepared half before the other parser finishes', async () => {
  const controller = new AbortController(), task = controlled({ signal: controller.signal });
  const rejected = assert.rejects(task.promise, error => error.name === 'AbortError'); await nextTurn();
  const exterior = parsed('exterior'); task.transfers.exterior.resolve(exterior); await nextTurn();
  controller.abort(); await rejected; assert.equal(exterior.disposed, 1);
  const archive = parsed('archive'); task.transfers.archive.resolve(archive); await nextTurn();
  assert.equal(archive.disposed, 1); assert.equal(exterior.disposed, 1);
});

test('a pre-cancelled scene starts neither asset and creates no remaining timers', async () => {
  const controller = new AbortController(); controller.abort(); const task = controlled({ signal: controller.signal });
  await assert.rejects(task.promise, error => error.name === 'AbortError');
  assert.deepEqual(task.transfers, {}); assert.deepEqual(task.progress, []); assert.equal(task.timers.pending, 0);
});

test('a busy peer cannot conceal the other transfer being idle for 45 seconds', async () => {
  const task = controlled(), rejected = assert.rejects(task.promise, error => error.code === 'ASSET_IDLE_TIMEOUT'); await nextTurn();
  await task.timers.advance(30000); task.transfers.exterior.reportProgress({ phase: 'downloading', loaded: 1, total: 6 });
  await task.timers.advance(15000); await rejected;
  assert.ok(Object.values(task.transfers).every(row => row.signal.aborted)); assert.equal(task.timers.pending, 0);
  for (const key of ['exterior', 'archive']) task.transfers[key].resolve(parsed(key)); await nextTurn();
  assert.equal(task.disposals.length, 2);
});

test('verification and parsing across both assets share one fixed 300-second deadline', async () => {
  const task = controlled(), rejected = assert.rejects(task.promise, error => error.code === 'ASSET_TOTAL_TIMEOUT'); await nextTurn();
  task.transfers.exterior.reportProgress({ phase: 'decoding', loaded: 6, total: 6 });
  task.transfers.archive.reportProgress({ phase: 'verifying', loaded: 4, total: 4 });
  await task.timers.advance(ASSET_LOAD_LIMITS.idleTimeoutMs + 1);
  assert.ok(Object.values(task.transfers).every(row => !row.signal.aborted));
  await task.timers.advance(ASSET_LOAD_LIMITS.totalTimeoutMs - ASSET_LOAD_LIMITS.idleTimeoutMs - 1); await rejected;
  assert.ok(Object.values(task.transfers).every(row => row.signal.aborted)); assert.equal(task.timers.pending, 0);
  for (const key of ['exterior', 'archive']) task.transfers[key].resolve(parsed(key)); await nextTurn();
});

test('real streamed SHA validation completes both assets before ownership transfer; corrupt archive cancels exterior', async () => {
  const content = { exterior: Uint8Array.of(1, 2, 3, 4, 5, 6), archive: Uint8Array.of(7, 8, 9, 10) };
  const descriptors = Object.fromEntries(Object.entries(content).map(([key, bytes]) => [key, {
    bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex'),
  }]));
  const requests = [], disposed = [];
  const result = await loadSceneAssets(entries, {
    dispose: value => disposed.push(value.key),
    load: async (key, context) => {
      const bytes = await verifiedBytes('/' + key + '.glb', descriptors[key], context.signal, { load: context,
        fetchImpl: async url => { requests.push(url); return new Response(content[key]); } });
      assert.deepEqual(new Uint8Array(bytes), content[key]);
      context.reportProgress({ phase: 'decoding', loaded: bytes.byteLength, total: bytes.byteLength });
      return parsed(key);
    },
  });
  assert.deepEqual(requests, ['/exterior.glb', '/archive.glb']); assert.deepEqual(Object.keys(result).sort(), ['archive', 'exterior']);
  assert.deepEqual(disposed, []);
  let cancelled = 0;
  await assert.rejects(loadSceneAssets(entries, {
    dispose: value => disposed.push(value.key),
    load: async (key, context) => {
      await verifiedBytes('/' + key + '.glb', descriptors[key], context.signal, { load: context,
        fetchImpl: async () => key === 'archive' ? new Response(Uint8Array.of(0, 0, 0, 0))
          : new Response(new ReadableStream({ cancel() { cancelled++; } })),
      });
      return parsed(key);
    },
  }), /Asset identity mismatch/);
  await nextTurn(); assert.equal(cancelled, 1);
});

test('the scene owns both parsed object trees until final disposal, with shared resources freed once', async () => {
  const controller = new AbortController(), counts = new Map(), objects = {};
  function tracked(key) {
    const root = new THREE.Group(), geometry = new THREE.BoxGeometry(1, 1, 1), texture = new THREE.Texture();
    const image = { close() { counts.set(key + ':image', (counts.get(key + ':image') || 0) + 1); } }; texture.image = image;
    const material = new THREE.MeshBasicMaterial({ map: texture });
    for (const [kind, resource] of [['geometry', geometry], ['material', material], ['texture', texture]]) {
      resource.addEventListener('dispose', () => counts.set(key + ':' + kind, (counts.get(key + ':' + kind) || 0) + 1));
    }
    root.add(new THREE.Mesh(geometry, material), new THREE.Mesh(geometry, material)); objects[key] = root; return root;
  }
  const result = await loadSceneAssets(entries, {
    signal: controller.signal, load: async key => tracked(key), dispose: disposeObject,
  });
  const scene = new THREE.Scene(); scene.add(result.exterior, result.archive);
  controller.abort(); assert.equal(counts.size, 0); // The loader no longer owns a successful set.
  for (let i = 0; i < 20; i++) { result.archive.visible = i % 2 === 0; assert.equal(result.archive, objects.archive); }
  assert.equal(counts.size, 0); disposeObject(scene);
  assert.equal(counts.size, 8); assert.ok([...counts.values()].every(count => count === 1));
});
