"""Merge validated fore08 changes with unchanged surface06 baked bridge data.

Retains the six embedded bridge PBR textures. New fore08 materials are simple
PBR approximations pending regional art review/baking. No website is changed.
"""
import argparse,json,sys,shutil
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fore_study as fore
import export_review as web
from fore_check import require
from surface_finish import sha
BAKED='74decbc0e7bf2976b21f8e5bfe4c3e5d700d04759611f331c4cc915b9a0dbd42'

def export(a):
 r=require(a.source,a.validation);assert sha(a.baked)==BAKED
 assert not a.output.exists() and not a.derivative.exists()
 bpy.ops.wm.open_mainfile(filepath=str(a.baked.resolve()))
 with bpy.data.libraries.load(str(a.source.resolve()),link=False) as (available,wanted):
  wanted.collections=[fore.NEW,fore.CUT]
 for c in wanted.collections:
  if c not in list(bpy.context.scene.collection.children):bpy.context.scene.collection.children.link(c)
 for name in fore.REMOVED:bpy.data.objects[name].hide_render=True
 bpy.data.collections[fore.CUT].hide_render=True;bpy.data.collections[fore.CUT].hide_viewport=True
 bpy.context.view_layer.update();a.derivative.parent.mkdir(parents=True,exist_ok=True)
 for image in bpy.data.images:
  if image.type=='IMAGE' and image.users:
   assert image.packed_file
   p=a.derivative.parent/'textures'/Path(image.filepath).name;p.parent.mkdir(exist_ok=True);p.write_bytes(image.packed_file.data)
   image.filepath='//textures/'+p.name
   for packed in image.packed_files:packed.filepath=image.filepath
 bpy.context.scene['fore08_editable_sha256']=sha(a.source)
 bpy.context.preferences.filepaths.save_version=0
 bpy.ops.wm.save_as_mainfile(filepath=str(a.derivative.resolve()),compress=True,relative_remap=False)
 derivative_hash=sha(a.derivative);web.SOURCE_REVISIONS[derivative_hash]='fore08-geometry-with-surface06-bakes'
 web.GROUPS['SIDE06_BAKED']='hull';web.GROUPS[fore.NEW]='hull';web.export(a.derivative,a.output)
 assert (a.output/'archive.glb').read_bytes()==(a.previous_assets/'archive.glb').read_bytes(),'Archive changed'
 for name in ('service-lights.glb','service-lighting.mjs'):shutil.copy2(a.previous_assets/name,a.output/name)
 # This is still the unchanged lighting07 rig. Pin it to the new mesh bytes.
 profile=json.loads((a.previous_assets/'service-lighting.json').read_text())
 profile.update(model_sha256=sha(a.output/'flagship.glb'),model_revision='fore-structure-08',
                model_source_sha256=sha(a.source),browser_tested=False)
 (a.output/'service-lighting.json').write_text(json.dumps(profile,indent=2)+'\n')
 p=a.output/'model-manifest.json';m=json.loads(p.read_text())
 m.update(revision='fore-structure-08-web',editable_source_sha256=sha(a.source),
  assembly_validation_sha256=sha(a.validation),baked_bridge_input_sha256=BAKED,
  materials='Bridge: unchanged surface06 PBR atlases. Fore08 and older rest of ship: approximate simple PBR.',
  new_fore_material_baking_complete=False,archive_byte_identical=True,lighting_rig_unchanged=True,
  browser_tested=False,published=False)
 p.write_text(json.dumps(m,indent=2)+'\n')
 print('FORE_EXPORT',json.dumps(m['files']),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True)
 p.add_argument('--baked',type=Path,required=True);p.add_argument('--previous-assets',type=Path,required=True)
 p.add_argument('--derivative',type=Path,required=True);p.add_argument('--output',type=Path,required=True);export(p.parse_args())
