// Browser presentation only. This does not edit or replace the pinned source recipe.
// Keep neutral available as the unchanged reference and leave AgX/exposure alone.
export const BLOG_VISUAL_LIGHTING_PROFILE='blog-visual-v1';
export const VISUAL_LIGHTING_SOURCE_SHA256='dd35a7b43c94ba22a03aa0f27e0b88de549cce594971829c9e0e6913e04d0339';

function frozenRow(row){
  for(const key of ['modes','position_source','target_source','color_linear'])Object.freeze(row[key]);
  Object.freeze(row.shadow);return Object.freeze(row);
}

const lights=Object.freeze([
  frozenRow({
    id:'web-visual-belly-bounce',type:'directional',scope:'exterior',modes:['space'],group:'fill',
    // Low cool light from below/front separates the belly from the background.
    // It is fixed in ship coordinates, so orbiting does not switch or chase it.
    position_source:[-430,-560,-500],target_source:[-12,0,0],
    color_linear:[.42,.59,.8],intensity_web:.36,shadow:{enabled:false}
  }),
  frozenRow({
    id:'web-visual-upper-gallery-bounce',type:'spot',scope:'archive',modes:['space'],group:'archive-existing',
    // A bounded soft cone across the upper gallery, aimed slightly upward.
    // This is an art-directed fill, not a new source lamp or physical bounce simulation.
    position_source:[-72,-39,22.15],target_source:[-94,-39,24.15],
    color_linear:[.95,.79,.58],intensity_web:.01,
    distance_source:34,angle_radians:1.0,penumbra:.85,shadow:{enabled:false}
  })
]);

const sourceProfile=Object.freeze({id:'source-recipe',lights:Object.freeze([]),calibrated:false});
const visualProfile=Object.freeze({id:BLOG_VISUAL_LIGHTING_PROFILE,sourceSceneSha256:VISUAL_LIGHTING_SOURCE_SHA256,
  lights,calibrated:false,extraShadowMaps:0});

export function resolveVisualLightingProfile(recipe,requested='source-recipe'){
  if(requested==='source-recipe')return sourceProfile;
  if(requested!==BLOG_VISUAL_LIGHTING_PROFILE)throw Error('Unknown browser lighting profile');
  // A profile for one measured layout must not silently illuminate another asset.
  if(recipe.source_scene_sha256!==VISUAL_LIGHTING_SOURCE_SHA256)throw Error('Browser lighting profile source identity differs');
  return visualProfile;
}
