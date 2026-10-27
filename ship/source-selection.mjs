import { readFile, realpath } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { validateDescriptor } from './src/asset-contract.mjs';

export const SHIP_ROOT = path.dirname(fileURLToPath(import.meta.url));
export const CONTRACT_URI = './assets/p23-asset-contract.json';
export const SUPPORT_FILES = ['assets/favicon.svg', 'assets/THREE-LICENSE.txt', 'assets/draco/draco_wasm_wrapper.js', 'assets/draco/draco_decoder.wasm'];
export const DEFAULT_PIN = Object.freeze({
  source: { stage: 'P25', sha256: '626188407125e818142c15c9e40f9664ef23d66e63fe7e0a1f9b47a4ecc6914d' },
  contract: { uri: CONTRACT_URI, bytes: 1686, sha256: 'eb5f10363b5aa0f6e031f47191a983c50c51dd194a11e2094b51f84d295ba690' },
});
export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
export function assertSourcePin(source) {
  // One reviewed composite-stage delivery; do not broaden the stage grammar.
  const finalP26P27 = source?.stage === 'P26-P27' && source?.sha256 === 'dd35a7b43c94ba22a03aa0f27e0b88de549cce594971829c9e0e6913e04d0339';
  if (!( /^P[0-9]+$/.test(source?.stage || '') || finalP26P27) || !/^[a-f0-9]{64}$/.test(source?.sha256 || '')) throw Error('Explicit stage/source SHA256 required');
}
export async function readSourceSelection({ snapshot, snapshotSha256 } = {}) {
  if (!snapshot) {
    if (snapshotSha256) throw Error('Snapshot hash supplied without snapshot');
    return { publicRoot: path.join(SHIP_ROOT, 'public'), ...structuredClone(DEFAULT_PIN), snapshot: null };
  }
  if (!/^public-[a-z0-9][a-z0-9-]*\/snapshot\.json$/.test(snapshot) || !/^[a-f0-9]{64}$/.test(snapshotSha256 || ''))
    throw Error('Snapshot must be public-NAME/snapshot.json with an explicit SHA256');
  const filename = path.join(SHIP_ROOT, snapshot), actual = await realpath(filename);
  if (actual.toLowerCase() !== filename.toLowerCase()) throw Error('Snapshot aliases/symlinks are forbidden');
  const bytes = await readFile(filename);
  if (sha256(bytes) !== snapshotSha256) throw Error('Snapshot SHA256 differs from explicit pin');
  const record = JSON.parse(bytes);
  if (record.schema !== 'ship-source-snapshot-v1' || record.publicDirectory !== snapshot.split('/')[0] || record.viewerInterface !== 'ship-seven-views-v1') throw Error('Invalid snapshot interface');
  assertSourcePin(record.source); validateDescriptor(record.contract);
  if (record.contract.uri !== CONTRACT_URI || record.browserVerified !== false || record.lightingCalibrated !== false) throw Error('Snapshot contract/acceptance differs');
  return { publicRoot: path.dirname(filename), source: record.source, contract: record.contract, snapshot, snapshotSha256 };
}
