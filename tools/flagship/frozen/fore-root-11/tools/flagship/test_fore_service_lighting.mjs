/** Isolated lifetime/abort tests. Mocks do not constitute Three/WebGL QA. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {attachServiceLighting} from './fore-service-lighting.mjs';
const profile=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
function fakeRig(duplicate=false){
 const lights=profile.lights.map((r,i)=>({isLight:true,intensity:2,visible:true,userData:{service_light_id:duplicate&&i===5?profile.lights[0].id:r.id,service_group:r.group},shadow:{mapSize:{set(){}},camera:{updateProjectionMatrix(){}},dispose(){this.disposeCount=(this.disposeCount??0)+1;}}}));
 return {scene:{traverse(fn){lights.forEach(fn);}},lights};
}
function root(){const mesh={isMesh:true,castShadow:false,receiveShadow:false};return {mesh,children:[],add(x){this.children.push(x);},remove(x){this.children=this.children.filter(o=>o!==x);},traverse(fn){fn(mesh);}};}
const p={profile,modelSha256:profile.model_sha256,lightUrl:'memory://test',intensityScale:1.25};let tested=[];
{
 const rig=fakeRig(),shipRoot=root();const h=await attachServiceLighting({...p,shipRoot,loader:{loadAsync:async()=>rig}});
 assert.equal(shipRoot.children.length,1);assert.equal(shipRoot.mesh.castShadow,true);h.setGroup('fore');assert.equal(rig.lights.filter(x=>x.visible).length,3);
 await assert.rejects(attachServiceLighting({...p,shipRoot,loader:{loadAsync:async()=>rig}}),/Dispose/);
 h.dispose();h.dispose();assert.equal(shipRoot.children.length,0);assert.equal(shipRoot.mesh.castShadow,false);assert.equal(shipRoot.mesh.receiveShadow,false);assert(rig.lights.every(x=>x.shadow.disposeCount===1));tested.push('ownership, regional selection and idempotent disposal');
}
{
 const rig=fakeRig(true),shipRoot=root();await assert.rejects(attachServiceLighting({...p,shipRoot,loader:{loadAsync:async()=>rig}}),/Unexpected/);
 assert.equal(shipRoot.children.length,0);assert(rig.lights.every(x=>x.shadow.disposeCount===1));const h=await attachServiceLighting({...p,shipRoot,loader:{loadAsync:async()=>fakeRig()}});h.dispose();tested.push('invalid duplicate light IDs rejected, ownership released');
}
{
 const rig=fakeRig(),shipRoot=root(),controller=new AbortController();let release;
 const pending=attachServiceLighting({...p,shipRoot,signal:controller.signal,loader:{loadAsync:()=>new Promise(resolve=>release=resolve)}});controller.abort();release(rig);await assert.rejects(pending,/cancelled/);
 assert.equal(shipRoot.children.length,0);assert(rig.lights.every(x=>x.shadow.disposeCount===1));const h=await attachServiceLighting({...p,shipRoot,loader:{loadAsync:async()=>fakeRig()}});h.dispose();tested.push('abort while loading does not attach or retain resources');
}
console.log(JSON.stringify({passed:true,tests:tested,browser_tested:false,three_executed:false}));
