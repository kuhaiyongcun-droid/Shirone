import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { validateAssetContract,validateRuntimeDocuments,validateAssetSemantics,parseGlbJson,localAssetUri,sourcePointToWeb,sourceDirectionToWeb,sourceMatrixToWeb } from '../src/asset-contract.mjs';
import { inspectContractFiles } from '../verify-assets.mjs';
import { PIN,selected } from './fixtures/release-source.mjs';
import { projectionForView,orthographicBounds,frameSize } from '../src/projection.mjs';
import { snapshotCompatible,assertImportedSceneHasNoLights,visibilityForView,lightAppliesToView } from '../src/runtime-guards.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const sha=text=>createHash('sha256').update(text).digest('hex');
// Synthetic fixtures are confined to tests; no final-model identity is invented.
const descriptor=name=>({uri:`./assets/${name}.json`,sha256:sha('synthetic:'+name),bytes:1});
function fixture(){
  const contract={schema_version:1,revision:'synthetic-test',status:'ready-for-review',source_scene:{stage:'P25',sha256:sha('synthetic-source')},coordinate_system:{gltf_up_axis:'Y',source_length_unit:'meter',root_scale:.01,model_rotation:[0,0,0]},verification:{browser_verified:false,lighting_calibrated:false},assets:{exterior:descriptor('exterior'),archive:descriptor('archive')},documents:Object.fromEntries(['semantics','cameras','lighting','references'].map(name=>[name,descriptor(name)]))};
  const base={schema_version:1,source_scene_sha256:contract.source_scene.sha256};
  const camera=(id,scope)=>({id,scope,label:{zh_CN:id,en:id},target_source:[0,0,0],matrix_world:[[1,0,0,0],[0,1,0,0],[0,0,1,100],[0,0,0,1]],projection:'PERSP',sensor_fit:'HORIZONTAL',lens_mm:50,sensor_width_mm:36,shift_x:0,shift_y:0,clip_start_source:.1,clip_end_source:10000,hidden_shell_nodes:[]});
  const docs={semantics:{...base,assets:{exterior:{hull:['Hull exact.name'],archive_shell:['Archive shell'],reserved:[]},archive:{archive_interior:['Room exact.name'],reserved:[]}}},
    cameras:{...base,source_coordinate_system:'Blender_Z_up',archive_anchor_source:[0,0,0],archive_locator_view:'wide',reference_resolution:[1600,1000],views:[camera('wide','exterior'),camera('room','archive')],defaults:{exterior:'wide',archive:'room'},distance_limits_source:{exterior:[1,1000],archive:[.1,50]}},
    lighting:{...base,source_coordinate_system:'Blender_Z_up',calibrated:false,exposure_stops:0,environment_intensity:.3,shadow_budget:{standard_max_lights:1,light_enabled:false},lights:[{id:'key',type:'directional',scope:'all',modes:['neutral','space'],position_source:[0,0,100],target_source:[0,0,0],color_linear:[1,1,1],intensity_web:1,group:'key',shadow:{enabled:true,map_size:512,near_source:1,far_source:200,span_source:100,bias:0,normal_bias_source:.01}}]},
    references:{...base,frames:['wide','room'].flatMap(view_id=>['neutral','space'].map(light=>({kind:'offline-render-reference',source_scene_sha256:contract.source_scene.sha256,view_id,scope:view_id==='wide'?'exterior':'archive',light,asset:descriptor(`reference-${view_id}-${light}`)})))}};
  return {contract,docs};
}
function glb(json){const text=Buffer.from(JSON.stringify(json)),length=Math.ceil(text.length/4)*4,b=Buffer.alloc(20+length,32);b.writeUInt32LE(0x46546c67,0);b.writeUInt32LE(2,4);b.writeUInt32LE(b.length,8);b.writeUInt32LE(length,12);b.writeUInt32LE(0x4e4f534a,16);text.copy(b,20);return b;}
test('pending contract explicitly has no model substitute or claimed acceptance',async()=>{
  const current=JSON.parse(await readFile(path.join(root,'tests/fixtures/p23-pending-contract.json'),'utf8'));assert.equal(validateAssetContract(current).ready,false);
  for(const changed of [{...current,source_scene:{stage:'P25',sha256:sha('fake')}},{...current,verification:{browser_verified:true,lighting_calibrated:false}}])assert.throws(()=>validateAssetContract(changed));
});
test('local URIs reject remote access, traversal and ambiguous paths',()=>{assert.equal(localAssetUri('./assets/p22/exterior.glb'),'./assets/p22/exterior.glb');for(const uri of ['https://example.test/a','../assets/a','./assets/../a','./assets//a','./assets/%2e%2e/a','./assets/a?token=x'])assert.throws(()=>localAssetUri(uri));});
test('ready contract requires two distinct assets and exactly bound document kinds',()=>{const {contract}=fixture();assert.equal(validateAssetContract(contract).ready,true);contract.assets.archive=contract.assets.exterior;assert.throws(()=>validateAssetContract(contract),/distinct/);});
test('coordinate contract rejects double rotation and unexpected scaling',()=>{for(const patch of [{root_scale:1},{source_length_unit:'centimeter'},{model_rotation:[-90,0,0]}]){const {contract}=fixture();Object.assign(contract.coordinate_system,patch);assert.throws(()=>validateAssetContract(contract));}});
test('source coordinates and camera matrix apply one metric scale and one axis conversion',()=>{assert.deepEqual(sourcePointToWeb([100,200,300]),[1,3,-2]);assert.deepEqual(sourceDirectionToWeb([1,2,3]),[1,3,-2]);const m=sourceMatrixToWeb([[1,0,0,100],[0,1,0,200],[0,0,1,300],[0,0,0,1]]);assert.deepEqual(m.map(row=>row[3]),[1,3,-2,1]);assert.deepEqual(m.slice(0,3).map(row=>row.slice(0,3)),[[1,0,0],[0,0,1],[-0,-1,-0]]);});
test('runtime documents bind source scene and require a valid camera per scope',()=>{const {contract,docs}=fixture();assert.equal(validateRuntimeDocuments(contract,docs).ready,true);docs.cameras.source_scene_sha256=sha('other');assert.throws(()=>validateRuntimeDocuments(contract,docs),/source binding/);docs.cameras.source_scene_sha256=contract.source_scene.sha256;docs.cameras.defaults.archive='wide';assert.throws(()=>validateRuntimeDocuments(contract,docs),/default archive/);});
test('camera transforms reject embedded scale',()=>{const {contract,docs}=fixture();docs.cameras.views[0].matrix_world[0][0]=.01;assert.throws(()=>validateRuntimeDocuments(contract,docs),/rigid/);});
test('formal orthographic views require their source span, never a perspective substitute',()=>{const {contract,docs}=fixture();const view=docs.cameras.views[0];view.projection='ORTHO';delete view.lens_mm;delete view.sensor_width_mm;assert.throws(()=>validateRuntimeDocuments(contract,docs),/orthographic/);view.ortho_scale_source=585;validateRuntimeDocuments(contract,docs);delete view.projection;assert.throws(()=>validateRuntimeDocuments(contract,docs),/explicit projection/);});
test('8:5 orthographic projection matches 585 source meters and keeps height on resize',()=>{const p=projectionForView({projection:'ORTHO',ortho_scale_source:585},8/5);assert.ok(Math.abs(p.right-p.left-5.85)<1e-12);assert.ok(Math.abs(p.top-p.bottom-3.65625)<1e-12);assert.deepEqual(orthographicBounds(p.height,8/5),{left:p.left,right:p.right,top:p.top,bottom:p.bottom});const portrait=projectionForView({projection:'ORTHO',ortho_scale_source:585},8/5,390/844);assert.equal(portrait.height,p.height);assert.ok(Math.abs((portrait.right-portrait.left)/(portrait.top-portrait.bottom)-390/844)<1e-12);});
test('matched frames retain 8:5 and perspective projection uses the published lens',()=>{for(const [w,h]of [[1440,900],[390,844]]){const f=frameSize(w,h,true,8/5);assert.ok(Math.abs(f.width/f.height-1.6)<1e-12);assert.ok(f.width<=w&&f.height<=h);}const p=projectionForView({projection:'PERSP',lens_mm:50,sensor_width_mm:36},8/5);assert.ok(Math.abs(p.fov-25.36076698363964)<1e-10);});
test('exact semantic lists reject duplicate interior and role ambiguity',()=>{const {contract,docs}=fixture();docs.semantics.assets.archive.archive_interior.push('Hull exact.name');assert.throws(()=>validateRuntimeDocuments(contract,docs),/overlap/);docs.semantics.assets.archive.archive_interior.pop();docs.semantics.assets.exterior.reserved.push('Hull exact.name');assert.throws(()=>validateRuntimeDocuments(contract,docs),/duplicate/);});
test('GLB semantic coverage rejects unlisted, missing or duplicate mesh nodes',()=>{const {docs}=fixture();const good={nodes:[{name:'Hull exact.name',mesh:0},{name:'Archive shell',mesh:1},{name:'Unmeshed parent'}]};assert.equal(validateAssetSemantics('exterior',good,docs.semantics).size,2);for(const nodes of [good.nodes.slice(1),[...good.nodes,{name:'Unknown',mesh:2}],[...good.nodes,{name:'Hull exact.name',mesh:3}]])assert.throws(()=>validateAssetSemantics('exterior',{nodes},docs.semantics));});
test('GLB cannot resolve an external URL or import undeclared cameras',()=>{assert.equal(parseGlbJson(glb({asset:{version:'2.0'},nodes:[]})).asset.version,'2.0');for(const json of [{buffers:[{uri:'https://example.test/secret'}]},{images:[{uri:'../image.png'}]},{cameras:[{}]},{animations:[{}]}])assert.throws(()=>parseGlbJson(glb(json)));const broken=glb({nodes:[]});broken.writeUInt32LE(2,8);assert.throws(()=>parseGlbJson(broken),/header/);});
test('GLB punctual-light definitions, declarations and node attachments are rejected before parsing',()=>{
  const cases=[{extensions:{KHR_lights_punctual:{lights:[{type:'point'}]}}},{extensions:{KHR_lights_punctual:null}},
    {extensionsUsed:['KHR_lights_punctual']},{extensionsRequired:['KHR_lights_punctual']},
    {nodes:[{extensions:{KHR_lights_punctual:{light:0}}}]},{nodes:[{extensions:{KHR_lights_punctual:null}}]}];
  for(const json of cases)assert.throws(()=>parseGlbJson(glb(json)),/punctual lights forbidden/);
  assert.doesNotThrow(()=>parseGlbJson(glb({extensionsUsed:['KHR_materials_emissive_strength'],nodes:[{name:'emissive surface',mesh:0}]})));
});
test('parsed imported object tree independently rejects lights before scene attachment',()=>{
  const tree=objects=>({traverse(visitor){for(const object of objects)visitor(object);}});
  assert.doesNotThrow(()=>assertImportedSceneHasNoLights(tree([{isGroup:true},{isMesh:true}])));
  assert.throws(()=>assertImportedSceneHasNoLights(tree([{isGroup:true},{isLight:true,type:'PointLight'},{isMesh:true}])),/imported GLB light forbidden/);
});
test('quality rebuild restores only the current room and matching source identities',()=>{
  const {contract,docs}=fixture(),snapshot={revision:contract.revision,sourceSceneSha256:contract.source_scene.sha256,modelSha256:contract.assets.exterior.sha256,
    archiveSha256:contract.assets.archive.sha256,cameraRecipeSha256:contract.documents.cameras.sha256,mode:'ship',view:'wide',camera:{projection:'PERSP'},savedView:null};
  assert.equal(snapshotCompatible(snapshot,'ship',contract,docs.cameras),true);
  assert.equal(snapshotCompatible(snapshot,'archive',contract,docs.cameras),false);
  const room={...snapshot,mode:'archive',view:'room',savedExteriorView:'wide',savedView:{projection:'PERSP'}};
  assert.equal(snapshotCompatible(room,'archive',contract,docs.cameras),true);assert.equal(snapshotCompatible(room,'ship',contract,docs.cameras),false);
  for(const key of ['revision','sourceSceneSha256','modelSha256','archiveSha256','cameraRecipeSha256'])assert.equal(snapshotCompatible({...snapshot,[key]:'different'},'ship',contract,docs.cameras),false);
  for(const changed of [{...snapshot,view:'room'},{...snapshot,camera:{projection:'ORTHO'}},{...room,savedExteriorView:'removed-view'}])assert.equal(snapshotCompatible(changed,changed.mode,contract,docs.cameras),false);
  assert.equal(snapshotCompatible(null,'ship',contract,docs.cameras),false);
});
test('per-view cutaway lists reject hull, reserved, unknown, duplicate and exterior hiding',()=>{
  const {contract,docs}=fixture();docs.semantics.assets.archive.reserved=['Reserved interface'];const room=docs.cameras.views[1];
  for(const names of [['Hull exact.name'],['Reserved interface'],['unknown'],['Archive shell','Archive shell']]){room.hidden_shell_nodes=names;assert.throws(()=>validateRuntimeDocuments(contract,docs),/archive_shell/);}
  room.hidden_shell_nodes=['Archive shell'];validateRuntimeDocuments(contract,docs);room.hidden_shell_nodes=[];
  docs.cameras.views[0].hidden_shell_nodes=['Archive shell'];assert.throws(()=>validateRuntimeDocuments(contract,docs),/exterior reference/);
});
test('archive reference views retain exterior and shell; only an explicit cutaway hides shell',()=>{
  const {docs}=fixture(),state={mode:'archive',viewId:'room',previewOpen:true,interiorReady:true};
  const normal=visibilityForView(state,docs.cameras,docs.semantics);assert.equal(normal.exteriorVisible,true);assert.equal(normal.interiorVisible,true);assert.equal(normal.outlineVisible,false);assert.deepEqual(normal.hiddenShellNodes,[]);
  const cutaway={...docs.cameras.views[1],id:'cutaway',hidden_shell_nodes:['Archive shell']};docs.cameras.views.push(cutaway);
  const cut=visibilityForView({...state,viewId:'cutaway'},docs.cameras,docs.semantics);assert.deepEqual(cut.hiddenShellNodes,['Archive shell']);assert.equal(cut.exteriorVisible,true);
  assert.deepEqual(visibilityForView(state,docs.cameras,docs.semantics),normal);
});
test('ship preview temporarily hides all shell then restores the published exterior visibility',()=>{
  const {docs}=fixture(),state={mode:'ship',viewId:'wide',previewOpen:true,interiorReady:true};
  const hover=visibilityForView(state,docs.cameras,docs.semantics);assert.deepEqual(hover.hiddenShellNodes,['Archive shell']);assert.equal(hover.interiorVisible,true);assert.equal(hover.outlineVisible,true);
  const ended=visibilityForView({...state,previewOpen:false},docs.cameras,docs.semantics);assert.deepEqual(ended.hiddenShellNodes,[]);assert.equal(ended.interiorVisible,false);assert.equal(ended.exteriorVisible,true);
  const pending=visibilityForView({...state,interiorReady:false},docs.cameras,docs.semantics);assert.deepEqual(pending.hiddenShellNodes,[]);assert.equal(pending.interiorVisible,false);
});
test('lighting fails closed on shadow budget, unsupported area lights or acceptance claims',()=>{for(const edit of [l=>l.shadow_budget.standard_max_lights=0,l=>l.lights[0].type='area',l=>l.calibrated=true,l=>l.shadow_budget.light_enabled=true]){const {contract,docs}=fixture();edit(docs.lighting);assert.throws(()=>validateRuntimeDocuments(contract,docs));}});
test('optional light views select exact cameras while absent views retain scope-wide applicability',()=>{
  const light={scope:'exterior',modes:['neutral']},state={scope:'exterior',mode:'neutral',view:'wide'};
  assert.equal(lightAppliesToView(light,state),true);assert.equal(lightAppliesToView(light,{...state,view:'underside'}),true);
  const selected={...light,views:['wide','locator']};assert.equal(lightAppliesToView(selected,state),true);assert.equal(lightAppliesToView(selected,{...state,view:'underside'}),false);
  assert.equal(lightAppliesToView(selected,{...state,scope:'archive'}),false);assert.equal(lightAppliesToView(selected,{...state,mode:'space'}),false);
});
test('light view lists reject unknown, duplicate, empty or cross-scope ids',()=>{
  for(const views of [['unknown'],['wide','wide'],[],['room']]){const {contract,docs}=fixture();Object.assign(docs.lighting.lights[0],{scope:'exterior',views});assert.throws(()=>validateRuntimeDocuments(contract,docs),/light views/);}
});
test('shadow budget is enforced for each scope, mode and view rather than all view alternatives together',()=>{
  const {contract,docs}=fixture();docs.cameras.views.push({...docs.cameras.views[0],id:'underside'});
  for(const mode of ['neutral','space'])docs.references.frames.push({kind:'offline-render-reference',source_scene_sha256:contract.source_scene.sha256,view_id:'underside',scope:'exterior',light:mode,asset:descriptor(`reference-underside-${mode}`)});
  Object.assign(docs.lighting.lights[0],{scope:'exterior',views:['wide']});docs.lighting.lights.push({...docs.lighting.lights[0],id:'underside-key',views:['underside']});
  validateRuntimeDocuments(contract,docs);delete docs.lighting.lights[1].views;assert.throws(()=>validateRuntimeDocuments(contract,docs),/shadow budget exceeded for view/);
});
test('fallback references require complete views, same source and exact file identity',()=>{const {contract,docs}=fixture();validateRuntimeDocuments(contract,docs);docs.references.frames[2].view_id='wide';assert.throws(()=>validateRuntimeDocuments(contract,docs),/reference view/);docs.references.frames[2].view_id='room';docs.references.frames.pop();assert.throws(()=>validateRuntimeDocuments(contract,docs),/fallback reference missing/);});
test('all ten locale registries contain the new pending-state key',async()=>{const base=path.join(root,'i18n');assert.match(await readFile(path.join(base,'i18nKey.ts'),'utf8'),/flagshipReviewAwaitingAssets/);for(const lang of ['en','zh_CN','zh_TW','es','id','ja','ko','th','tr','vi'])assert.match(await readFile(path.join(base,`languages/${lang}.ts`),'utf8'),/\[Key\.flagshipReviewAwaitingAssets\]:\s*"[^"]+"/);});
test('final P26-P27 asset bytes, full semantic coverage and production view/PNG compatibility',async()=>{const actual=await inspectContractFiles(selected.publicRoot,{expectedSource:PIN.source,expectedContract:PIN.contract,requireViewerCompatibility:true});assert.equal(actual.ready,true);assert.ok(actual.mesh_node_counts.exterior>0&&actual.mesh_node_counts.archive>0);assert.equal(actual.compatibility.referenceFrames,14);});

// Stage-specific rejection prevents silently loading the frozen P22/P24 package.
test('P25 viewer rejects older model stages',()=>{for(const stage of ['P22','P24']){const {contract}=fixture();contract.source_scene.stage=stage;assert.throws(()=>validateAssetContract(contract),/P25 final source/);}});
