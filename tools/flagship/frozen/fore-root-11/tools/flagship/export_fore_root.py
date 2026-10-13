"""Append validated fore11 roots to the verified fore10 web scene."""
import argparse,json,shutil,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fore_root as s
import export_review as web
from fore_root_check import require
from surface_finish import sha
PRIOR_MAIN='f9d5a8f531e8a53f57a64caffdc1c9e2a5782dcc676977f6851e75d25870919b'
def export(a):
 r=require(a.source,a.validation);cfg=json.loads(a.config.read_text());assert r['config_sha256']==sha(a.config)
 prior=json.loads((a.previous_assets/'model-manifest.json').read_text());assert sha(a.previous_assets/'flagship.glb')==PRIOR_MAIN and prior['editable_source_sha256']==s.INPUT and sha(a.web_source)==prior['source_sha256'];assert not a.output.exists() and not a.derivative.exists()
 bpy.ops.wm.open_mainfile(filepath=str(a.web_source.resolve()));assert bpy.data.collections['FORE08_CUTTERS'] in list(bpy.context.scene.collection.children)
 with bpy.data.libraries.load(str(a.source.resolve()),link=False) as (available,wanted):wanted.collections=[s.NEW,s.CUT]
 for c in wanted.collections:bpy.context.scene.collection.children.link(c)
 for name in [cfg['removed_object']]+cfg['removed_overlays']:bpy.data.objects[name].hide_render=True
 bpy.data.collections[s.CUT].hide_render=True;bpy.data.collections[s.CUT].hide_viewport=True
 a.derivative.parent.mkdir(parents=True,exist_ok=True)
 for im in bpy.data.images:
  if im.type=='IMAGE' and im.users:
   assert im.packed_file;p=a.derivative.parent/'textures'/Path(im.filepath).name;p.parent.mkdir(exist_ok=True)
   if p.exists():assert p.read_bytes()==im.packed_file.data
   else:p.write_bytes(im.packed_file.data)
   im.filepath='//textures/'+p.name
   for packed in im.packed_files:packed.filepath=im.filepath
 bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(a.derivative.resolve()),compress=True,relative_remap=False)
 web.SOURCE_REVISIONS[sha(a.derivative)]='fore11-root-structure-on-verified-fore10';web.GROUPS.update({'SIDE06_BAKED':'hull','FORE09_BAKED':'hull','FORE10_FIXTURES':'hull',s.NEW:'hull'});web.export(a.derivative,a.output)
 assert (a.output/'archive.glb').read_bytes()==(a.previous_assets/'archive.glb').read_bytes()
 for name in ('service-lights.glb','service-lighting.mjs'):shutil.copy2(a.previous_assets/name,a.output/name)
 profile=json.loads((a.previous_assets/'service-lighting.json').read_text());profile.update(model_sha256=sha(a.output/'flagship.glb'),model_revision='fore-root-11',model_source_sha256=sha(a.source),browser_tested=False,published=False)
 (a.output/'service-lighting.json').write_text(json.dumps(profile,indent=2)+'\n')
 p=a.output/'model-manifest.json';m=json.loads(p.read_text());m.update(revision='fore-root-11-web',editable_source_sha256=sha(a.source),prior_fore10_source_sha256=s.INPUT,assembly_validation_sha256=sha(a.validation),config_sha256=sha(a.config),
  materials='Nine prior bridge/fore09 PBR atlases unchanged. Fore11 armor/frame/link uses existing palette in simple PBR; regional surface refinement remains pending.',new_root_material_baking_complete=False,
  root_meshes=38,replaced_root_objects=[cfg['removed_object']]+cfg['removed_overlays'],preserved_baked_textures=9,archive_byte_identical=True,lighting_glb_and_adapter_byte_identical=True,
  lighting_assets={n:{'bytes':(a.output/n).stat().st_size,'sha256':sha(a.output/n)} for n in ('service-lights.glb','service-lighting.json','service-lighting.mjs')},browser_tested=False,published=False)
 p.write_text(json.dumps(m,indent=2)+'\n');print('FORE11_WEB',json.dumps(m['files']),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--config',type=Path,default=s.DEFAULT);p.add_argument('--web-source',type=Path,required=True);p.add_argument('--previous-assets',type=Path,required=True);p.add_argument('--derivative',type=Path,required=True);p.add_argument('--output',type=Path,required=True);export(p.parse_args())
