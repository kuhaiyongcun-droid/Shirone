import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';

// The pinned Three r186 loader does not make dispose terminal: pending decoder
// libraries can still allocate a blob URL/worker, and terminated worker tasks
// remain pending. Keep those asynchronous boundaries inside this viewer's owner.
export class SceneDracoLoader extends DRACOLoader {
  constructor({ signal, fetchImpl = globalThis.fetch } = {}) {
    super();
    this._lifetime = new AbortController();
    this._fetch = fetchImpl;
    this._pendingLibraries = new Set();
    this._discardedGeometry = new WeakSet();
    this._externalSignal = signal;
    this._cancel = () => this.dispose(signal.reason);
    signal?.addEventListener('abort', this._cancel, { once: true });
    if (signal?.aborted) this._cancel();
  }

  _assertAlive() { this._lifetime.signal.throwIfAborted(); }

  // Guard the actual callback, not a preceding promise: cancellation can occur
  // between microtasks. Three calls these private promise-like results with then.
  _guard(pending) {
    return { then: (fulfilled, rejected) => pending.then(value => {
      try { this._assertAlive(); }
      catch (error) { if (rejected) return rejected(error); throw error; }
      return fulfilled ? fulfilled(value) : value;
    }, rejected) };
  }

  _loadLibrary(url, responseType) {
    this._assertAlive();
    const signal = this._lifetime.signal;
    // Native fetch avoids Three's global in-flight URL sharing: cancelling an
    // obsolete viewer must not cancel a retry that needs the same decoder URL.
    const transfer = (async () => {
      const response = await this._fetch(url, { signal,
        credentials: this.withCredentials ? 'include' : 'same-origin' });
      if (signal.aborted || !response.ok) {
        void response.body?.cancel().catch(() => {});
        signal.throwIfAborted();
        throw Error(`Decoder HTTP ${response.status}: ${url}`);
      }
      const value = await (responseType === 'arraybuffer' ? response.arrayBuffer() : response.text());
      signal.throwIfAborted();
      return value;
    })();
    return new Promise((resolve, reject) => {
      const cancel = () => reject(signal.reason);
      this._pendingLibraries.add(cancel);
      transfer.then(value => { this._pendingLibraries.delete(cancel); resolve(value); },
        error => { this._pendingLibraries.delete(cancel); reject(error); });
      if (signal.aborted) cancel();
    });
  }

  _initDecoder() {
    this._assertAlive();
    const pending = super._initDecoder();
    if (this._watchedDecoder !== pending) {
      this._watchedDecoder = pending;
      // Also close a URL if disposal fell between already-resolved libraries
      // and Three's queued URL-creation microtask. No worker can use that URL.
      pending.then(() => { if (this._lifetime.signal.aborted) this._releaseDecoderURL(); }, () => {});
    }
    return this._guard(pending);
  }

  _getWorker(taskID, taskCost) {
    this._assertAlive();
    return this._guard(super._getWorker(taskID, taskCost));
  }

  decodeGeometry(buffer, taskConfig) {
    try {
      this._assertAlive();
      return super.decodeGeometry(buffer, taskConfig).then(geometry => {
        if (this._lifetime.signal.aborted) {
          if (!this._discardedGeometry.has(geometry)) {
            this._discardedGeometry.add(geometry); geometry.dispose();
          }
          this._assertAlive();
        }
        return geometry;
      });
    } catch (error) { return Promise.reject(error); }
  }

  _releaseDecoderURL() {
    if (this.workerSourceURL) URL.revokeObjectURL(this.workerSourceURL);
    this.workerSourceURL = '';
  }

  dispose(reason = new DOMException('Scene decoder disposed', 'AbortError')) {
    if (this._lifetime.signal.aborted) return this;
    this._lifetime.abort(reason);
    this._externalSignal?.removeEventListener('abort', this._cancel);
    for (const cancel of this._pendingLibraries) cancel();
    this._pendingLibraries.clear();
    for (const worker of this.workerPool) {
      worker.onmessage = null;
      for (const callback of Object.values(worker._callbacks)) callback.reject(reason);
    }
    super.dispose();
    this.workerSourceURL = '';
    return this;
  }
}
