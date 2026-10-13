"""Validate side05 real clearances, route endpoints and panel visibility."""
import argparse,json,hashlib,sys,collections
from pathlib import Path
import bpy,bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0,str(Path(__file__).resolve().parent))
import finish_study as f

P='SIDE05 / '
def tree(o,dg):
    e=o.evaluated_get(dg);m=e.to_mesh();m.calc_loop_triangles()
    vs=[o.matrix_world@v.co for v in m.vertices];fs=[tuple(t.vertices) for t in m.loop_triangles]
    t=BVHTree.FromPolygons(vs,fs,all_triangles=True);e.to_mesh_clear()
    return t,vs,fs
def inside(t,p):
    d=Vector((.618033,.271828,.732051)).normalized();start=p.copy();n=0
    for i in range(80):
        result=t.ray_cast(start,d,10000)
        if result[0] is None:break
        start=result[0]+d*.0001;n+=1
    return bool(n%2)
def main(a):
    global P
    P=getattr(a,'prefix','SIDE05 / ')
    f.PREFIX=getattr(a,'protected_prefix',P)
    bpy.ops.wm.open_mainfile(filepath=str(a.baseline.resolve()));before=f.protected()
    had_front='side05_front' in bpy.data.objects
    bpy.ops.wm.open_mainfile(filepath=str(a.scene.resolve()))
    cam=bpy.data.objects['side05_front']
    if not had_front:cam.name=P+'front inspection camera'
    after=f.protected()
    if not had_front:
        after['cameras'].pop(cam.name,None);cam.name='side05_front'
    checks={'prior_content_preserved':before==after}
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    visible={}
    def visit(c,hidden=False):
        hidden=hidden or c.hide_render
        if hidden or c.name=='SPACE':return
        for o in c.objects:
            if o.type=='MESH' and not o.hide_render and o.visible_get():visible[o.name]=o
        for child in c.children:visit(child,hidden)
    visit(bpy.context.scene.collection)
    trees={};verts=[];faces=[];owner=[];mesh={};bad=[]
    for name,o in sorted(visible.items()):
        t,vs,fs=tree(o,dg);trees[name]=t;mesh[name]=(vs,fs)
        offset=len(verts);verts.extend(vs);faces.extend(tuple(offset+i for i in f) for f in fs);owner.extend([name]*len(fs))
        if name.startswith(P) and o.get('validation_type')!='surface_marking':
            e=o.evaluated_get(dg);m=e.to_mesh();bm=bmesh.new();bm.from_mesh(m)
            if not all(edge.is_manifold for edge in bm.edges) or bm.calc_volume(signed=True)<=0:bad.append(name)
            bm.free();e.to_mesh_clear()
    world=BVHTree.FromPolygons(verts,faces,all_triangles=True)
    hulls=['BRIDGE01 / Tapered bridge plinth','FORM03 / Prow upper wedge',P+'Opened structural abutment',
           P+'Service bay pressure boundary 0',P+'Service bay pressure boundary 1']
    collisions=[];ends=[];supports=[];tees=[];clearance_groups=[]
    for name,o in visible.items():
        if not name.startswith(P):continue
        if o.get('assembly_group') in ('E1','E2','E3','P1','P2','P3') or o.get('assembly_route'):
            for h in hulls:
                crossings=len(trees[name].overlap(trees[h]))
                inside_count=sum(inside(trees[h],v) for v in mesh[name][0][::max(1,len(mesh[name][0])//24)])
                if crossings or inside_count:collisions.append({'object':name,'hull':h,'crossed_triangle_pairs':crossings,'inside_samples':inside_count})
        if o.get('assembly_route'):
            points=json.loads(o['route_points'])
            for side,p in (('start',points[0]),('end',points[-1])):
                target=o[side+'_target'];p=Vector(p);near=trees[target].find_nearest(p)
                enclosed=inside(trees[target],p)
                ends.append({'route':name,'side':side,'target':target,'inside_fitting':enclosed,'nearest_surface':round(near[3],6)})
        if o.get('support_points'):
            for side,p in zip(('start','end'),json.loads(o['support_points'])):
                target=o[side+'_target'];supports.append({'support':name,'side':side,'target':target,'attached':inside(trees[target],Vector(p))})
        if o.get('mate_manifold'):
            tees.append({'tee':name,'manifold':o['mate_manifold'],'attached':inside(trees[o['mate_manifold']],o.matrix_world.translation)})
    checks['closed_solids']=not bad
    checks['equipment_and_routes_clear_of_hull']=not collisions
    checks['all_functional_endpoints_in_fittings']=all(e['inside_fitting'] for e in ends)
    checks['mounts_and_tees_attached']=all(s['attached'] for s in supports+tees)
    views=[]
    def samples(o):
        corners=[Vector(v) for v in o.bound_box];lo=Vector(tuple(min(v[k] for v in corners) for k in range(3)));hi=Vector(tuple(max(v[k] for v in corners) for k in range(3)))
        return [o.matrix_world@Vector((lo.x+(hi.x-lo.x)*(.1+.8*x/16),lo.y-.002,lo.z+(hi.z-lo.z)*(.1+.8*z/16))) for x in range(17) for z in range(17)]
    for base,label in (('Inset module face','E'),('Canister instrument saddle','P')):
        for i in range(3):
            name=P+base+('' if i==0 else '.'+str(i).zfill(3));pts=samples(visible[name]);group=label+str(i+1)
            for camname in ('side03_detail','side03_reverse','side05_front'):
                origin=bpy.data.objects[camname].matrix_world.translation;hits=collections.Counter();ok=0
                for p in pts:
                    d=p-origin;r=world.ray_cast(origin,d.normalized(),d.length+.15)
                    n=owner[r[2]] if r[2] is not None else 'none';hits[n]+=1
                    if n in visible and visible[n].get('assembly_group')==group:ok+=1
                views.append({'panel':group,'camera':camname,'visible_fraction':round(ok/len(pts),4),'occluders':dict(hits.most_common(4))})
    checks['inspection_panels_visible']=all(r['visible_fraction']>=.90 for r in views)
    images=[{'name':i.name,'packed':bool(i.packed_file),'relative':i.filepath.startswith('//'),
             'exists':Path(bpy.path.abspath(i.filepath)).exists()} for i in bpy.data.images if i.type=='IMAGE' and i.users]
    checks['portable_images']=all(i['packed'] and i['relative'] and i['exists'] for i in images)
    result={'checks':checks,'passed':all(checks.values()),'source_sha256':hashlib.sha256(a.scene.read_bytes()).hexdigest(),
            'collisions':collisions,'invalid_meshes':bad,'route_endpoints':ends,'support_endpoints':supports,'manifold_tees':tees,
            'panel_visibility':views,'images':images,'browser_tested':False}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'checks':checks,'collisions':collisions,'bad_endpoints':[e for e in ends if not e['inside_fitting']],
                      'occluded_panels':[r for r in views if r['visible_fraction']<.90]},indent=2))
    print('BAD_SUPPORTS',json.dumps([s for s in supports+tees if not s['attached']]))
    if not result['passed']:raise SystemExit(1)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--scene',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prefix',default='SIDE05 / ')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None);main(a)
