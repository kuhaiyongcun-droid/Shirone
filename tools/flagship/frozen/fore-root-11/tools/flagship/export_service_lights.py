"""Export a separate punctual light rig; reuse unchanged surface06 GLBs.

Positions are divided by 100 and pointlike powers by 100^2, preserving
inverse-square illumination in web units. The glTF exporter owns W -> cd.
Source radii and shadow settings are documented separately because glTF
punctual lights do not preserve Blender finite-source soft shadows.
"""
import argparse,json,math,shutil,struct,sys
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from surface_gate import require
from surface_finish import sha
from lighting_study import DEFAULT
def export(a):
 check=require(a.source,a.validation);cfg=json.loads(a.config.read_text());assert check['config_sha256']==sha(a.config)
 assert check['checks']['declared_lights_only'] and check['checks']['lighting_configuration']
 old=json.loads((a.assets/'model-manifest.json').read_text());assert old['editable_source_sha256']==cfg['source_sha256']
 assert not a.output.exists();a.output.mkdir(parents=True)
 for name in ('flagship.glb','archive.glb'):
  assert sha(a.assets/name)==old['files'][name]['sha256'];shutil.copy2(a.assets/name,a.output/name)
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));source_scene=bpy.context.scene
 scene=bpy.data.scenes.new('Service lighting / web units');bpy.context.window.scene=scene
 rows=[]
 for d in cfg['lights']:
  old_light=bpy.data.objects[cfg['prefix']+d['name']];o=old_light.copy();o.data=old_light.data.copy();scene.collection.objects.link(o)
  o.name='WEB07 / '+d['name'];o.data.name=o.name;o.location=old_light.location/100;o.data.energy=old_light.data.energy/10000
  o.data.shadow_soft_size=old_light.data.shadow_soft_size/100
  o['web_shadow_map']=d['web_shadow_map'];o['source_radius_m']=d['radius'];o['ship_fixed']=True
  o['source_light']=old_light.name
  o['service_light_id']=d['name']
  rows.append({'id':d['name'],'name':o.name,'source_light':old_light.name,'position_web':[d['position'][0]/100,d['position'][2]/100,-d['position'][1]/100],
   'target_web':[d['target'][0]/100,d['target'][2]/100,-d['target'][1]/100],
   'color_linear':d['color_linear'],'expected_intensity_cd':d['energy_w']/10000/(4*math.pi)*683,
   'cast_shadow':d['cast_shadow'],'shadow_map':d['web_shadow_map'],'source_radius_m':d['radius'],
   'shadow_near':.002,'shadow_far':1.6 if d['fixture'] is None else .5})
 path=a.output/'service-lights.glb'
 bpy.ops.export_scene.gltf(filepath=str(path.resolve()),export_format='GLB',use_active_scene=True,export_lights=True,
  export_cameras=False,export_animations=False,export_extras=True,export_yup=True,export_import_convert_lighting_mode='SPEC')
 raw=path.read_bytes();doc=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
 exported=doc['extensions']['KHR_lights_punctual']['lights'];assert len(exported)==3 and not doc.get('meshes')
 actual={x['name']:x for x in exported}
 for row in rows:
  d=actual[row['name']];assert d['type']=='spot' and abs(d['intensity']-row['expected_intensity_cd'])<.00001
 profile={'revision':'side-lighting-07','coordinate_system':'glTF Y up, 100 source meters per web unit; attach to ship root',
  'source_sha256':sha(a.source),'input_surface_sha256':cfg['source_sha256'],'config_sha256':sha(a.config),
  'model_sha256':sha(a.output/'flagship.glb'),'lights_sha256':sha(path),'lights':rows,'browser_tested':False,
  'host_intensity_calibration_required':True,'runtime_adapter_status':'JavaScript syntax checked; browser integration not yet tested',
  'shadow_limit':'Three spot shadows requested at 512 each; Blender finite-radius shadow softness is not preserved by KHR_lights_punctual. Browser shadow quality and FPS untested.',
  'camera_contract':'Ship-fixed. No camera attachment, pointer parallax, auto-rotation or new animation loop.'}
 (a.output/'service-lighting.json').write_text(json.dumps(profile,indent=2)+'\n')
 shutil.copy2(Path(__file__).with_name('service-lighting.mjs'),a.output/'service-lighting.mjs')
 old.update(revision='side-lighting-07-web',lighting_source_sha256=sha(a.source),geometry_and_materials_unchanged_from_surface06=True,
  lighting_assets={'service-lights.glb':{'bytes':path.stat().st_size,'sha256':sha(path)},'service-lighting.json':{'sha256':sha(a.output/'service-lighting.json')},'service-lighting.mjs':{'sha256':sha(a.output/'service-lighting.mjs')}},
  browser_performance_tested=False,published=False)
 (a.output/'model-manifest.json').write_text(json.dumps(old,indent=2)+'\n');print(json.dumps(profile,indent=2),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--config',type=Path,default=DEFAULT)
 p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);export(p.parse_args())
