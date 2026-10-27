import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {createContractLighting} from '../src/contract-lighting.mjs';
import {BLOG_VISUAL_LIGHTING_PROFILE,VISUAL_LIGHTING_SOURCE_SHA256,resolveVisualLightingProfile} from '../src/visual-lighting-profile.mjs';
import {docs} from './fixtures/release-source.mjs';

const recipe=docs.lighting;
const selected={profile:BLOG_VISUAL_LIGHTING_PROFILE};
const allLights=lighting=>lighting.root.children.filter(child=>child.isLight);
const sourceLights=lighting=>allLights(lighting).filter(light=>!light.name.startsWith('web-visual-'));
const addedLights=lighting=>allLights(lighting).filter(light=>light.name.startsWith('web-visual-'));

test('presentation must be explicitly requested and bound to the unchanged source',()=>{
  const before=JSON.stringify(recipe),scene=new THREE.Scene();
  const baseline=createContractLighting(scene,'standard',recipe);
  assert.equal(baseline.profileId,'source-recipe');assert.equal(allLights(baseline).length,recipe.lights.length);baseline.dispose();
  assert.throws(()=>createContractLighting(scene,'standard',{...recipe,source_scene_sha256:'0'.repeat(64)},selected),/source identity differs/);
  assert.throws(()=>createContractLighting(scene,'standard',recipe,{profile:'unknown'}),/Unknown/);
  assert.equal(scene.children.length,0);assert.equal(recipe.source_scene_sha256,VISUAL_LIGHTING_SOURCE_SHA256);
  assert.equal(JSON.stringify(recipe),before);
});

test('real Three lights keep neutral and every source lamp exactly unchanged',()=>{
  for(const quality of ['standard','light']){
    const baseline=createContractLighting(new THREE.Scene(),quality,recipe);
    const visual=createContractLighting(new THREE.Scene(),quality,recipe,selected);
    assert.equal(visual.calibrated,false);assert.equal(visual.profileId,BLOG_VISUAL_LIGHTING_PROFILE);
    assert.ok(allLights(visual).every(light=>light.visible===false));
    for(const camera of docs.cameras.views)for(const mode of ['neutral','space'])for(const group of ['all','off',...Object.keys(recipe.group_labels)]){
      const state={scope:camera.scope,view:camera.id,mode,group,gain:1.5};baseline.setState(state);visual.setState(state);
      const originals=allLights(baseline),actual=sourceLights(visual);
      assert.equal(originals.length,actual.length);
      for(let index=0;index<actual.length;index++){
        const a=actual[index],b=originals[index];
        assert.equal(a.visible,b.visible);assert.equal(a.intensity,b.intensity);assert.equal(a.castShadow,b.castShadow);
        assert.deepEqual(a.position.toArray(),b.position.toArray());assert.deepEqual(a.target.position.toArray(),b.target.position.toArray());assert.deepEqual(a.color.toArray(),b.color.toArray());
      }
      if(mode==='neutral')assert.ok(addedLights(visual).every(light=>!light.visible));
      assert.ok(allLights(visual).filter(light=>light.visible&&light.castShadow).length<=(quality==='light'?0:recipe.shadow_budget.standard_max_lights));
    }
    baseline.dispose();visual.dispose();
  }
});

test('fills stay fixed across orbit views, follow scope and service controls, and never cast shadows',()=>{
  const lighting=createContractLighting(new THREE.Scene(),'light',recipe,selected);
  const [belly,upper]=addedLights(lighting);assert.equal(belly.isDirectionalLight,true);assert.equal(upper.isSpotLight,true);
  assert.deepEqual(upper.position.toArray(),[-.72,.2215,.39]);
  assert.equal(upper.distance,.34);assert.equal(upper.decay,2);assert.ok(upper.angle<Math.PI/2);assert.ok(upper.penumbra>=.8);
  assert.equal(belly.castShadow,false);assert.equal(upper.castShadow,false);
  for(const view of docs.cameras.views){
    for(const group of ['all','off','archive-existing','vestibule'])for(const gain of [0,.5,1,1.5]){
      lighting.setState({scope:view.scope,view:view.id,mode:'space',group,gain});
      assert.equal(belly.visible,view.scope==='exterior');assert.equal(belly.intensity,.36);
      assert.equal(upper.visible,view.scope==='archive'&&['all','archive-existing'].includes(group));assert.equal(upper.intensity,.01*gain);
    }
  }
  lighting.dispose();
});

test('profile is immutable and every source and presentation shadow is disposed once',()=>{
  const profile=resolveVisualLightingProfile(recipe,BLOG_VISUAL_LIGHTING_PROFILE);
  assert.ok(Object.isFrozen(profile)&&Object.isFrozen(profile.lights));
  assert.throws(()=>{profile.lights[0].position_source[0]=0;},TypeError);
  const scene=new THREE.Scene(),lighting=createContractLighting(scene,'standard',recipe,selected);
  const emitted=allLights(lighting),calls=new Map();
  for(const light of emitted){calls.set(light,0);light.shadow.dispose=()=>calls.set(light,calls.get(light)+1);}
  lighting.dispose();lighting.dispose();lighting.setState({scope:'archive',mode:'space',view:'archive-upper'});
  assert.equal(scene.children.length,0);assert.equal(lighting.root.children.length,0);
  assert.ok(emitted.every(light=>calls.get(light)===1&&!light.visible&&light.parent===null&&light.target.parent===null));
});
