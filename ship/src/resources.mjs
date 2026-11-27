import { runAssetLoad } from './asset-loading.mjs';

// GLTFLoader owns parsed resources until the viewer takes ownership. Late loads
// after abort must be disposed too. Shared textures/ImageBitmaps close once.
export function disposeObject(root) {
  const geometries = new Set(), materials = new Set(), textures = new Set(), images = new Set();
  root.traverse(item => {
    if (item.geometry) geometries.add(item.geometry);
    for (const material of (Array.isArray(item.material) ? item.material : [item.material])) {
      if (material) materials.add(material);
    }
  });
  for (const material of materials) {
    for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
    for (const uniform of Object.values(material.uniforms || {})) if (uniform.value?.isTexture) textures.add(uniform.value);
  }
  for (const texture of textures) {
    for (const image of (Array.isArray(texture.image) ? texture.image : [texture.image])) if (image?.close) images.add(image);
    texture.dispose();
  }
  for (const image of images) image.close();
  for (const material of materials) material.dispose();
  for (const geometry of geometries) geometry.dispose();
}

export async function verifiedBytes(url, expected, signal, options = {}) {
  async function read({ signal: activeSignal, reportProgress }) {
    const progress = (phase, loaded) => reportProgress({ phase, loaded, total: expected.bytes });
    progress('downloading', 0);
    activeSignal.throwIfAborted();
    const response = await (options.fetchImpl || fetch)(url, { signal: activeSignal });
    if (activeSignal.aborted || !response.ok) {
      // An aborted fetch double or a late response must not leave its body open.
      void response.body?.cancel().catch(() => {});
      activeSignal.throwIfAborted();
      throw Error(`Asset HTTP ${response.status}: ${url}`);
    }
    let bytes;
    if (response.body?.getReader) {
      const buffer = new Uint8Array(expected.bytes), reader = response.body.getReader();
      let loaded = 0, complete = false;
      const cancelReader = () => { void reader.cancel(activeSignal.reason).catch(() => {}); };
      activeSignal.addEventListener('abort', cancelReader, { once: true });
      try {
        while (true) {
          const { done, value } = await reader.read();
          activeSignal.throwIfAborted();
          if (done) { complete = true; break; }
          if (!value.byteLength) continue;
          loaded += value.byteLength;
          if (loaded > expected.bytes) throw Error('Asset size mismatch');
          buffer.set(value, loaded - value.byteLength);
          progress('downloading', loaded);
        }
        if (loaded !== expected.bytes) throw Error('Asset size mismatch');
        bytes = buffer.buffer;
      } finally {
        activeSignal.removeEventListener('abort', cancelReader);
        if (!complete) cancelReader();
        reader.releaseLock();
      }
    } else {
      bytes = await response.arrayBuffer();
      activeSignal.throwIfAborted();
      if (bytes.byteLength !== expected.bytes) throw Error('Asset size mismatch');
      progress('downloading', bytes.byteLength);
    }
    progress('verifying', bytes.byteLength);
    activeSignal.throwIfAborted();
    const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(v => v.toString(16).padStart(2,'0')).join('');
    activeSignal.throwIfAborted();
    if (sha !== expected.sha256) throw Error('Asset identity mismatch');
    return bytes;
  }
  // The viewer supplies its existing load so parsing shares the same deadline.
  return options.load ? read(options.load) : runAssetLoad(read, { ...options, signal });
}
