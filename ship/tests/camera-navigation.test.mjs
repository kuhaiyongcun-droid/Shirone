import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { applyContractCamera,captureView,restoreView } from '../src/contract-camera.mjs';
import { moveCameraByKey,installTouchDollyGuard } from '../src/camera-navigation.mjs';
import { docs } from './fixtures/release-source.mjs';
const cameras=docs.cameras;
function make(id,matched=false){const controls=new OrbitControls(new THREE.PerspectiveCamera());return {controls,camera:applyContractCamera(controls.object,controls,id,cameras,1.6,{matched})};}
function within(camera,controls){const sphere=new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
  for(const [v,min,max]of [[sphere.theta,controls.minAzimuthAngle,controls.maxAzimuthAngle],[sphere.phi,controls.minPolarAngle,controls.maxPolarAngle],[sphere.radius,controls.minDistance,controls.maxDistance]])assert.ok(v>=min-1e-8&&v<=max+1e-8,`${v} outside ${min}..${max}`);
}
test('all four interior cameras clamp repeated keyboard and actual OrbitControls changes to the same window',()=>{
  for(const id of ['archive-cutaway','archive-entry','archive-upper','vestibule']){
    const {camera,controls}=make(id);assert.equal(camera.userData.navigation.profile,'interior-recommended-window-v1');
    for(const key of ['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','-'])for(let i=0;i<30;i++){assert.equal(moveCameraByKey(camera,controls,key),true);within(camera,controls);}
    for(const angle of [10,-10]){controls.rotateLeft(angle);controls.rotateUp(angle);controls.dollyIn(100);controls.update();within(camera,controls);controls.dollyOut(100);controls.update();within(camera,controls);}
  }
});
test('archive-upper ArrowLeft six times stops at 1.5 degrees instead of reaching a wall-facing 0.6 radians',()=>{
  const {camera,controls}=make('archive-upper'),before=new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
  for(let i=0;i<6;i++)moveCameraByKey(camera,controls,'ArrowLeft');
  const after=new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
  assert.ok(Math.abs(after.theta-before.theta-1.5*Math.PI/180)<1e-8);within(camera,controls);
});
test('recommended reset restores current interior camera exactly and does not modify source recipe',()=>{
  const original=JSON.stringify(cameras);
  for(const id of ['archive-cutaway','archive-entry','archive-upper','vestibule']){
    const {controls,camera}=make(id),before=captureView(camera,controls);moveCameraByKey(camera,controls,'ArrowLeft');moveCameraByKey(camera,controls,'+');
    const reset=applyContractCamera(camera,controls,id,cameras,1.6);assert.deepEqual(captureView(reset,controls),before);
  }
  assert.equal(JSON.stringify(cameras),original);
});
test('quality restoration retains interior limits and return to exterior removes them without changing saved pose',()=>{
  let {camera,controls}=make('whole-ship');controls.rotateLeft(.1);const exterior=captureView(camera,controls);
  camera=applyContractCamera(camera,controls,'archive-upper',cameras,1.6);moveCameraByKey(camera,controls,'ArrowLeft');const inside=captureView(camera,controls);
  const rebuilt=new OrbitControls(new THREE.PerspectiveCamera());let restored=restoreView(rebuilt.object,rebuilt,inside,1.6);assert.deepEqual(captureView(restored,rebuilt),inside);within(restored,rebuilt);
  restored=restoreView(restored,rebuilt,exterior,1.6);assert.deepEqual(captureView(restored,rebuilt),exterior);assert.equal(rebuilt.minAzimuthAngle,-Infinity);assert.equal(rebuilt.maxAzimuthAngle,Infinity);
});
test('matched reference keyboard controls leave exact pose and projection unchanged',()=>{
  for(const id of ['whole-ship','archive-upper']){
    const {camera,controls}=make(id,true),before=captureView(camera,controls);assert.equal(controls.enableRotate,false);assert.equal(controls.enableZoom,false);
    for(const key of ['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','-'])moveCameraByKey(camera,controls,key);
    assert.deepEqual(captureView(camera,controls),before);
  }
});
test('zero-distance pinch never poisons the real touch handler and ordinary pinches continue afterwards',()=>{
  for(const id of ['archive-cutaway','archive-entry','archive-upper','vestibule']){
    const {camera,controls}=make(id);controls.enablePan=false;installTouchDollyGuard(controls);
    const target=controls.target.toArray();controls._pointers=[1,2];controls._pointerPositions[2]=new THREE.Vector2(200,200);
    controls._handleTouchStartDollyPan({pointerId:1,pageX:200,pageY:200});
    for(const x of [200,200,100,50,200,200,100,150]){
      controls._handleTouchMoveDollyPan({pointerId:1,pageX:x,pageY:200});controls.update();
      assert.ok(camera.position.toArray().every(Number.isFinite),id+' finite position');assert.ok(camera.quaternion.toArray().every(Number.isFinite),id+' finite quaternion');
      assert.ok(controls.target.distanceTo(new THREE.Vector3().fromArray(target))<1e-12,'no touch panning beyond floating-point roundoff');within(camera,controls);
    }
    assert.ok(Math.abs(camera.position.distanceTo(controls.target)-controls.maxDistance)<1e-8,'ordinary pinch zoom still reaches its bound');
  }
});
test('touch dolly guard has idempotent installation/removal and diagnoses an incompatible Three API',()=>{
  assert.throws(()=>installTouchDollyGuard({}),/expected pinned OrbitControls/);
  const {controls}=make('archive-upper'),original=controls._handleTouchMoveDolly,remove=installTouchDollyGuard(controls),wrapped=controls._handleTouchMoveDolly;
  assert.notEqual(wrapped,original);assert.equal(installTouchDollyGuard(controls),remove);assert.equal(controls._handleTouchMoveDolly,wrapped);
  remove();remove();assert.equal(controls._handleTouchMoveDolly,original);
  const again=installTouchDollyGuard(controls);assert.notEqual(controls._handleTouchMoveDolly,original);again();assert.equal(controls._handleTouchMoveDolly,original);
});
