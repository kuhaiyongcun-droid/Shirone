export const ASSET_LOAD_LIMITS = Object.freeze({ totalTimeoutMs: 300000, idleTimeoutMs: 45000 });

function timeout(message, code) {
  return Object.assign(new Error(message), { name: 'TimeoutError', code });
}

// A load owns one deadline through download, verification and decoding. Only
// received bytes extend the network idle deadline; the overall limit never moves.
export async function runAssetLoad(task, {
  signal, onProgress,
  totalTimeoutMs = ASSET_LOAD_LIMITS.totalTimeoutMs,
  idleTimeoutMs = ASSET_LOAD_LIMITS.idleTimeoutMs,
  timers = globalThis,
} = {}) {
  const controller = new AbortController();
  let totalTimer, idleTimer, settled = false, lastLoaded = 0, rejectCancellation;
  const cancelled = new Promise((_, reject) => { rejectCancellation = reject; });
  function stop(reason) {
    if (settled || controller.signal.aborted) return;
    controller.abort(reason);
    rejectCancellation(reason);
  }
  const cancel = () => stop(signal.reason || new DOMException('Asset load cancelled', 'AbortError'));
  function armIdle() {
    timers.clearTimeout(idleTimer);
    idleTimer = timers.setTimeout(() => stop(timeout('Asset download stalled', 'ASSET_IDLE_TIMEOUT')), idleTimeoutMs);
  }
  function reportProgress(progress) {
    if (settled || controller.signal.aborted) return;
    if (progress.phase === 'downloading') {
      if (progress.loaded > lastLoaded) armIdle();
      lastLoaded = progress.loaded;
    } else timers.clearTimeout(idleTimer);
    onProgress?.(progress);
  }
  signal?.addEventListener('abort', cancel, { once: true });
  if (signal?.aborted) cancel();
  else {
    totalTimer = timers.setTimeout(() => stop(timeout('Asset load timed out', 'ASSET_TOTAL_TIMEOUT')), totalTimeoutMs);
    armIdle();
  }
  try {
    return await Promise.race([
      Promise.resolve().then(() => {
        controller.signal.throwIfAborted();
        return task({ signal: controller.signal, reportProgress });
      }),
      cancelled,
    ]);
  } finally {
    settled = true;
    timers.clearTimeout(totalTimer);
    timers.clearTimeout(idleTimer);
    signal?.removeEventListener('abort', cancel);
  }
}
