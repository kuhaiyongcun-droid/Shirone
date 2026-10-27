import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { cutawayOpen,renderScale } from './interaction.mjs';
import { makeSpace } from './space.mjs';
import { applyContractCamera,captureView,restoreView,resizeContractCamera,frameSize,presentationPoints } from './contract-camera.mjs';
import { createContractLighting } from './contract-lighting.mjs';
import { BLOG_VISUAL_LIGHTING_PROFILE } from './visual-lighting-profile.mjs';
import { presentationInsets } from './presentation-layout.mjs';
import { moveCameraByKey,installTouchDollyGuard } from './camera-navigation.mjs';
import { disposeObject,verifiedBytes } from './resources.mjs';
import { runAssetLoad } from './asset-loading.mjs';
import { parseGlbJson,validateAssetSemantics,sourcePointToWeb } from './asset-contract.mjs';
import { snapshotCompatible,assertImportedSceneHasNoLights,visibilityForView } from './runtime-guards.mjs';

export async function createViewer({viewport,hotspot,quality,state,onError,onLoading,onProgress,signal,review,initialSnapshot,runtime}) {
  if(!runtime?.ready)throw Error('Complete pinned source asset contract required');
  const {contract,cameras,lighting:recipe}=runtime,scene=new THREE.Scene();scene.background=new THREE.Color(0x070b0f);
  let camera=new THREE.PerspectiveCamera(38,1,.0005,400);
  const renderer=new THREE.WebGLRenderer({antialias:quality!=='light',powerPreference:'default'});
  renderer.toneMapping=THREE.AgXToneMapping;renderer.toneMappingExposure=2**recipe.exposure_stops;renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.shadowMap.enabled=quality!=='light';renderer.shadowMap.type=THREE.PCFShadowMap;renderer.domElement.setAttribute('aria-hidden','true');renderer.domElement.hidden=true;viewport.prepend(renderer.domElement);
  const controls=new OrbitControls(camera,renderer.domElement);controls.enablePan=false;controls.enableDamping=false;controls.autoRotate=false;controls.rotateSpeed=.65;controls.minPolarAngle=.06;controls.maxPolarAngle=Math.PI-.06;
  const removeTouchDollyGuard=installTouchDollyGuard(controls);
  const abort=new AbortController(),draco=new DRACOLoader();draco.setDecoderPath(new URL('./assets/draco/',document.baseURI).href);draco.setWorkerLimit(quality==='light'?1:2);
  const loader=new GLTFLoader().setDRACOLoader(draco),anchor=new THREE.Vector3().fromArray(sourcePointToWeb(cameras.archive_anchor_source));
  let dead=false,ready=false,raf=0,currentMode='ship',ship=null,interior=null,interiorPromise=null,savedView=null,savedExteriorView=null;
  let interiorEpoch=0,interiorController=null;
  let exteriorPoints=null;
  let view=cameras.views.some(v=>v.id===review.view&&v.scope==='exterior')?review.view:cameras.defaults.exterior;
  let lightMode=review.lighting,group=review.group,matched=review.matched,gain=review.gain,frame=frameSize(1,1,false);
  const hull=[],shell=[],outline=new THREE.Group();outline.visible=false;scene.add(outline);const space=makeSpace();scene.add(space);
  const pointer=new THREE.Vector2(),ray=new THREE.Raycaster(),pmrem=new THREE.PMREMGenerator(renderer),environment=new RoomEnvironment();
  const environmentTarget=pmrem.fromScene(environment,.06);scene.environment=environmentTarget.texture;scene.environmentIntensity=recipe.environment_intensity;environment.dispose();pmrem.dispose();
  const lights=createContractLighting(scene,quality,recipe,{profile:BLOG_VISUAL_LIGHTING_PROFILE});
  function request(){if(!dead&&!document.hidden&&!raf)raf=requestAnimationFrame(render);}
  function projectBeacon(){
    if(!ready||currentMode!=='ship'){hotspot.hidden=true;return;}scene.updateMatrixWorld(true);camera.updateMatrixWorld(true);const p=anchor.clone().project(camera);
    const x=frame.x+(p.x+1)*frame.width/2,y=frame.y+(1-p.y)*frame.height/2;ray.setFromCamera(new THREE.Vector2(p.x,p.y),camera);
    const obstacle=ray.intersectObjects(hull,false)[0],obscured=obstacle&&obstacle.distance<ray.ray.origin.distanceTo(anchor)-.005;
    const bounds=matched?{left:25,right:viewport.clientWidth-25,top:115,bottom:viewport.clientHeight-150}:{left:frame.x+22,right:frame.x+frame.width-22,top:Math.max(frame.y+22,115),bottom:Math.min(frame.y+frame.height-22,viewport.clientHeight-150)};
    hotspot.hidden=p.z < -1||p.z>1||x<bounds.left||x>bounds.right||y<bounds.top||y>bounds.bottom||!!obscured;
    if(!hotspot.hidden){hotspot.style.left=`${x}px`;hotspot.style.top=`${y}px`;}
  }
  function render(){raf=0;if(dead||document.hidden)return;projectBeacon();renderer.render(scene,camera);}
  function applyLighting(schedule=true){const scope=currentMode==='archive'?'archive':'exterior';lights.setState({scope,mode:lightMode,view,group,gain});space.visible=scope==='exterior'&&lightMode==='space';if(schedule)request();}
  function fit(){camera=applyContractCamera(camera,controls,view,cameras,frame.width/frame.height,
    {portrait:!matched&&viewport.clientWidth<=650&&viewport.clientHeight>viewport.clientWidth,points:exteriorPoints,matched});applyVisibility();applyLighting();request();}
  function resize(){
    const w=Math.max(1,viewport.clientWidth),h=Math.max(1,viewport.clientHeight),aspect=cameras.reference_resolution[0]/cameras.reference_resolution[1];frame=frameSize(w,h,matched,aspect,presentationInsets(viewport,matched));
    resizeContractCamera(camera,frame.width/frame.height);renderer.setPixelRatio(renderScale(frame.width,frame.height,devicePixelRatio||1,quality));renderer.setSize(frame.width,frame.height,false);
    Object.assign(renderer.domElement.style,{width:`${frame.width}px`,height:`${frame.height}px`,left:`${frame.x}px`,top:`${frame.y}px`,position:'absolute'});request();
  }
  // `view` is already an exact exterior camera or its published default. Filter before any event can queue a frame.
  applyLighting(false);
  const observer=new ResizeObserver(resize);observer.observe(viewport);controls.addEventListener('change',request);
  document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(raf);raf=0;}else request();},{signal:abort.signal});
  renderer.domElement.addEventListener('webglcontextlost',e=>{e.preventDefault();if(!dead)onError();},{signal:abort.signal});
  async function loadScope(scope,scopeSignal){
    const controller=new AbortController(),stop=()=>controller.abort();abort.signal.addEventListener('abort',stop,{once:true});
    scopeSignal?.addEventListener('abort',stop,{once:true});if(abort.signal.aborted||scopeSignal?.aborted)controller.abort();
    try{return await runAssetLoad(async load=>{
      const descriptor=contract.assets[scope],url=new URL(descriptor.uri,document.baseURI);url.searchParams.set('v',descriptor.sha256.slice(0,16));
      const bytes=await verifiedBytes(url,descriptor,load.signal,{load}),json=parseGlbJson(bytes),assigned=validateAssetSemantics(scope,json,runtime.semantics);
      load.reportProgress({phase:'decoding',loaded:descriptor.bytes,total:descriptor.bytes});
      load.signal.throwIfAborted();
      const gltf=await loader.parseAsync(bytes,'');
      if(dead||load.signal.aborted){disposeObject(gltf.scene);load.signal.throwIfAborted();throw Error('Viewer disposed');}
      try{assertImportedSceneHasNoLights(gltf.scene);const seen=new Set();gltf.scene.traverse(mesh=>{
        if(!mesh.isMesh)return;
        // Three sanitizes names. Associate the exact original GLB node instead.
        let object=mesh,index;
        while(object){const i=gltf.parser.associations.get(object)?.nodes;if(i!==undefined&&json.nodes[i].mesh!==undefined){index=i;break;}object=object.parent;}
        const name=index===undefined?null:json.nodes[index].name,role=assigned.get(name);if(!role)throw Error('Imported mesh lacks exact semantic node');
        seen.add(name);mesh.userData.p23SourceNode=name;mesh.userData.p23Role=role;mesh.castShadow=true;mesh.receiveShadow=true;mesh.geometry.computeBoundingSphere();
      });if(seen.size!==assigned.size)throw Error('Imported semantic node coverage differs');
        // GLB export_yup has already converted axes. Apply only the one scale.
        gltf.scene.scale.setScalar(contract.coordinate_system.root_scale);return gltf.scene;
      }catch(error){disposeObject(gltf.scene);throw error;}
    },{signal:controller.signal,onProgress:progress=>{if(!dead)onProgress?.({...progress,scope});}});}
    finally{abort.signal.removeEventListener('abort',stop);scopeSignal?.removeEventListener('abort',stop);}
  }
  function loadInterior(){
    if(interiorPromise)return interiorPromise;if(interior)return Promise.resolve(interior);onLoading(true);
    const epoch=++interiorEpoch;interiorController=new AbortController();
    interiorPromise=loadScope('archive',interiorController.signal).then(object=>{
      if(dead||epoch!==interiorEpoch){disposeObject(object);return null;}
      interior=object;scene.add(interior);update(state());return interior;
    }).catch(error=>{if(!dead&&epoch===interiorEpoch){console.warn(error);onError(error);}return null;})
      .finally(()=>{if(!dead&&epoch===interiorEpoch){interiorPromise=null;interiorController=null;onLoading(false);}});return interiorPromise;
  }
  function unloadInterior(){
    ++interiorEpoch;interiorController?.abort();interiorController=null;
    if(interior){scene.remove(interior);disposeObject(interior);interior=null;}
    interiorPromise=null;onLoading(false);
  }
  function applyVisibility(){
    if(!ready||!ship)return;
    const visible=visibilityForView({mode:currentMode,viewId:view,previewOpen:cutawayOpen(state()),interiorReady:!!interior},cameras,runtime.semantics);
    ship.visible=visible.exteriorVisible;const hidden=new Set(visible.hiddenShellNodes);
    for(const mesh of shell)mesh.visible=!hidden.has(mesh.userData.p23SourceNode);
    outline.visible=visible.outlineVisible;if(interior)interior.visible=visible.interiorVisible;
  }
  function update(next){
    if(dead||!ready)return;if(next.mode!==currentMode){
      if(next.mode==='archive'){savedView=captureView(camera,controls);savedExteriorView=view;view=cameras.defaults.archive;currentMode=next.mode;fit();}
      else{currentMode=next.mode;view=savedExteriorView||cameras.defaults.exterior;if(savedView)camera=restoreView(camera,controls,savedView,frame.width/frame.height);else fit();unloadInterior();}
      applyLighting();resize();}
    const open=cutawayOpen(next);if(open&&!interior&&!interiorPromise)loadInterior();else if(!open&&interiorPromise&&!interior)unloadInterior();applyVisibility();request();
  }
  function hit(x,y){
    if(!ready||currentMode!=='ship')return false;const rect=renderer.domElement.getBoundingClientRect();if(x<rect.left||x>rect.right||y<rect.top||y>rect.bottom)return false;
    pointer.set((x-rect.left)/rect.width*2-1,-(y-rect.top)/rect.height*2+1);scene.updateMatrixWorld(true);camera.updateMatrixWorld(true);ray.setFromCamera(pointer,camera);
    const first=ray.intersectObjects([...hull,...shell],false)[0];return !!first&&shell.includes(first.object);
  }
  function key(name){const handled=moveCameraByKey(camera,controls,name);if(handled)request();return handled;}
  function setReview(next){const scope=currentMode==='archive'?'archive':'exterior',nextView=cameras.views.find(v=>v.id===next.view&&v.scope===scope),changed=(nextView&&nextView.id!==view)||matched!==next.matched;
    if(matched!==next.matched)savedView=null;
    if(nextView)view=nextView.id;lightMode=next.lighting;group=next.group;matched=next.matched;gain=next.gain;resize();if(changed)fit();applyVisibility();applyLighting();}
  function snapshot(){camera.updateMatrixWorld(true);ship?.updateMatrixWorld(true);return {revision:contract.revision,sourceSceneSha256:contract.source_scene.sha256,modelSha256:contract.assets.exterior.sha256,archiveSha256:contract.assets.archive.sha256,cameraRecipeSha256:contract.documents.cameras.sha256,
    camera:captureView(camera,controls),cameraWorldMatrix:camera.matrixWorld.toArray(),cameraViewMatrix:camera.matrixWorldInverse.toArray(),cameraProjectionMatrix:camera.projectionMatrix.toArray(),savedView,savedExteriorView,mode:currentMode,shipMatrix:ship?.matrixWorld.toArray(),frame,view,lighting:lightMode,group,matched,gain,quality,interiorLoaded:!!interior,interiorLoading:!!interiorPromise&&!interior,
    render:{...renderer.info.render},memory:{...renderer.info.memory},lightingProfile:lights.profileId,framingProfile:camera.userData.presentation?.kind||(matched?'reference':'source-presentation'),browserAcceptance:false,lightingCalibrated:false};}
  function dispose(){if(dead)return;dead=true;abort.abort();interiorController?.abort();++interiorEpoch;observer.disconnect();cancelAnimationFrame(raf);signal?.removeEventListener('abort',dispose);lights.dispose();removeTouchDollyGuard();controls.dispose();draco.dispose();disposeObject(scene);environmentTarget.dispose();renderer.renderLists.dispose();renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();ship=null;interior=null;interiorPromise=null;}
  try{
    if(signal?.aborted)throw Error('Viewer disposed');signal?.addEventListener('abort',dispose,{once:true});resize();ship=await loadScope('exterior');
    if(dead||signal?.aborted){disposeObject(ship);ship=null;throw Error('Viewer disposed');}
    scene.add(ship);scene.updateMatrixWorld(true);exteriorPoints=presentationPoints(ship);
    ship.traverse(mesh=>{if(!mesh.isMesh)return;if(mesh.userData.p23Role==='archive_shell'){shell.push(mesh);
      const line=new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry,24),new THREE.LineBasicMaterial({color:0xe8b775,transparent:true,opacity:.9}));line.matrixAutoUpdate=false;line.matrix.copy(mesh.matrixWorld);outline.add(line);
    }else hull.push(mesh);});if(!shell.length||!hull.length)throw Error('Missing exact exterior semantic groups');
    ready=true;renderer.domElement.hidden=false;fit();const desiredState=state();update(desiredState);
    if(initialSnapshot?.matched===matched&&snapshotCompatible(initialSnapshot,desiredState.mode,contract,cameras)){camera=restoreView(camera,controls,initialSnapshot.camera,frame.width/frame.height);savedView=initialSnapshot.savedView;savedExteriorView=initialSnapshot.savedExteriorView;view=initialSnapshot.view;}
    resize();applyVisibility();applyLighting();return {update,hit,key,dispose,setReview,snapshot,resize,reset:fit,locate:()=>{view=cameras.archive_locator_view;fit();return view;}};
  }catch(error){dispose();throw error;}
}
