import { verifiedBytes } from './resources.mjs';
import { lightAppliesToView } from './runtime-guards.mjs';

const hash = /^[a-f0-9]{64}$/;
const scopes = ['exterior', 'archive'];
const finite = value => typeof value === 'number' && Number.isFinite(value);
const vector = value => Array.isArray(value) && value.length === 3 && value.every(finite);
function check(value, message) { if (!value) throw Error(`P23 contract: ${message}`); }
export function localAssetUri(uri) {
  check(typeof uri === 'string' && /^\.\/assets\/[A-Za-z0-9_./-]+$/.test(uri), 'asset URI must be local ./assets/...');
  check(!uri.includes('..') && !uri.includes('//') && !uri.endsWith('/'), 'unsafe asset URI');
  return uri;
}
export function validateDescriptor(row) {
  check(row && hash.test(row.sha256) && Number.isSafeInteger(row.bytes) && row.bytes > 0, 'real SHA256/byte count required');
  localAssetUri(row.uri); return row;
}
export function validateAssetContract(value, { expectedSource } = {}) {
  check(value?.schema_version === 1 && typeof value.revision === 'string', 'schema/revision required');
  check(value.verification?.browser_verified === false && value.verification?.lighting_calibrated === false, 'unverified preparation cannot assert acceptance');
  const units = value.coordinate_system;
  check(units?.gltf_up_axis === 'Y' && units.source_length_unit === 'meter' && units.root_scale === .01, 'meter GLB must have one .01 root scale');
  check(JSON.stringify(units.model_rotation) === '[0,0,0]', 'GLB is already Y-up; no second rotation');
  if (expectedSource !== undefined) {
    // Keep this runtime gate aligned with the exact offline source-selection pin.
    const finalP26P27 = expectedSource?.stage === 'P26-P27' && expectedSource?.sha256 === 'dd35a7b43c94ba22a03aa0f27e0b88de549cce594971829c9e0e6913e04d0339';
    check(typeof expectedSource?.stage === 'string' && (/^P[0-9]+$/.test(expectedSource.stage) || finalP26P27) && hash.test(expectedSource.sha256), 'explicit source identity pin required');
    check(value.source_scene?.stage === expectedSource.stage && value.source_scene?.sha256 === expectedSource.sha256, 'source identity differs from explicit pin');
  } else check(value.source_scene?.stage === 'P25', 'P25 final source required unless an explicit source identity is supplied');
  if (value.status === 'awaiting-final-assets') {
    check(value.source_scene.sha256 === null && value.assets === null && value.documents === null, 'pending contract must not contain substitute assets or invented hashes');
    return { ready: false, contract: value };
  }
  check(value.status === 'ready-for-review' && hash.test(value.source_scene.sha256), 'accepted source identity required');
  for (const scope of scopes) validateDescriptor(value.assets?.[scope]);
  check(Object.keys(value.assets).sort().join(',') === 'archive,exterior', 'exactly two asset scopes required');
  check(value.assets.exterior.sha256 !== value.assets.archive.sha256 && value.assets.exterior.uri !== value.assets.archive.uri, 'exterior and archive must be distinct assets');
  for (const key of ['semantics','cameras','lighting','references']) validateDescriptor(value.documents?.[key]);
  check(Object.keys(value.documents).sort().join(',') === 'cameras,lighting,references,semantics', 'exactly four runtime documents required');
  return { ready: true, contract: value };
}
export function sourcePointToWeb([x,y,z]) { return [x * .01, z * .01, -y * .01]; }
export function sourceDirectionToWeb([x,y,z]) { return [x,z,-y]; }
export function sourceMatrixToWeb(rows) {
  const result=rows.map(row=>[...row]);
  for(let i=0;i<3;i++)result[i][3]*=.01;
  return [result[0],result[2],result[1].map(n=>-n),result[3]];
}
export function semanticAssignments(semantics, scope) {
  const expected = scope === 'exterior' ? ['hull','archive_shell','reserved'] : ['archive_interior','reserved'];
  const groups = semantics.assets?.[scope]; check(groups && JSON.stringify(Object.keys(groups).sort()) === JSON.stringify(expected.sort()), `complete ${scope} role groups required`);
  const assignments = new Map();
  for (const [role, names] of Object.entries(groups)) {
    check(Array.isArray(names), `${role} exact node list required`);
    for (const name of names) { check(typeof name === 'string' && name.length && !assignments.has(name), 'duplicate/invalid semantic node'); assignments.set(name,role); }
  }
  check(assignments.size > 0, 'empty semantic asset');
  check(scope !== 'exterior' || groups.archive_shell.length > 0, 'real archive shell required');
  check(scope !== 'archive' || groups.archive_interior.length > 0, 'real archive interior required');
  return assignments;
}
export function validateRuntimeDocuments(contract, docs) {
  for (const [name, doc] of Object.entries(docs)) check(doc?.schema_version === 1 && doc.source_scene_sha256 === contract.source_scene.sha256, `${name} source binding differs`);
  const ex = semanticAssignments(docs.semantics, 'exterior'), ar = semanticAssignments(docs.semantics, 'archive');
  check(![...ex.keys()].some(name => ar.has(name)), 'exterior/archive nodes overlap; duplicate interior forbidden');
  const c = docs.cameras;
  check(c.source_coordinate_system === 'Blender_Z_up' && vector(c.archive_anchor_source), 'camera coordinate/anchor required');
  check(Array.isArray(c.reference_resolution) && c.reference_resolution.length === 2 && c.reference_resolution.every(v => finite(v) && v > 0), 'reference resolution required');
  check(Array.isArray(c.views) && c.views.length > 1, 'published view set required');
  const ids = new Set();
  for (const view of c.views) {
    check(typeof view.id === 'string' && !ids.has(view.id) && scopes.includes(view.scope), 'unique view/scope required'); ids.add(view.id);
    check(view.label?.zh_CN && view.label?.en && vector(view.target_source), 'camera labels/target required');
    check(Array.isArray(view.hidden_shell_nodes)&&new Set(view.hidden_shell_nodes).size===view.hidden_shell_nodes.length&&view.hidden_shell_nodes.every(name=>ex.get(name)==='archive_shell'),'hidden_shell_nodes must be unique exact archive_shell names only');
    check(view.scope!=='exterior'||view.hidden_shell_nodes.length===0,'exterior reference views cannot hide shell geometry');
    check(Array.isArray(view.matrix_world) && view.matrix_world.length === 4 && view.matrix_world.every(row => Array.isArray(row) && row.length === 4 && row.every(finite)), 'camera matrix required');
    check(JSON.stringify(view.matrix_world[3]) === '[0,0,0,1]', 'affine camera matrix required');
    const axes=[0,1,2].map(col=>view.matrix_world.slice(0,3).map(row=>row[col]));
    for(let i=0;i<3;i++)for(let j=0;j<3;j++)check(Math.abs(axes[i].reduce((sum,n,k)=>sum+n*axes[j][k],0)-(i===j?1:0))<1e-5,'camera matrix must be rigid without scale');
    check(['PERSP','ORTHO'].includes(view.projection) && (view.sensor_fit === 'HORIZONTAL' || (view.sensor_fit === 'AUTO' && c.reference_resolution[0] >= c.reference_resolution[1])), 'explicit projection and effective horizontal source sensor fit required');
    check(view.shift_x===0 && view.shift_y===0, 'source camera must declare zero lens shift');
    check(finite(view.clip_start_source)&&finite(view.clip_end_source)&&view.clip_start_source>0&&view.clip_end_source>view.clip_start_source,'source clipping planes required');
    if(view.projection==='PERSP')check(finite(view.lens_mm)&&view.lens_mm>0&&finite(view.sensor_width_mm)&&view.sensor_width_mm>0,'perspective camera projection required');
    else check(finite(view.ortho_scale_source)&&view.ortho_scale_source>0,'orthographic source span required');
  }
  for (const scope of scopes) {
    check(c.views.some(v => v.id === c.defaults?.[scope] && v.scope === scope), `default ${scope} camera missing`);
    const limit = c.distance_limits_source?.[scope]; check(Array.isArray(limit) && limit.length === 2 && limit.every(finite) && 0 < limit[0] && limit[0] < limit[1], 'camera distance limits required');
  }
  check(c.views.some(v=>v.id===c.archive_locator_view&&v.scope==='exterior'),'published exterior archive locator view required');
  const l = docs.lighting;
  check(l.source_coordinate_system === 'Blender_Z_up' && l.calibrated === false, 'new uncalibrated source lighting recipe required');
  check(finite(l.exposure_stops) && finite(l.environment_intensity) && l.environment_intensity >= 0, 'explicit exposure/environment required');
  check(Number.isInteger(l.shadow_budget?.standard_max_lights) && l.shadow_budget.standard_max_lights >= 0 && l.shadow_budget.light_enabled === false, 'explicit shadow budget required');
  check(Array.isArray(l.lights) && l.lights.length > 0, 'final source light recipe missing');
  const lightIds = new Set();
  for (const row of l.lights) {
    check(typeof row.id === 'string' && !lightIds.has(row.id), 'duplicate light'); lightIds.add(row.id);
    check(['directional','spot'].includes(row.type) && ['exterior','archive','all'].includes(row.scope), 'unsupported light type/scope');
    if(row.views!==undefined)check(Array.isArray(row.views)&&row.views.length>0&&new Set(row.views).size===row.views.length&&row.views.every(id=>c.views.some(view=>view.id===id&&(row.scope==='all'||view.scope===row.scope))),'light views must be unique published ids matching the light scope');
    check(Array.isArray(row.modes) && row.modes.length && row.modes.every(m => ['neutral','space'].includes(m)), 'light mode required');
    check(vector(row.position_source) && vector(row.target_source) && vector(row.color_linear) && row.color_linear.every(n=>n>=0&&n<=1), 'source light vectors/linear color required');
    check(row.position_source.some((n,i)=>n!==row.target_source[i]), 'light position equals target');
    check(finite(row.intensity_web) && row.intensity_web >= 0 && typeof row.group === 'string', 'declared preview intensity/group required');
    check(typeof row.shadow?.enabled === 'boolean', 'shadow intent required');
    if (row.shadow.enabled) {
      check([256,512,1024,2048].includes(row.shadow.map_size), 'unsupported shadow resolution');
      check(finite(row.shadow.near_source) && finite(row.shadow.far_source) && 0 < row.shadow.near_source && row.shadow.near_source < row.shadow.far_source, 'shadow range required');
      check(finite(row.shadow.bias) && finite(row.shadow.normal_bias_source), 'shadow biases required');
      if (row.type === 'directional') check(finite(row.shadow.span_source) && row.shadow.span_source > 0, 'directional shadow span required');
    }
    if (row.type === 'spot') check(finite(row.angle_radians) && row.angle_radians > 0 && row.angle_radians < Math.PI / 2 && finite(row.distance_source) && row.distance_source > 0 && finite(row.penumbra) && row.penumbra >= 0 && row.penumbra <= 1, 'spot cone/range required');
  }
  for(const view of c.views)for(const mode of ['space','neutral'])check(l.lights.filter(row=>row.shadow.enabled&&lightAppliesToView(row,{scope:view.scope,mode,view:view.id})).length<=l.shadow_budget.standard_max_lights,'shadow budget exceeded for view');
  check(Array.isArray(docs.references.frames), 'reference list required');
  const refs = new Set();
  for (const ref of docs.references.frames) {
    check(ref.kind === 'offline-render-reference' && ref.source_scene_sha256 === contract.source_scene.sha256, 'reference provenance differs');
    check(c.views.some(v => v.id === ref.view_id && v.scope === ref.scope) && ['neutral','space'].includes(ref.light), 'reference view mismatch');
    const key = `${ref.scope}/${ref.view_id}/${ref.light}`; check(!refs.has(key),'duplicate reference'); refs.add(key); validateDescriptor(ref.asset);
  }
  for(const view of c.views)for(const mode of ['neutral','space'])check(refs.has(`${view.scope}/${view.id}/${mode}`),'fallback reference missing for published view/light');
  return { ready: true, contract, ...docs };
}
export function parseGlbJson(buffer) {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  check(bytes.byteLength >= 20, 'truncated GLB'); const d = new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  check(d.getUint32(0,true) === 0x46546c67 && d.getUint32(4,true) === 2 && d.getUint32(8,true) === bytes.byteLength, 'invalid GLB header');
  const length = d.getUint32(12,true); check(d.getUint32(16,true) === 0x4e4f534a && 20 + length <= bytes.byteLength, 'invalid JSON chunk');
  const value = JSON.parse(new TextDecoder().decode(bytes.subarray(20,20+length)));
  const lightExtension='KHR_lights_punctual',hasLightExtension=extensions=>Object.prototype.hasOwnProperty.call(extensions||{},lightExtension);
  check(!hasLightExtension(value.extensions)&&!(value.extensionsUsed||[]).includes(lightExtension)&&!(value.extensionsRequired||[]).includes(lightExtension)&&
    !(value.nodes||[]).some(node=>hasLightExtension(node.extensions)), 'GLB punctual lights forbidden; use the reviewed lighting recipe');
  check(![...(value.buffers || []), ...(value.images || [])].some(row => row.uri && !row.uri.startsWith('data:')), 'external GLB dependencies forbidden');
  check(!value.cameras?.length && !value.animations?.length, 'unreleased camera/animation dependency');
  return value;
}
export function validateAssetSemantics(scope, json, semantics) {
  const assigned = semanticAssignments(semantics, scope); const actual = new Map();
  for (const [index,node] of (json.nodes || []).entries()) if (node.mesh !== undefined) {
    check(typeof node.name === 'string' && !actual.has(node.name), 'mesh node names must be exact and unique'); actual.set(node.name,index);
  }
  check(actual.size === assigned.size && [...actual.keys()].every(name => assigned.has(name)), `${scope} semantic coverage differs from GLB mesh nodes`);
  return assigned;
}
export async function loadContractBundle(url, signal, expected = {}) {
  // Production pins the top-level document as well as every transitive asset.
  let value;
  if (expected.contract) value = JSON.parse(new TextDecoder().decode(await verifiedBytes(url, expected.contract, signal)));
  else {
    const response = await fetch(url,{signal,cache:'no-cache'}); if (!response.ok) throw Error(`Contract HTTP ${response.status}`);
    value = await response.json();
  }
  const initial = validateAssetContract(value, { expectedSource: expected.source }); if (!initial.ready) return initial;
  const docs = {};
  for (const [name,descriptor] of Object.entries(initial.contract.documents)) {
    const bytes = await verifiedBytes(new URL(descriptor.uri,document.baseURI),descriptor,signal);
    docs[name] = JSON.parse(new TextDecoder().decode(bytes));
  }
  return validateRuntimeDocuments(initial.contract,docs);
}
