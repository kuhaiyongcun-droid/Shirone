import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { applyContractCamera,captureView,restoreView,resizeContractCamera,presentationPoints } from '../src/contract-camera.mjs';
import { frameSize,presentationHeight } from '../src/projection.mjs';
import { parseGlbJson } from '../src/asset-contract.mjs';
import { docs,contract,readAsset } from './fixtures/release-source.mjs';

// Reconstruct the pinned GLB's actual node transforms and POSITION bounds.
// This tests framing against all exterior mesh envelopes without a renderer,
// texture load, synthetic stand-in hull or Draco/third-party download.
const glb=parseGlbJson(await readAsset(contract.assets.exterior));
const nodes=glb.nodes.map(row=>{
  const object=new THREE.Group();
  if(row.matrix){object.matrix.fromArray(row.matrix);object.matrix.decompose(object.position,object.quaternion,object.scale);}
  else{if(row.translation)object.position.fromArray(row.translation);if(row.rotation)object.quaternion.fromArray(row.rotation);if(row.scale)object.scale.fromArray(row.scale);}
  if(row.mesh!==undefined)for(const primitive of glb.meshes[row.mesh].primitives){
    const accessor=glb.accessors[primitive.attributes.POSITION],geometry=new THREE.BufferGeometry();
    assert.ok(accessor.min&&accessor.max,'real GLB position envelope required');
    geometry.boundingBox=new THREE.Box3(new THREE.Vector3().fromArray(accessor.min),new THREE.Vector3().fromArray(accessor.max));
    object.add(new THREE.Mesh(geometry));
  }
  return object;
});
for(let i=0;i<glb.nodes.length;i++)for(const child of glb.nodes[i].children||[])nodes[i].add(nodes[child]);
const exterior=new THREE.Group();for(const index of glb.scenes[glb.scene||0].nodes)exterior.add(nodes[index]);exterior.scale.setScalar(contract.coordinate_system.root_scale);
const points=presentationPoints(exterior),cameras=docs.cameras;
function projected(camera){camera.updateMatrixWorld(true);const b=new THREE.Box3();for(const p of points)b.expandByPoint(new THREE.Vector3().fromArray(p).project(camera));return b;}
function state(camera,controls){camera.updateMatrixWorld(true);return {camera:captureView(camera,controls),world:camera.matrixWorld.toArray(),projection:camera.projectionMatrix.toArray()};}

test('reference frames ignore all page insets and retain the original 8:5 rectangle',()=>{
  for(const [w,h]of [[390,844],[844,390],[1440,900]])assert.deepEqual(frameSize(w,h,true,1.6,{top:132,bottom:240}),frameSize(w,h,true,1.6));
  assert.deepEqual(frameSize(390,844,false,1.6,{top:130,bottom:230}),{width:390,height:484,x:0,y:130});
  const tiny=frameSize(100,100,false,1.6,{top:400,bottom:400,left:400,right:400});assert.equal(tiny.width,1);assert.equal(tiny.height,1);
  assert.throws(()=>presentationHeight({width:1,height:1},0),/Positive/);
});
test('mobile whole-ship framing keeps every pinned exterior mesh envelope visible and uses more phone height',t=>{
  assert.ok(points.length>1000,'full exterior must be used');
  for(const id of ['whole-ship','whole-underside']){
    const controls=new OrbitControls(new THREE.PerspectiveCamera());let camera=applyContractCamera(controls.object,controls,id,cameras,1.6);
    const reference=projected(camera),oldHeight=(reference.max.y-reference.min.y)/2*390/1.6;
    camera=applyContractCamera(camera,controls,id,cameras,390/484,{portrait:true,points});
    const mobile=projected(camera),height=(mobile.max.y-mobile.min.y)/2*484;
    t.diagnostic(`${id}: conservative mesh envelope ${oldHeight.toFixed(1)}px → ${height.toFixed(1)}px tall in a 390×484 presentation frame; ${(height/oldHeight).toFixed(2)}× height`);
    assert.equal(camera.userData.presentation.kind,'portrait-whole-ship');
    assert.ok(height>oldHeight*1.5,`${id}: ${height} vs ${oldHeight}`);
    for(const axis of ['x','y']){assert.ok(mobile.min[axis]>=-1/1.08-1e-8);assert.ok(mobile.max[axis]<=1/1.08+1e-8);}
    assert.ok(mobile.min.z>=-1&&mobile.max.z<=1);
  }
});
test('presentation resize preserves pose across phone rotation and continues containing the complete envelope',()=>{
  const controls=new OrbitControls(new THREE.PerspectiveCamera());let camera=applyContractCamera(controls.object,controls,'whole-ship',cameras,390/484,{portrait:true,points});
  const before=camera.matrixWorld.toArray();
  for(const aspect of [320/350,390/484,844/180,1.6,390/484]){
    resizeContractCamera(camera,aspect);camera.updateMatrixWorld(true);assert.deepEqual(camera.matrixWorld.toArray(),before);
    const b=projected(camera);for(const axis of ['x','y'])assert.ok(b.min[axis]>=-1/1.08-1e-8&&b.max[axis]<=1/1.08+1e-8);
  }
});
test('enter/back and quality-style reconstruction restore portrait framing and user adjustment exactly',()=>{
  for(const adjusted of [false,true]){
    const controls=new OrbitControls(new THREE.PerspectiveCamera());let camera=applyContractCamera(controls.object,controls,'whole-ship',cameras,390/484,{portrait:true,points});
    if(adjusted){controls.rotateLeft(.113);controls.rotateUp(.047);camera.zoom=1.11;camera.updateProjectionMatrix();}
    const saved=captureView(camera,controls),before=state(camera,controls);
    for(let round=0;round<20;round++){
      camera=applyContractCamera(camera,controls,'archive-cutaway',cameras,390/484,{portrait:true,points});
      assert.equal(camera.userData.presentation,undefined,'interior never inherits whole-ship framing');
      camera=restoreView(camera,controls,saved,390/484);assert.deepEqual(state(camera,controls),before);
    }
    const rebuilt=new OrbitControls(new THREE.PerspectiveCamera());const restored=restoreView(rebuilt.object,rebuilt,saved,390/484);assert.deepEqual(state(restored,rebuilt),before);
  }
});
test('returning to matched reference discards presentation and reproduces the exact source-view matrices',()=>{
  const controls=new OrbitControls(new THREE.PerspectiveCamera());let camera=applyContractCamera(controls.object,controls,'whole-ship',cameras,1.6),before=state(camera,controls);
  camera=applyContractCamera(camera,controls,'whole-ship',cameras,390/484,{portrait:true,points});
  camera=applyContractCamera(camera,controls,'whole-ship',cameras,1.6);assert.deepEqual(state(camera,controls),before);
});
