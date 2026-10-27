import * as THREE from 'three';

// Deliberately small viewing adjustments around authored interior cameras.
// This is an orbit window, not collision detection or walk-through navigation.
const windows={
  'archive-cutaway':{yaw:12,pitch:8,near:.90,far:1.10},
  'archive-entry':{yaw:2,pitch:.5,near:.99,far:1.01},
  'archive-upper':{yaw:1.5,pitch:1,near:.995,far:1.005},
  vestibule:{yaw:2,pitch:1,near:.99,far:1.01}
};
const fields=['minAzimuthAngle','maxAzimuthAngle','minPolarAngle','maxPolarAngle','minDistance','maxDistance','enableRotate','enableZoom'];
const dollyGuards=new WeakMap();
// Thin adapter for the pinned Three 0.186.1 OrbitControls touch implementation.
// Re-run real-handler and DOM pointer-chain tests when upgrading Three: these
// underscore members are implementation details, not a stable upstream API.
export function installTouchDollyGuard(controls){
  if(dollyGuards.has(controls))return dollyGuards.get(controls);
  if(typeof controls?._handleTouchMoveDolly!=='function'||typeof controls?._getSecondPointerPosition!=='function'||typeof controls?._dollyStart?.set!=='function')throw Error('Touch dolly guard: expected pinned OrbitControls touch handlers are unavailable');
  const original=controls._handleTouchMoveDolly;
  function guarded(event){
    const other=this._getSecondPointerPosition(event),dx=event.pageX-other?.x,dy=event.pageY-other?.y;
    const distance=Math.sqrt(dx*dx+dy*dy),previous=this._dollyStart.y,ratio=Math.pow(distance/previous,this.zoomSpeed);
    if(!Number.isFinite(distance)||distance<=1e-6||!Number.isFinite(previous)||previous<=1e-6||!Number.isFinite(ratio)||ratio<=0){
      // Zero separation cannot define a pinch ratio. Re-baseline without
      // allowing NaN into _scale; the next ordinary pinch remains usable.
      this._dollyStart.set(0,Number.isFinite(distance)?distance:0);return;
    }
    return original.call(this,event);
  }
  controls._handleTouchMoveDolly=guarded;let installed=true;
  const remove=()=>{if(!installed)return;installed=false;if(controls._handleTouchMoveDolly===guarded)controls._handleTouchMoveDolly=original;dollyGuards.delete(controls);};
  dollyGuards.set(controls,remove);return remove;
}
export function clearNavigationWindow(controls){
  controls.minAzimuthAngle=-Infinity;controls.maxAzimuthAngle=Infinity;
  controls.minPolarAngle=.06;controls.maxPolarAngle=Math.PI-.06;
  controls.enableRotate=true;controls.enableZoom=true;
}
export function applyNavigationWindow(camera,controls,row,{matched=false}={}){
  clearNavigationWindow(controls);
  const sphere=new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
  const window=windows[row.id];let profile='exterior-free';
  if(matched){profile='matched-reference-lock';controls.enableRotate=false;controls.enableZoom=false;}
  else if(row.scope==='archive'&&window){
    profile='interior-recommended-window-v1';
    const rad=Math.PI/180;
    controls.minAzimuthAngle=sphere.theta-window.yaw*rad;controls.maxAzimuthAngle=sphere.theta+window.yaw*rad;
    controls.minPolarAngle=Math.max(.06,sphere.phi-window.pitch*rad);controls.maxPolarAngle=Math.min(Math.PI-.06,sphere.phi+window.pitch*rad);
    controls.minDistance=sphere.radius*window.near;controls.maxDistance=sphere.radius*window.far;
  }
  camera.userData.navigation={profile,...Object.fromEntries(fields.map(key=>[key,controls[key]]))};
}
export function restoreNavigationWindow(camera,controls,value){
  clearNavigationWindow(controls);
  if(value){for(const field of fields)if(value[field]!==undefined)controls[field]=value[field];camera.userData.navigation={...value};}
  else delete camera.userData.navigation;
}
export function moveCameraByKey(camera,controls,key){
  if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','=','-','−'].includes(key))return false;
  const zoom=['+','=','-','−'].includes(key);
  if((zoom&&!controls.enableZoom)||(!zoom&&!controls.enableRotate))return true;
  if(camera.isOrthographicCamera&&zoom){camera.zoom*= ['+','='].includes(key)?1/.9:.9;camera.updateProjectionMatrix();return true;}
  const sphere=new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
  if(key==='ArrowLeft')sphere.theta+=.1;else if(key==='ArrowRight')sphere.theta-=.1;
  else if(key==='ArrowUp')sphere.phi-=.1;else if(key==='ArrowDown')sphere.phi+=.1;
  else if(['+','='].includes(key))sphere.radius*=.9;else sphere.radius/=.9;
  sphere.theta=THREE.MathUtils.clamp(sphere.theta,controls.minAzimuthAngle,controls.maxAzimuthAngle);
  sphere.phi=THREE.MathUtils.clamp(sphere.phi,controls.minPolarAngle,controls.maxPolarAngle);
  sphere.radius=THREE.MathUtils.clamp(sphere.radius,controls.minDistance,controls.maxDistance);
  camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(sphere));controls.update();return true;
}
