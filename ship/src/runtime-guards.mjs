// No Three dependency: these guards also run in the offline regression suite.
export function snapshotCompatible(snapshot,mode,contract,cameras) {
  if(!snapshot||!['ship','archive'].includes(mode)||snapshot.mode!==mode)return false;
  if(snapshot.revision!==contract.revision||snapshot.sourceSceneSha256!==contract.source_scene.sha256||
    snapshot.modelSha256!==contract.assets.exterior.sha256||snapshot.archiveSha256!==contract.assets.archive.sha256||
    snapshot.cameraRecipeSha256!==contract.documents.cameras.sha256)return false;
  const scope=mode==='archive'?'archive':'exterior',view=cameras.views.find(row=>row.id===snapshot.view&&row.scope===scope);
  if(!view||snapshot.camera?.projection!==view.projection)return false;
  if(snapshot.savedView){
    const exterior=cameras.views.find(row=>row.id===snapshot.savedExteriorView&&row.scope==='exterior');
    if(!exterior||snapshot.savedView.projection!==exterior.projection)return false;
  }
  return true;
}
export function assertImportedSceneHasNoLights(root) {
  root.traverse(object=>{if(object.isLight)throw Error('P23 imported GLB light forbidden; lighting must come from the reviewed recipe');});
}
export function visibilityForView({mode,viewId,previewOpen,interiorReady},cameras,semantics) {
  const scope=mode==='archive'?'archive':'exterior',view=cameras.views.find(row=>row.id===viewId&&row.scope===scope);
  if(!view)throw Error('P23 visibility requires a published camera in the current scope');
  const preview=mode==='ship'&&previewOpen&&interiorReady;
  return {exteriorVisible:true,interiorVisible:interiorReady&&(mode==='archive'||preview),outlineVisible:preview,
    hiddenShellNodes:preview?[...semantics.assets.exterior.archive_shell]:[...view.hidden_shell_nodes]};
}
export function lightAppliesToView(light,{scope,mode,view}) {
  return (light.scope===scope||light.scope==='all')&&light.modes.includes(mode)&&
    (light.views===undefined||light.views.includes(view));
}
