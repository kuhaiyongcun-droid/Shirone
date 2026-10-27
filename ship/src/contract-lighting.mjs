import * as THREE from 'three';
import { sourcePointToWeb } from './asset-contract.mjs';
import { lightAppliesToView } from './runtime-guards.mjs';
import { resolveVisualLightingProfile } from './visual-lighting-profile.mjs';
// Source-bound preview recipe. No historical light asset or AREA-light equivalence.
export function createContractLighting(scene,quality,recipe,{profile='source-recipe'}={}) {
  const presentation=resolveVisualLightingProfile(recipe,profile);
  const root=new THREE.Group();root.name='P23 source-bound preview lighting';scene.add(root);const entries=[];
  for(const row of [...recipe.lights,...presentation.lights]){
    const color=new THREE.Color().setRGB(...row.color_linear,THREE.LinearSRGBColorSpace);
    const light=row.type==='directional'?new THREE.DirectionalLight(color,row.intensity_web):new THREE.SpotLight(color,row.intensity_web,row.distance_source*.01,row.angle_radians,row.penumbra,2);
    light.visible=false; // Stay inactive until the current scope, mode and view have been applied.
    light.name=row.id;light.position.fromArray(sourcePointToWeb(row.position_source));light.target.position.fromArray(sourcePointToWeb(row.target_source));
    light.castShadow=quality!=='light'&&row.shadow.enabled;
    if(row.shadow.enabled){light.shadow.mapSize.set(row.shadow.map_size,row.shadow.map_size);light.shadow.camera.near=row.shadow.near_source*.01;light.shadow.camera.far=row.shadow.far_source*.01;
      light.shadow.bias=row.shadow.bias;light.shadow.normalBias=row.shadow.normal_bias_source*.01;
      if(row.type==='directional'){const span=row.shadow.span_source*.01;Object.assign(light.shadow.camera,{left:-span,right:span,top:span,bottom:-span});
        // Web shadow maps need a receiver offset tied to their texel footprint.
        // The source recipe's smaller offset caused visible self-shadow stripes.
        light.shadow.normalBias=Math.max(light.shadow.normalBias,1.5*2*span/row.shadow.map_size);
        light.shadow.bias=Math.min(light.shadow.bias,-.00015);
      }light.shadow.camera.updateProjectionMatrix();}
    root.add(light,light.target);entries.push({light,row});
  }
  let dead=false;
  function setState({scope,mode,view,group='all',gain=1}){if(dead)return;for(const {light,row} of entries){const service=row.group!=='key'&&row.group!=='fill';
    light.visible=lightAppliesToView(row,{scope,mode,view})&&(!service||(group!=='off'&&(group==='all'||group===row.group)));light.intensity=row.intensity_web*(service?gain:1);}}
  function dispose(){if(dead)return;dead=true;for(const {light} of entries){light.visible=false;light.shadow?.dispose();root.remove(light);root.remove(light.target);}entries.length=0;scene.remove(root);}
  return {root,setState,dispose,calibrated:false,profileId:presentation.id};
}
