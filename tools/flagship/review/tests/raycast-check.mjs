// Node-only geometry checks. Supply the uncompressed GLBs produced by
// inspect_review.py --decoded <directory>. This does not start a browser.
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import path from 'node:path';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const dir = process.argv[2];
if (!dir) throw Error('Pass the decoded GLB directory');
const buffer = await readFile(path.join(dir, 'flagship.glb'));
const ship = (await new GLTFLoader().parseAsync(buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength), '')).scene;
ship.updateMatrixWorld(true);
const hull = [], shell = [];
ship.traverse(o => { if (o.isMesh) (o.userData.role === 'archive_shell' ? shell : hull).push(o); });
assert.equal(shell.length, 5); assert.equal(hull.length, 9);
const radius = new THREE.Box3().setFromObject(ship).getBoundingSphere(new THREE.Sphere()).radius;
const anchor = new THREE.Vector3(-.8, .30, .48);
const results = [];
for (const [width, height] of [[1440,900],[390,844]]) {
  const camera = new THREE.PerspectiveCamera(38, width / height, .015, 400);
  const angle = Math.min(THREE.MathUtils.degToRad(19), Math.atan(Math.tan(THREE.MathUtils.degToRad(19)) * width / height));
  camera.position.copy(new THREE.Vector3(0,.08,0)).addScaledVector(new THREE.Vector3(-5.5,3.82,6).normalize(), radius / Math.sin(angle) * 1.1);
  camera.lookAt(0,.08,0); camera.updateMatrixWorld(true);
  const projected = anchor.clone().project(camera);
  const x = (projected.x + 1) * width / 2, y = (1 - projected.y) * height / 2;
  assert.ok(x > 25 && x < width - 25 && y > 115 && y < height - 150);
  const ray = new THREE.Raycaster(camera.position, anchor.clone().sub(camera.position).normalize());
  const obstacle = ray.intersectObjects(hull, false)[0];
  assert.ok(!obstacle || obstacle.distance >= camera.position.distanceTo(anchor) - .035, 'Default beacon occluded');
  let visibleSurface = null;
  for (const mesh of shell) {
    const position = mesh.geometry.attributes.position, index = mesh.geometry.index;
    for (let i=0;i<(index?.count || position.count);i+=3) {
      const centroid = new THREE.Vector3();
      for (let j=0;j<3;j++) centroid.add(new THREE.Vector3().fromBufferAttribute(position,index ? index.getX(i+j) : i+j));
      centroid.multiplyScalar(1/3).applyMatrix4(mesh.matrixWorld);
      ray.set(camera.position, centroid.clone().sub(camera.position).normalize());
      const first = ray.intersectObjects([...hull,...shell],false)[0];
      if(first && shell.includes(first.object)){ visibleSurface=centroid; break; }
    }
    if (visibleSurface) break;
  }
  assert.ok(visibleSurface,'No actual archive surface visible from overview');
  const matrices = shell.map(m=>m.matrixWorld.elements.slice());
  shell.forEach(m=>m.visible=false);
  ray.set(camera.position,visibleSurface.clone().sub(camera.position).normalize());
  assert.ok(shell.includes(ray.intersectObjects([...hull,...shell],false)[0].object), 'Cutaway must remain pickable');
  assert.deepEqual(shell.map(m=>m.matrixWorld.elements),matrices,'Hover visibility moved geometry');
  shell.forEach(m=>m.visible=true);
  // Opposite flank must block the room, rather than selecting through the ship.
  const behind = new THREE.Vector3(-.8,.2,-4);
  ray.set(behind,anchor.clone().sub(behind).normalize());
  assert.ok(hull.includes(ray.intersectObjects([...hull,...shell],false)[0]?.object));
  results.push({width,height,beacon:[+x.toFixed(2),+y.toFixed(2)],visible:true,occlusion:true});
}
console.log(JSON.stringify({geometry_checks:results,browser_tested:false},null,2));
