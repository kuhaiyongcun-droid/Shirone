import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { applyContractCamera, captureView, restoreView } from '../src/contract-camera.mjs';
import { docs } from './fixtures/release-source.mjs';
// Real locally installed Three/OrbitControls math only; no renderer or browser.
const cameras=docs.cameras;
const state = (camera, controls) => {
  camera.updateMatrixWorld(true);
  return {camera:captureView(camera,controls),world:camera.matrixWorld.toArray(),view:camera.matrixWorldInverse.toArray(),projection:camera.projectionMatrix.toArray()};
};
test('real controls preserve the captured exterior pose exactly through repeated archive roundtrips',()=>{
  for (const id of ['whole-ship','archive-locator']) for (const adjusted of [false,true]) {
    let camera = new THREE.PerspectiveCamera(), controls = new OrbitControls(camera);
    controls.enableDamping=false; controls.enablePan=false; controls.minPolarAngle=.06; controls.maxPolarAngle=Math.PI-.06;
    camera=applyContractCamera(camera,controls,id,cameras,8/5);
    // Preserve an actual user-adjusted pose, not only a published camera preset.
    if(adjusted){controls.rotateLeft(.113); controls.rotateUp(.047);}
    const before=state(camera,controls), saved=captureView(camera,controls);
    for(let round=0;round<20;round++){
      camera=applyContractCamera(camera,controls,'archive-cutaway',cameras,8/5);
      camera=restoreView(camera,controls,saved,8/5);
      assert.deepEqual(state(camera,controls),before,`${id} adjusted=${adjusted} round ${round+1}`);
    }
  }
});
