"""Combine fore09 baked material sample with the immutable six bridge atlases."""
import argparse,json,sys,shutil
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fore_study as fore
import export_review as web
from fore_surface_check import require
from surface_finish import sha
BRIDGE='74decbc0e7bf2976b21f8e5bfe4c3e5d700d04759611f331c4cc915b9a0dbd42'
PRIOR_MAIN='012172a48097a27473b4e0f52178c0f0286e0fcce3a56fc7f9d108874abceff5'

def main(a):
 require(a.source,a.validation);assert sha(a.bridge)==BRIDGE
 bake=json.loads((a.baked.parent/'bake-report.json').read_text());assert bake['source_sha256']==sha(a.source) and bake['bake_sha256']==sha(a.baked)
 assert bake['geometry_vertices_faces_equal'] and bake['surface_objects']==98
 assert sha(a.previous_assets/'flagship.glb')==PRIOR_MAIN
 assert not a.output.exists() and not a.derivative.exists()
 bpy.ops.wm.open_mainfile(filepath=str(a.bridge.resolve()))
 # Hosts retain editable boolean modifiers. Their cutter must be linked into
 # the scene graph, not merely loaded as an unlinked dependency datablock.
 with bpy.data.libraries.load(str(a.baked.resolve()),link=False) as (available,wanted):wanted.collections=['FORE09_BAKED',fore.CUT]
 for c in wanted.collections:bpy.context.scene.collection.children.link(c)
 bpy.data.collections[fore.CUT].hide_render=True;bpy.data.collections[fore.CUT].hide_viewport=True
 for name in fore.REMOVED:bpy.data.objects[name].hide_render=True
 bpy.context.view_layer.update();a.derivative.parent.mkdir(parents=True,exist_ok=True)
 for img in bpy.data.images:
  if img.type=='IMAGE' and img.users:
   assert img.packed_file;p=a.derivative.parent/'textures'/Path(img.filepath).name;p.parent.mkdir(exist_ok=True)
   if p.exists():assert p.read_bytes()==img.packed_file.data,'Texture basename collision'
   else:p.write_bytes(img.packed_file.data)
   img.filepath='//textures/'+p.name
   for packed in img.packed_files:packed.filepath=img.filepath
 bpy.context.scene['fore09_editable_sha256']=sha(a.source);bpy.context.preferences.filepaths.save_version=0
 bpy.ops.wm.save_as_mainfile(filepath=str(a.derivative.resolve()),compress=True,relative_remap=False)
 web.SOURCE_REVISIONS[sha(a.derivative)]='fore09-pbr-with-unchanged-surface06-bakes';web.GROUPS['SIDE06_BAKED']='hull';web.GROUPS['FORE09_BAKED']='hull';web.export(a.derivative,a.output)
 assert (a.output/'archive.glb').read_bytes()==(a.previous_assets/'archive.glb').read_bytes()
 for name in ('service-lights.glb','service-lighting.mjs'):shutil.copy2(a.previous_assets/name,a.output/name)
 profile=json.loads((a.previous_assets/'service-lighting.json').read_text());profile.update(model_sha256=sha(a.output/'flagship.glb'),model_revision='fore-surface-09',model_source_sha256=sha(a.source),browser_tested=False)
 (a.output/'service-lighting.json').write_text(json.dumps(profile,indent=2)+'\n')
 p=a.output/'model-manifest.json';m=json.loads(p.read_text());m.update(revision='fore-surface-09-web',editable_source_sha256=sha(a.source),surface_validation_sha256=sha(a.validation),baked_fore_sha256=sha(a.baked),baked_bridge_sha256=BRIDGE,
  materials='Bridge: six unchanged surface06 PNG atlases. Fore09 service surfaces: three new PBR PNG atlases. Retained hosts/older hull: approximate PBR. Clearcoat omitted; no baked AO or lighting.',
  fore_service_surface_baking_complete=True,whole_ship_materials_complete=False,archive_byte_identical=True,lighting_rig_unchanged=True,browser_tested=False,published=False)
 p.write_text(json.dumps(m,indent=2)+'\n');print('FORE09_EXPORT',json.dumps(m['files']),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--bridge',type=Path,required=True);p.add_argument('--baked',type=Path,required=True);p.add_argument('--previous-assets',type=Path,required=True);p.add_argument('--derivative',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
