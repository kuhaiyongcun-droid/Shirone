import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { validateAssetContract, validateRuntimeDocuments, loadContractBundle } from '../src/asset-contract.mjs';
import { DEFAULT_PIN, assertSourcePin, readSourceSelection, sha256 } from '../source-selection.mjs';
import { REQUIRED_VIEWS, assertViewerCompatibility, assertReferencePng } from '../viewer-compatibility.mjs';
import { validateHandoff, safeRelative } from '../src/handoff-contract.mjs';

import { PIN,selected,bytes,contract,docs,readAsset } from './fixtures/release-source.mjs';
const runtime = () => validateRuntimeDocuments(structuredClone(contract), structuredClone(docs));

test('explicit release snapshot binds the actual P26-P27 mother model and contract bytes', async () => {
  const current = await readSourceSelection({snapshot:PIN.snapshot,snapshotSha256:PIN.snapshotSha256});
  assert.deepEqual(current,selected);
  assert.deepEqual(selected.source, contract.source_scene);
  assert.equal(selected.contract.sha256, sha256(bytes)); assert.equal(selected.contract.bytes, bytes.length);
  assert.equal(selected.snapshot, PIN.snapshot);
});
test('nondefault source requires an exact externally supplied stage and SHA, never a relaxed stage regex', () => {
  const candidate = structuredClone(contract); candidate.source_scene = {stage:'P26',sha256:sha256('synthetic-new-source-only-for-tests')};
  assert.throws(() => validateAssetContract(candidate), /P25 final source/);
  assert.equal(validateAssetContract(candidate, {expectedSource:candidate.source_scene}).ready, true);
  for (const expectedSource of [DEFAULT_PIN.source, {stage:'P26',sha256:contract.source_scene.sha256}, {stage:'P26'}, {}])
    assert.throws(() => validateAssetContract(candidate, {expectedSource}), /pin|identity/);
});

test('both composite-stage gates accept only the reviewed P26-P27 source and retain the P25 default', () => {
  const source = {stage:'P26-P27',sha256:'dd35a7b43c94ba22a03aa0f27e0b88de549cce594971829c9e0e6913e04d0339'};
  const candidate = structuredClone(contract); candidate.source_scene = source;
  assert.doesNotThrow(() => assertSourcePin(source));
  assert.equal(validateAssetContract(candidate,{expectedSource:source}).ready,true);
  assert.throws(() => validateAssetContract(candidate),/P25 final source/);
  assert.doesNotThrow(() => assertSourcePin(DEFAULT_PIN.source));
  const legacy=structuredClone(contract);legacy.source_scene=structuredClone(DEFAULT_PIN.source);
  assert.equal(validateAssetContract(legacy,{expectedSource:DEFAULT_PIN.source}).ready,true);
  for (const wrong of [
    {...source,sha256:sha256('unreviewed P26-P27 scene')},
    {...source,sha256:source.sha256.toUpperCase()},
    {stage:source.stage},
    {...source,stage:'P26-P28'},
    {...source,stage:'P27-P26'},
    {...source,stage:'p26-p27'},
    {...source,stage:'P26-P27 '},
  ]) {
    assert.throws(() => assertSourcePin(wrong),/Explicit stage\/source SHA256/);
    const selfConsistentButUnreviewed = structuredClone(candidate); selfConsistentButUnreviewed.source_scene = wrong;
    assert.throws(() => validateAssetContract(selfConsistentButUnreviewed,{expectedSource:wrong}),/explicit source identity pin/);
  }
  for (const stage of ['P26','P27']) assert.throws(() => validateAssetContract(candidate,{expectedSource:{...source,stage}}),/source identity differs/);
});

test('P26-P27 handoff keeps its actual stage and rejects a changed exact source before import', () => {
  const source={stage:'P26-P27',sha256:'dd35a7b43c94ba22a03aa0f27e0b88de549cce594971829c9e0e6913e04d0339'};
  const value={schema:'ship-web-handoff-v1',complete:true,source,contract:DEFAULT_PIN.contract,publicDirectory:'public',browserVerified:false,lightingCalibrated:false,evidence:['geometry','protection','same-camera'].map(kind=>({kind,status:'PASS',sourceSceneSha256:source.sha256,path:'evidence/'+kind+'.json',bytes:1,sha256:sha256('synthetic evidence only')}))};
  assert.equal(validateHandoff(value,source).source.stage,'P26-P27');
  assert.throws(() => validateHandoff(value,{...source,sha256:sha256('wrong final source')}),/Explicit stage\/source SHA256/);
  for(const stage of ['P26','P27']) assert.throws(() => validateHandoff({...value,source:{...source,stage}},source),/Handoff source differs/);
});
test('production interface retains seven exact cameras and fourteen 8:5 references', () => {
  const result = assertViewerCompatibility(runtime()); assert.equal(result.views,7); assert.equal(result.referenceFrames,14); assert.equal(REQUIRED_VIEWS.length,7);
  for (const removed of ['whole-underside','archive-upper','vestibule']) {
    const candidate=runtime(); candidate.cameras.views=candidate.cameras.views.filter(v=>v.id!==removed);
    assert.throws(()=>assertViewerCompatibility(candidate), new RegExp('missing views: '+removed));
  }
});
test('camera aliases, projection changes, empty per-view lighting and mismatched image frames fail closed', () => {
  const changes=[r=>r.cameras.views[0].projection='PERSP',r=>r.cameras.defaults.archive='archive-entry',r=>r.cameras.reference_resolution=[1200,800],r=>r.references.frames[0].resolution=[1600,1000],r=>r.lighting.lights.forEach(l=>l.intensity_web=0)];
  for(const change of changes){const candidate=runtime();change(candidate);assert.throws(()=>assertViewerCompatibility(candidate));}
});
test('actual PNG header matches published dimensions; mislabeled dimensions cannot pass',async()=>{
  const row=docs.references.frames[0],png=await readAsset(row.asset);
  assert.doesNotThrow(()=>assertReferencePng(png,row.resolution));
  assert.throws(()=>assertReferencePng(png,[1600,1000]),/dimensions/);
  assert.throws(()=>assertReferencePng(Buffer.from('not a PNG'),row.resolution),/actual PNG/);
});
test('top-level network contract is hash-checked before any runtime documents load',async()=>{
  const original=globalThis.fetch;let requests=0;
  globalThis.fetch=async()=>{requests++;return new Response(bytes);};
  try{await assert.rejects(loadContractBundle('http://127.0.0.1:4177/assets/p23-asset-contract.json',undefined,{source:PIN.source,contract:{...PIN.contract,sha256:sha256('wrong contract')}}),/identity mismatch/);assert.equal(requests,1);}
  finally{globalThis.fetch=original;}
});
test('handoff must include distinct successful geometry/protection/same-camera records bound to the chosen source',()=>{
  const value={schema:'ship-web-handoff-v1',complete:true,source:DEFAULT_PIN.source,contract:DEFAULT_PIN.contract,publicDirectory:'public',browserVerified:false,lightingCalibrated:false,evidence:['geometry','protection','same-camera'].map(kind=>({kind,status:'PASS',sourceSceneSha256:DEFAULT_PIN.source.sha256,path:'evidence/'+kind+'.json',bytes:1,sha256:sha256('synthetic evidence')}))};
  assert.equal(validateHandoff(value,DEFAULT_PIN.source),value);
  for(const change of [v=>v.complete=false,v=>v.evidence.pop(),v=>v.evidence[0].status='PENDING',v=>v.evidence[0].sourceSceneSha256=sha256('wrong'),v=>v.evidence[0].path='../outside.json',v=>v.browserVerified=true]){
    const candidate=structuredClone(value);change(candidate);assert.throws(()=>validateHandoff(candidate,DEFAULT_PIN.source));
  }
});
test('input/snapshot selectors reject path traversal, absent SHA and remote paths before reading files',async()=>{
  for(const value of ['../outside','/absolute','D:/outside','https://example.test/a','a//b','a/../b'])assert.throws(()=>safeRelative(value));
  for(const options of [{snapshot:'public-p26-v1/snapshot.json'},{snapshot:'../outside.json',snapshotSha256:sha256('x')},{snapshotSha256:sha256('x')}])await assert.rejects(readSourceSelection(options));
});
