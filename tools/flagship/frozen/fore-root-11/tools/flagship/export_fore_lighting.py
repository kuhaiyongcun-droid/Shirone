"""Keep fore09 baked hull; append mounted fore10 fixtures and export six lamps."""
import argparse,json,math,shutil,struct,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import export_review as web
import fore_lighting as s
from fore_light_check import require
from surface_finish import sha
PRIOR_MAIN='a5d059554bf71baa37d5e6ee99c26b77d6cfea1a9691cb1a4f7a56ac1d21e0e7'
def light_definitions(config):
 old=json.loads(Path(__file__).with_name('lighting-study-07.json').read_text());rows=[]
 for d in old['lights']:rows.append(dict(d,id=d['name'],source_name=old['prefix']+d['name'],group='bridge'))
 for d in config['fixtures']:rows.append(dict(d,name=d['id'],source_name=s.P+d['id']+' / task beam',group='fore',cast_shadow=True,web_shadow_map=config['web_shadow_map'],fixture=s.P+d['id']+' / inset downward diffuser'))
 return rows
def export(a):
 check=require(a.source,a.validation);cfg=json.loads(a.config.read_text());assert check['config_sha256']==sha(a.config)
 old=json.loads((a.assets/'model-manifest.json').read_text());assert old['editable_source_sha256']==s.INPUT and sha(a.assets/'flagship.glb')==PRIOR_MAIN
 assert sha(a.web_source)==old['source_sha256'];assert not a.output.exists() and not a.derivative.exists()
 bpy.ops.wm.open_mainfile(filepath=str(a.web_source.resolve()))
 # Existing FORE08_CUTTERS stays linked in this verified web scene.
 assert bpy.data.collections['FORE08_CUTTERS'] in list(bpy.context.scene.collection.children)
 with bpy.data.libraries.load(str(a.source.resolve()),link=False) as (available,wanted):wanted.collections=[s.FIX]
 for c in wanted.collections:bpy.context.scene.collection.children.link(c)
 a.derivative.parent.mkdir(parents=True,exist_ok=True)
 for image in bpy.data.images:
  if image.type=='IMAGE' and image.users:
   assert image.packed_file;p=a.derivative.parent/'textures'/Path(image.filepath).name;p.parent.mkdir(exist_ok=True)
   if p.exists():assert p.read_bytes()==image.packed_file.data
   else:p.write_bytes(image.packed_file.data)
   image.filepath='//textures/'+p.name
   for packed in image.packed_files:packed.filepath=image.filepath
 bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(a.derivative.resolve()),compress=True,relative_remap=False)
 web.SOURCE_REVISIONS[sha(a.derivative)]='fore10-mounted-fixtures-on-verified-fore09';web.GROUPS.update({'SIDE06_BAKED':'hull','FORE09_BAKED':'hull',s.FIX:'hull'});web.export(a.derivative,a.output)
 assert (a.output/'archive.glb').read_bytes()==(a.assets/'archive.glb').read_bytes()
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));scene=bpy.data.scenes.new('Fore10 plus retained bridge07 light rig');bpy.context.window.scene=scene;rows=[]
 for d in light_definitions(cfg):
  source=bpy.data.objects[d['source_name']];o=source.copy();o.data=source.data.copy();scene.collection.objects.link(o)
  o.name='WEB10 / '+d['group']+' / '+d['id'];o.data.name=o.name;o.location=source.location/100;o.data.energy=source.data.energy/10000;o.data.shadow_soft_size=source.data.shadow_soft_size/100
  o['service_light_id']=d['id'];o['service_group']=d['group'];o['ship_fixed']=True
  rows.append({'id':d['id'],'name':o.name,'source_name':d['source_name'],'group':d['group'],
   'position_web':[d['position'][0]/100,d['position'][2]/100,-d['position'][1]/100],'target_web':[d['target'][0]/100,d['target'][2]/100,-d['target'][1]/100],
   'expected_intensity_cd':d['energy_w']/10000/(4*math.pi)*683,'cast_shadow':True,'shadow_map':512,'shadow_near':.001 if d['group']=='fore' else .002,
   'shadow_far':.18 if d['group']=='fore' else (1.6 if d['fixture'] is None else .5),'normal_bias':.0001 if d['group']=='fore' else .0003,'source_radius_m':d['radius']})
 path=a.output/'service-lights.glb';bpy.ops.export_scene.gltf(filepath=str(path.resolve()),export_format='GLB',use_active_scene=True,export_lights=True,export_cameras=False,export_animations=False,export_extras=True,export_yup=True,export_import_convert_lighting_mode='SPEC')
 raw=path.read_bytes();d=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]]);lights=d['extensions']['KHR_lights_punctual']['lights'];assert len(lights)==6 and not d.get('meshes')
 actual={x['name']:x for x in lights}
 for row in rows:assert actual[row['name']]['type']=='spot' and abs(actual[row['name']]['intensity']-row['expected_intensity_cd'])<.00001
 profile={'revision':'fore-lighting-10','source_sha256':sha(a.source),'config_sha256':sha(a.config),'model_sha256':sha(a.output/'flagship.glb'),'lights_sha256':sha(path),'light_count':6,'lights':rows,
  'host_intensity_calibration_required':True,'coordinate_system':'Y up; 100 source meters per web unit; attach to ship root',
  'camera_contract':'No camera/pointer attachment, animation loop or auto-rotation.',
  'shadow_limit':'Up to six 512 shadow maps in all mode; three active in a regional mode. KHR_lights_punctual omits finite-source radii, so browser shadows differ from Cycles. Host calibration and device performance remain untested.',
  'browser_tested':False,'published':False}
 (a.output/'service-lighting.json').write_text(json.dumps(profile,indent=2)+'\n');shutil.copy2(Path(__file__).with_name('fore-service-lighting.mjs'),a.output/'service-lighting.mjs')
 p=a.output/'model-manifest.json';m=json.loads(p.read_text());m.update(revision='fore-lighting-10-web',editable_source_sha256=sha(a.source),prior_fore09_source_sha256=s.INPUT,lighting_validation_sha256=sha(a.validation),materials=old['materials']+' New lamp fixtures use simple PBR and dim emitter surfaces.',
  preserved_baked_textures=9,added_fixture_meshes=18,archive_byte_identical=True,old_bridge_lights_preserved=True,added_fore_lights=3,
  lighting_assets={n:{'bytes':(a.output/n).stat().st_size,'sha256':sha(a.output/n)} for n in ('service-lights.glb','service-lighting.json','service-lighting.mjs')},browser_tested=False,published=False)
 p.write_text(json.dumps(m,indent=2)+'\n');print('FORE10_WEB',json.dumps(m['files']),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--config',type=Path,default=s.DEFAULT);p.add_argument('--web-source',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--derivative',type=Path,required=True);p.add_argument('--output',type=Path,required=True);export(p.parse_args())
