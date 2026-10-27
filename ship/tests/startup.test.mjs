import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { registerHooks } from 'node:module';

// Import the real lighting module with a narrow object-only Three double. This never runs a browser backend.
const hook=registerHooks({resolve(specifier,context,next){
  if(specifier==='three'&&context.parentURL?.endsWith('/src/contract-lighting.mjs'))
    return {url:new URL('./fixtures/three-lighting-double.mjs',import.meta.url).href,shortCircuit:true};
  return next(specifier,context);
}});
const {createContractLighting}=await import('../src/contract-lighting.mjs');
hook.deregister();
const {Group}=await import('./fixtures/three-lighting-double.mjs');
const {docs,PIN}=await import('./fixtures/release-source.mjs');
const recipe=docs.lighting,cameras=docs.cameras;
const emittedLights=lighting=>lighting.root.children.filter(child=>child.isLight);

test('actual published lighting recipe starts with every light hidden before the first state selection',()=>{
  const lighting=createContractLighting(new Group(),'standard',recipe),lights=emittedLights(lighting);
  assert.equal(lights.length,recipe.lights.length);assert.equal(lights.length,PIN.expectedLights);
  assert.equal(lights.filter(light=>light.castShadow).length,PIN.expectedShadowLights);
  assert.equal(lights.filter(light=>light.visible).length,0);
  assert.equal(lights.filter(light=>light.visible&&light.castShadow).length,0);
  lighting.dispose();
});

test('actual light initialization and every published view respect the active shadow budget',()=>{
  for(const quality of ['standard','light']){
    const lighting=createContractLighting(new Group(),quality,recipe),lights=emittedLights(lighting);
    // This is the first state applied before observer registration / resize can queue a frame.
    lighting.setState({scope:'exterior',mode:'neutral',view:cameras.defaults.exterior,group:'all',gain:1});
    assert.ok(lights.some(light=>light.visible));
    for(const camera of cameras.views)for(const mode of ['neutral','space'])for(const group of ['all','off']){
      lighting.setState({scope:camera.scope,mode,view:camera.id,group,gain:1.5});
      for(let i=0;i<lights.length;i++){
        const row=recipe.lights[i],service=row.group!=='key'&&row.group!=='fill';
        const expected=(row.scope==='all'||row.scope===camera.scope)&&row.modes.includes(mode)&&
          (!row.views||row.views.includes(camera.id))&&(!service||group==='all');
        assert.equal(lights[i].visible,expected,`${camera.id}/${mode}/${group}/${row.id}`);
      }
      const activeShadows=lights.filter(light=>light.visible&&light.castShadow).length;
      assert.ok(activeShadows<=(quality==='light'?0:recipe.shadow_budget.standard_max_lights),`${camera.id}/${mode}/${quality}: ${activeShadows}`);
    }
    lighting.dispose();
  }
});

test('viewer filters its valid initial exterior view before event registration and the first resize request',async()=>{
  const source=await readFile(new URL('../src/contract-viewer.mjs',import.meta.url),'utf8');
  const selection=source.indexOf("let view=cameras.views.some(v=>v.id===review.view&&v.scope==='exterior')?review.view:cameras.defaults.exterior;");
  const init=source.indexOf('applyLighting(false);');
  assert.ok(selection>=0&&selection<init);
  assert.ok(init<source.indexOf('observer.observe(viewport)'));
  assert.ok(init<source.indexOf("controls.addEventListener('change',request)"));
  assert.ok(init<source.indexOf("resize();ship=await loadScope('exterior')"));
  assert.match(source,/function applyLighting\(schedule=true\)\{[^\n]+lights\.setState\([^\n]+if\(schedule\)request\(\);\}/);
});
