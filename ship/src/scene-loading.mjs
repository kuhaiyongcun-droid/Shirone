import { ASSET_LOAD_LIMITS, runAssetLoad } from './asset-loading.mjs';

// One user operation owns every scene asset until all assets can be handed to
// the viewer together. Individual transfers keep their own inactivity limit;
// the scene has one non-renewable deadline, including verification and parsing.
export async function loadSceneAssets(entries, {
  load, dispose, signal, onProgress, timers = globalThis,
  totalTimeoutMs = ASSET_LOAD_LIMITS.totalTimeoutMs,
  idleTimeoutMs = ASSET_LOAD_LIMITS.idleTimeoutMs,
} = {}) {
  if (!entries.length || new Set(entries.map(entry => entry.key)).size !== entries.length
    || entries.some(entry => !Number.isSafeInteger(entry.bytes) || entry.bytes <= 0)) {
    throw Error('Distinct scene assets with pinned byte totals required');
  }
  const controller = new AbortController(), owned = new Map();
  const progress = new Map(entries.map(entry => [entry.key, {
    key: entry.key, phase: 'downloading', loaded: 0, total: entry.bytes,
  }]));
  let timer, closed = false;
  const cancel = () => controller.abort(signal.reason || new DOMException('Scene load cancelled', 'AbortError'));
  function publish() {
    if (closed || controller.signal.aborted) return;
    const assets = [...progress.values()].map(value => ({ ...value }));
    const phase = assets.some(value => value.phase === 'downloading') ? 'downloading'
      : assets.some(value => value.phase === 'verifying') ? 'verifying' : 'decoding';
    onProgress?.({ scope: 'scene', phase, assets,
      loaded: assets.reduce((sum, value) => sum + value.loaded, 0),
      total: assets.reduce((sum, value) => sum + value.total, 0) });
  }
  signal?.addEventListener('abort', cancel, { once: true });
  if (signal?.aborted) cancel();
  else timer = timers.setTimeout(() => controller.abort(Object.assign(new Error('Scene load timed out'), {
    name: 'TimeoutError', code: 'ASSET_TOTAL_TIMEOUT',
  })), totalTimeoutMs);
  try {
    controller.signal.throwIfAborted();
    publish();
    await Promise.all(entries.map(entry => runAssetLoad(async context => {
      const value = await load(entry.key, context);
      // Parsers cannot always be interrupted. A result that arrives after the
      // scene failed/cancelled still belongs to this operation, never a retry.
      if (context.signal.aborted || controller.signal.aborted || closed) {
        dispose(value);
        context.signal.throwIfAborted();
        controller.signal.throwIfAborted();
        throw Error('Scene load closed');
      }
      owned.set(entry.key, value);
      progress.set(entry.key, { key: entry.key, phase: 'ready', loaded: entry.bytes, total: entry.bytes });
      publish();
      return value;
    }, {
      signal: controller.signal, timers, totalTimeoutMs, idleTimeoutMs,
      onProgress: value => {
        // Trusted contract bytes remain the denominator, independent of HTTP headers.
        progress.set(entry.key, { ...value, key: entry.key, total: entry.bytes });
        publish();
      },
    })));
    controller.signal.throwIfAborted();
    const result = Object.fromEntries(owned);
    owned.clear(); // Ownership transfers exactly once, after the entire set is ready.
    return result;
  } catch (error) {
    controller.abort(error);
    for (const value of owned.values()) dispose(value);
    owned.clear();
    throw error;
  } finally {
    closed = true;
    timers.clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
  }
}
