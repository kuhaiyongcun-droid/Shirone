"""Bake only the verified side sample into unlit base/ORM/tangent-normal atlases.

Editable source stays untouched. The evaluated web copy keeps exact source
geometry and custom normals; native equipment stencils and emitters remain
separate. CPU only, no dependency installation.
"""
import argparse,hashlib,json,math,sys,time
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from surface_gate import require
from surface_finish import sha

def atlas_group(o):
 name=o.name.removeprefix('SIDE06 / ')
 if o.get('validation_type')=='surface_marking' or 'Shielded service emitter' in name:return 'native'
 if name.startswith(('Opened structural','Service bay pressure','Bay ','Primary diagonal','Forward overlapping armor','Aft overlapping armor','Service attachment rail','Structural attachment pad','Service rail bracket','Recessed worklight hood')):return 'structure'
 return 'equipment'

def evaluated_group(objects,name,dg,col):
 vertices=[];faces=[];normals=[];indices=[];materials=[];lookup={}
 for o in objects:
  e=o.evaluated_get(dg);m=e.to_mesh();offset=len(vertices);vertices.extend(o.matrix_world@v.co for v in m.vertices)
  normal_matrix=o.matrix_world.to_3x3().inverted().transposed()
  for poly in m.polygons:
   faces.append(tuple(offset+i for i in poly.vertices));mat=o.material_slots[poly.material_index].material
   if mat.name not in lookup:lookup[mat.name]=len(materials);materials.append(mat)
   indices.append(lookup[mat.name])
   normals.extend((normal_matrix@m.corner_normals[i].vector).normalized() for i in poly.loop_indices)
  e.to_mesh_clear()
 mesh=bpy.data.meshes.new('BAKED06 / '+name);mesh.from_pydata(vertices,[],faces);mesh.update()
 for p,i in zip(mesh.polygons,indices):p.material_index=i;p.use_smooth=True
 mesh.normals_split_custom_set(normals)
 for m in materials:mesh.materials.append(m)
 o=bpy.data.objects.new(mesh.name,mesh);col.objects.link(o);o['role']='hull';o['source_objects']=json.dumps([x.name for x in objects])
 bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
 bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
 bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.004,area_weight=.15,correct_aspect=True,scale_to_bounds=False)
 bpy.ops.object.mode_set(mode='OBJECT');return o

def bake_channel(obj,channel,size,path):
 image=bpy.data.images.new('SIDE06 '+obj.name.rsplit(' / ',1)[-1]+' '+channel,width=size,height=size,alpha=False)
 image.colorspace_settings.name='sRGB' if channel=='basecolor' else 'Non-Color'
 image.filepath_raw=str(path.resolve());image.file_format='PNG'
 modified=[]
 for mat in obj.data.materials:
  n,l=mat.node_tree.nodes,mat.node_tree.links;b=n.get('Principled BSDF');out=n.get('Material Output')
  old=out.inputs['Surface'].links[0].from_socket;temp=[]
  tex=n.new('ShaderNodeTexImage');tex.image=image;n.active=tex;temp.append(tex)
  if channel!='normal':
   emission=n.new('ShaderNodeEmission');temp.append(emission)
   def value(sock,target):
    if sock.is_linked:l.new(sock.links[0].from_socket,target)
    else:target.default_value=sock.default_value
   if channel=='basecolor':value(b.inputs['Base Color'],emission.inputs['Color'])
   else:
    combine=n.new('ShaderNodeCombineColor');combine.mode='RGB';temp.append(combine);combine.inputs[0].default_value=1
    value(b.inputs['Roughness'],combine.inputs[1]);value(b.inputs['Metallic'],combine.inputs[2]);l.new(combine.outputs[0],emission.inputs['Color'])
   l.new(emission.outputs[0],out.inputs['Surface'])
  modified.append((mat,old,temp))
 start=time.perf_counter()
 bpy.ops.object.bake(type='NORMAL' if channel=='normal' else 'EMIT',margin=6 if size==2048 else 3,use_clear=True)
 image.save();image.pack();image.filepath='//textures/'+path.name
 for mat,old,temp in modified:
  mat.node_tree.links.new(old,mat.node_tree.nodes.get('Material Output').inputs['Surface'])
  for n in temp:mat.node_tree.nodes.remove(n)
 return image,{'channel':channel,'size':size,'seconds':round(time.perf_counter()-start,3),'bytes':path.stat().st_size,'sha256':sha(path),'path':'textures/'+path.name}

def baked_material(name,images):
 m=bpy.data.materials.new('BAKED06 / '+name);m.use_nodes=True;m['baked_pbr']=True
 n,l=m.node_tree.nodes,m.node_tree.links;b=n.get('Principled BSDF')
 for kind,img in images.items():
  t=n.new('ShaderNodeTexImage');t.name='Baked '+kind;t.image=img;t.interpolation='Linear';t.extension='EXTEND'
  if kind=='basecolor':l.new(t.outputs['Color'],b.inputs['Base Color'])
  elif kind=='orm':
   separate=n.new('ShaderNodeSeparateColor');separate.mode='RGB';l.new(t.outputs['Color'],separate.inputs[0])
   l.new(separate.outputs[1],b.inputs['Roughness']);l.new(separate.outputs[2],b.inputs['Metallic'])
  else:
   normal=n.new('ShaderNodeNormalMap');l.new(t.outputs['Color'],normal.inputs['Color']);l.new(normal.outputs[0],b.inputs['Normal'])
 return m

def main(a):
 validation=require(a.source,a.validation);assert not a.output.exists(),'Fresh bake directory required'
 a.output.mkdir(parents=True);texdir=a.output/'textures';texdir.mkdir()
 bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()));scene=bpy.context.scene
 scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8;scene.render.threads_mode='FIXED';scene.render.threads=6
 bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
 groups={k:[] for k in ('structure','equipment','native')}
 for o in bpy.data.collections['SIDE06_STRUCTURE'].objects:groups[atlas_group(o)].append(o)
 col=bpy.data.collections.new('SIDE06_BAKED');scene.collection.children.link(col);results=[]
 for name in ('structure','equipment'):
  o=evaluated_group(groups[name],name,dg,col);images={};records=[]
  for channel in ('basecolor','orm','normal'):
   size=2048 if name=='equipment' and channel=='basecolor' else 1024
   img,r=bake_channel(o,channel,size,texdir/(name+'-'+channel+'.png'));images[channel]=img;records.append(r)
   print('BAKE_CHANNEL',name,json.dumps(r),flush=True)
  o.data.materials.clear();o.data.materials.append(baked_material(name,images))
  for p in o.data.polygons:p.material_index=0
  o.data.calc_loop_triangles();results.append({'group':name,'source_objects':len(groups[name]),'triangles':len(o.data.loop_triangles),'images':records})
 for old in groups['native']:
  o=old.copy();o.data=old.data.copy();o.name='BAKED06 / '+old.name.removeprefix('SIDE06 / ');col.objects.link(o)
 bpy.data.collections['SIDE06_STRUCTURE'].hide_render=True;bpy.data.collections['SIDE06_STRUCTURE'].hide_viewport=True
 for image in bpy.data.images:
  if image.type=='IMAGE' and image.users:
   p=texdir/Path(image.filepath).name
   if not p.exists():
    assert image.packed_file;p.write_bytes(image.packed_file.data)
   image.filepath='//textures/'+p.name
   for packed in image.packed_files:packed.filepath=image.filepath
 blend=a.output/'flagship-side-surface-06-web.blend';bpy.context.preferences.filepaths.save_version=0
 bpy.ops.wm.save_as_mainfile(filepath=str(blend.resolve()),compress=True,relative_remap=False)
 assert sha(a.source)==validation['source_sha256']
 report={'source_sha256':sha(a.source),'bake_sha256':sha(blend),'source_unchanged':True,'geometry_validation_sha256':sha(a.validation),
         'atlases':results,'native_objects':len(groups['native']),'channels':'Unlit sRGB base color, linear ORM (R=1, G=roughness, B=metallic), tangent normal',
         'limitation':'Source coating clearcoat (0.10) is not baked; web uses base PBR lobe. No baked lighting or AO. Whole-ship materials outside this sample remain simple approximations.',
         'browser_tested':False,'device':'CPU','threads':6}
 (a.output/'bake-report.json').write_text(json.dumps(report,indent=2)+'\n');print('BAKE_COMPLETE',json.dumps(report),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
