import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { validateAssetContract,validateRuntimeDocuments,validateAssetSemantics,parseGlbJson } from './src/asset-contract.mjs';
import { assertViewerCompatibility, assertReferencePng } from './viewer-compatibility.mjs';

export async function inspectContractFiles(publicRoot, { expectedSource, expectedContract, requireViewerCompatibility = false } = {}) {
  const contractBytes = await readFile(path.join(publicRoot,'assets/p23-asset-contract.json'));
  if (expectedContract && (contractBytes.length !== expectedContract.bytes || createHash('sha256').update(contractBytes).digest('hex') !== expectedContract.sha256)) throw Error('Contract identity differs from explicit pin');
  const initial=validateAssetContract(JSON.parse(contractBytes), { expectedSource });
  const files=new Set(['assets/p23-asset-contract.json']);
  if(!initial.ready)return {...initial,files:[...files],asset_checks:'PENDING: no final assets supplied'};
  async function verified(descriptor) {
    const relative=descriptor.uri.slice(2),bytes=await readFile(path.join(publicRoot,relative));
    if(bytes.length!==descriptor.bytes||createHash('sha256').update(bytes).digest('hex')!==descriptor.sha256)throw Error(`Identity mismatch: ${relative}`);
    files.add(relative);return bytes;
  }
  const docs={};
  for(const [key,descriptor] of Object.entries(initial.contract.documents))docs[key]=JSON.parse(await verified(descriptor));
  const runtime=validateRuntimeDocuments(initial.contract,docs),counts={};
  const compatibility = requireViewerCompatibility ? assertViewerCompatibility(runtime) : null;
  for(const scope of ['exterior','archive']) {
    const json=parseGlbJson(await verified(initial.contract.assets[scope]));
    counts[scope]=validateAssetSemantics(scope,json,docs.semantics).size;
  }
  for(const row of docs.references.frames) {
    const bytes = await verified(row.asset);
    if (requireViewerCompatibility) assertReferencePng(bytes, row.resolution);
  }
  return {...runtime,files:[...files],asset_checks:'PASS: file identities and exact semantic coverage',mesh_node_counts:counts,compatibility};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const root=path.dirname(fileURLToPath(import.meta.url));
  const result=await inspectContractFiles(path.join(root,'public'));
  console.log(JSON.stringify({ready:result.ready,status:result.contract.status,source_scene_sha256:result.contract.source_scene.sha256,asset_checks:result.asset_checks,mesh_node_counts:result.mesh_node_counts,browser_verified:false,lighting_calibrated:false},null,2));
}
