import * as THREE from 'three';
import { sourcePointToWeb,sourceMatrixToWeb } from './asset-contract.mjs';
import { projectionForView,orthographicBounds,presentationHeight } from './projection.mjs';
import { clearNavigationWindow,applyNavigationWindow,restoreNavigationWindow } from './camera-navigation.mjs';
export { frameSize } from './projection.mjs';
function cameraType(current,controls,projection) {
  const orthographic=projection==='ORTHO';
  if(orthographic===!!current.isOrthographicCamera)return current;
  const next=orthographic?new THREE.OrthographicCamera(-1,1,1,-1,current.near,current.far):new THREE.PerspectiveCamera(38,current.aspect||1,current.near,current.far);
  controls.object=next;return next;
}
export function resizeContractCamera(camera,aspect) {
  camera.aspect=aspect;
  const fit=Math.max(1,(camera.userData.referenceAspect||1.6)/aspect);
  if(camera.isOrthographicCamera)Object.assign(camera,orthographicBounds(camera.userData.presentation?presentationHeight(camera.userData.presentation.bounds,aspect):camera.userData.referenceHeight*fit,aspect));
  else if(camera.userData.referenceFov)camera.fov=2*Math.atan(Math.tan(camera.userData.referenceFov*Math.PI/360)*fit)*180/Math.PI;
  camera.updateProjectionMatrix();
}
// Project actual mesh bounds rather than the much looser world-axis whole-ship
// box. These conservative corners include the bow, engine pods and pipework.
export function presentationPoints(object) {
  object.updateMatrixWorld(true);const points=[];
  object.traverse(mesh=>{
    if(!mesh.isMesh||!mesh.geometry)return;
    if(!mesh.geometry.boundingBox)mesh.geometry.computeBoundingBox();
    const box=mesh.geometry.boundingBox;if(!box||box.isEmpty())return;
    for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z])points.push(new THREE.Vector3(x,y,z).applyMatrix4(mesh.matrixWorld).toArray());
  });return points;
}
function portraitWholeShip(camera,controls,row,points) {
  if(!camera.isOrthographicCamera||!['whole-ship','whole-underside'].includes(row.id)||!points?.length)return;
  // This is an explicitly different page presentation, not a source-camera
  // comparison. Keep Y up and look along the hull so its length uses the phone's
  // vertical space; all geometry, the model transform and source recipe stay put.
  const distance=camera.position.distanceTo(controls.target),direction=new THREE.Vector3(-.50,row.id==='whole-underside'?-.84:.84,.20).normalize();
  camera.position.copy(controls.target).addScaledVector(direction,distance);camera.lookAt(controls.target);controls.update();camera.updateMatrixWorld(true);
  const inverse=camera.matrixWorldInverse,box=new THREE.Box3();
  for(const point of points)box.expandByPoint(new THREE.Vector3().fromArray(point).applyMatrix4(inverse));
  const center=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3());
  if(!(size.x>0&&size.y>0))return;
  const offset=new THREE.Vector3(center.x,center.y,0).applyQuaternion(camera.quaternion);
  camera.position.add(offset);controls.target.add(offset);controls.update();
  camera.userData.presentation={kind:'portrait-whole-ship',view:row.id,bounds:{width:size.x,height:size.y},padding:1.08};
}
export function applyContractCamera(current,controls,viewId,recipe,aspect=current.aspect||1,{portrait=false,points=null,matched=false}={}) {
  const row=recipe.views.find(view=>view.id===viewId);if(!row)throw Error(`Unpublished camera: ${viewId}`);
  const projection=projectionForView(row,recipe.reference_resolution[0]/recipe.reference_resolution[1],aspect),camera=cameraType(current,controls,row.projection);
  clearNavigationWindow(controls);
  const matrix=new THREE.Matrix4().set(...sourceMatrixToWeb(row.matrix_world).flat());
  camera.position.setFromMatrixPosition(matrix);camera.quaternion.setFromRotationMatrix(matrix).normalize();
  camera.near=row.clip_start_source*.01;camera.far=row.clip_end_source*.01;
  camera.userData.referenceAspect=recipe.reference_resolution[0]/recipe.reference_resolution[1];
  delete camera.userData.presentation;
  if(row.projection==='ORTHO')camera.userData.referenceHeight=projection.height;else camera.userData.referenceFov=projection.fov;
  camera.zoom=1;resizeContractCamera(camera,aspect);controls.target.fromArray(sourcePointToWeb(row.target_source));
  [controls.minDistance,controls.maxDistance]=recipe.distance_limits_source[row.scope].map(n=>n*.01);
  controls.update();
  if(portrait)portraitWholeShip(camera,controls,row,points);
  applyNavigationWindow(camera,controls,row,{matched});
  resizeContractCamera(camera,aspect);camera.updateMatrixWorld(true);return camera;
}
export function captureView(camera,controls) {
  return {projection:camera.isOrthographicCamera?'ORTHO':'PERSP',referenceHeight:camera.isOrthographicCamera?camera.userData.referenceHeight:null,
    referenceAspect:camera.userData.referenceAspect,referenceFov:camera.userData.referenceFov,
    position:camera.position.toArray(),quaternion:camera.quaternion.toArray(),target:controls.target.toArray(),fov:camera.isPerspectiveCamera?camera.fov:null,
    near:camera.near,far:camera.far,aspect:camera.aspect,zoom:camera.zoom,minDistance:controls.minDistance,maxDistance:controls.maxDistance,
    presentation:camera.userData.presentation?structuredClone(camera.userData.presentation):null,
    navigation:camera.userData.navigation?{...camera.userData.navigation}:null};
}
export function restoreView(current,controls,value,aspect=value.aspect) {
  const camera=cameraType(current,controls,value.projection);camera.position.fromArray(value.position);camera.quaternion.fromArray(value.quaternion);
  controls.target.fromArray(value.target);camera.near=value.near;camera.far=value.far;camera.zoom=value.zoom;
  camera.userData.referenceAspect=value.referenceAspect||1.6;
  if(value.presentation)camera.userData.presentation=structuredClone(value.presentation);else delete camera.userData.presentation;
  if(camera.isOrthographicCamera)camera.userData.referenceHeight=value.referenceHeight;else camera.userData.referenceFov=value.referenceFov||value.fov;
  controls.minDistance=value.minDistance;controls.maxDistance=value.maxDistance;
  restoreNavigationWindow(camera,controls,value.navigation);
  resizeContractCamera(camera,aspect);controls.update();
  // Sync OrbitControls' internal spherical state first, then restore the saved
  // pose verbatim. Its spherical/lookAt roundtrip otherwise changes low bits of
  // published positions/quaternions even without user input.
  camera.position.fromArray(value.position);camera.quaternion.fromArray(value.quaternion);controls.target.fromArray(value.target);
  camera.updateMatrixWorld(true);return camera;
}
