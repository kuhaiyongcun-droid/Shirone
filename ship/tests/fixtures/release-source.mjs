import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { readSourceSelection, sha256 } from '../../source-selection.mjs';

export const PIN=JSON.parse(await readFile(new URL('./release-source.json',import.meta.url),'utf8'));
export const selected=await readSourceSelection({snapshot:PIN.snapshot,snapshotSha256:PIN.snapshotSha256});
assert.deepEqual(selected.source,PIN.source);
assert.deepEqual(selected.contract,PIN.contract);
export async function readAsset(descriptor){
  assert.match(descriptor.uri,/^\.\/assets\//);
  const bytes=await readFile(path.join(selected.publicRoot,descriptor.uri.slice(2)));
  assert.equal(bytes.length,descriptor.bytes,descriptor.uri+' byte length');
  assert.equal(sha256(bytes),descriptor.sha256,descriptor.uri+' SHA256');
  return bytes;
}
export const bytes=await readAsset(selected.contract);
export const contract=JSON.parse(bytes),docs={};
for(const [key,row] of Object.entries(contract.documents))docs[key]=JSON.parse(await readAsset(row));
