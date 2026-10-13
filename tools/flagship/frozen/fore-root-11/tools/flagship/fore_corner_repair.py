"""Close four verified fore08-C corner gaps without rebuilding the assembly.

The main fore_study generator contains the same corrected dimensions. This
small recovery step preserves the exact reviewed candidate C and records the
repair as a fresh immutable scene. Full fore_check is required afterwards.
"""
import argparse,json,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fore_study as fore
from surface_finish import sha
EXPECTED='9335bfa460d8c1831085d79e1ee8c99dc3de6348cebedc139745196ab2728a12'
def main(a):
 assert sha(a.source)==EXPECTED and not a.output.exists()
 prior=json.loads(a.validation.read_text());assert prior['source_sha256']==EXPECTED and prior['passed']
 assert len(prior['checks'])==15 and all(prior['checks'].values())
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));before=fore.protected()
 repairs=[]
 for name,axis,old,new in [('Inboard continuous sill',0,21.8,22.4),('Outboard continuous sill',0,21.8,22.4),
                          ('Fore pressure bulkhead',1,8.5,9.1),('Aft pressure bulkhead',1,8.5,9.1)]:
  o=bpy.data.objects[fore.P+name]
  for v in o.data.vertices:v.co[axis]*=new/old
  o.data.update();repairs.append({'object':o.name,'axis':axis,'old_span':old,'new_span':new})
 bpy.context.view_layer.update();assert fore.protected()==before
 a.output.parent.mkdir(parents=True,exist_ok=True)
 for image in bpy.data.images:
  if image.type=='IMAGE' and image.users:
   assert image.packed_file;p=a.output.parent/'textures'/Path(image.filepath).name;p.parent.mkdir(exist_ok=True);p.write_bytes(image.packed_file.data)
   image.filepath='//textures/'+p.name
   for packed in image.packed_files:packed.filepath=image.filepath
 bpy.context.scene['fore08_corner_repair_parent']=EXPECTED
 bpy.context.preferences.filepaths.save_version=0
 bpy.ops.wm.save_as_mainfile(filepath=str(a.output.resolve()),compress=True,relative_remap=False)
 r={'revision':'fore-structure-08','source_sha256':sha(a.output),'direct_repair_input_sha256':EXPECTED,
    'immutable_lighting07_input_sha256':fore.INPUT,'repairs':repairs,'full_validation_required':True,'browser_tested':False}
 a.output.with_suffix('.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
