"""Side05: repair assembly relationships from immutable side04, CPU only."""
import argparse,hashlib,json,sys
from pathlib import Path
import bpy
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
sys.path.insert(0,str(Path(__file__).resolve().parent))
import side_study as s
import finish_study as f
import build_scene as base

PREFIX='SIDE05 / ';NEW='SIDE05_STRUCTURE'
EXPECTED='2b5bbd664279a5bf210fcc9916aa2b797069271801db414a030d7e37b57b4911'
ROUTES=[]
LAST_WALL=None
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def short(o):return o.name.removeprefix(PREFIX)
def center(o):return sum((o.matrix_world@Vector(p) for p in o.bound_box),Vector())/8
def point(o):return o.matrix_world.translation.copy()
def obj(name):return bpy.data.objects[PREFIX+name]
def suffix(i):return '' if i==0 else '.'+str(i).zfill(3)
def transform(o,old,new,scale=(1,1,1)):
    o.matrix_world=Matrix.Translation(new)@Matrix.Diagonal((*scale,1))@Matrix.Translation(-Vector(old))@o.matrix_world
def cylinder(name,loc,radius,depth,mat='s_metal',direction=(0,0,1)):
    o=s.finish(base.cylinder(name,loc,radius,depth,mat,'Z',NEW,vertices=24),'installed service fitting')
    o.rotation_euler=Vector(direction).to_track_quat('Z','Y').to_euler()
    return o
def route(name,points,radius,start,end):
    o=s.pipe(name,points,radius)
    o['assembly_route']=True
    o['start_target']=start.name;o['end_target']=end.name
    o['route_points']=json.dumps([list(p) for p in points]);o['route_radius']=radius
    ROUTES.append(o.name)
    return o
def tree(o,dg):
    e=o.evaluated_get(dg);m=e.to_mesh();m.calc_loop_triangles()
    t=BVHTree.FromPolygons([o.matrix_world@v.co for v in m.vertices],[tuple(t.vertices) for t in m.loop_triangles],all_triangles=True)
    e.to_mesh_clear();return t
def wall_at(x,y,z,trees):
    global LAST_WALL
    hits=[]
    for name,t in trees.items():
        p,n,index,d=t.ray_cast(Vector((x,y,z)),Vector((0,1,0)),50)
        if p is not None:hits.append((d,p,name))
    if not hits:raise RuntimeError('No wall behind attachment')
    closest=min(hits,key=lambda v:v[0]);LAST_WALL=closest[2]
    return closest[1]
def support_contacts(o,start,end,start_target,end_target):
    o['support_points']=json.dumps([list(start),list(end)])
    o['start_target']=start_target;o['end_target']=end_target
def bulkhead(name,p,r=.35):
    # The flange sits outside the surface; its socket sleeve reaches into the wall.
    plate=cylinder(name+' flange',(p.x,p.y-.055,p.z),r,.16,'s_paint',(0,1,0))
    port=cylinder(name+' socket',(p.x,p.y-.18,p.z),r*.59,.44,'s_metal',(0,1,0))
    for o in (plate,port):o['wall_attachment']=True
    return port

def build(source,output):
    assert sha(source)==EXPECTED,'Unregistered input'
    assert not output.exists(),'Choose a new output'
    bpy.ops.wm.open_mainfile(filepath=str(source.resolve()))
    f.PREFIX=PREFIX
    protected=f.protected()
    base.COLLECTIONS.update({c.name:c for c in bpy.data.collections});base.collection(NEW)
    for old in list(bpy.data.collections['SIDE04_STRUCTURE'].objects):
        o=old.copy();o.data=old.data.copy() if old.data else None
        o.name=PREFIX+old.name.removeprefix('SIDE04 / ')
        o['source_object']=old.name
        bpy.data.collections[NEW].objects.link(o)
    bpy.data.collections['SIDE04_STRUCTURE'].hide_render=True
    bpy.data.collections['SIDE04_STRUCTURE'].hide_viewport=True
    s.NEW,s.PREFIX=NEW,PREFIX;s.PARTS=[]
    for key in ('s_paint','s_repair','s_dark','s_metal','s_pipe','s_seal','s_mark','s_label','s_ivory','s_connector','s_primer'):
        base.MATERIALS[key]=bpy.data.materials['SIDE04 / '+key]
    base.MATERIALS['s_lamp']=bpy.data.materials['SIDE04 / warm service lamp']
    remove=('Cassette routed connection','Cassette rear mounting arm','Avionics lower carrier','Carrier junction',
        'Upper segmented manifold','Upper manifold connector','Lower fluid return','Aft electrical trunk',
        'Secondary equipment carrier','Cylinder rear mounting arm','Shield stand-off','Sill inner folded channel',
        'Tray spaced transverse support','Cable tray cushioned cleat','Separated signal umbilical',
        'Trunk removable terminal cover','stencil J-07','Rear equipment mounting rail','Rail header terminal','Upper line isolated union')
    for o in list(bpy.data.collections[NEW].objects):
        if short(o).startswith(remove):bpy.data.objects.remove(o,do_unlink=True)

    cassette_names=('Isolated cassette cradle','Replaceable electronics module','Inset module face','Module face protective rib',
        'Module identity strip','Cassette lid overlap','Recessed lifting handle','Cassette removable header','stencil E-',
        'Captive quarter-turn latch','Cassette side cooling plate','Cassette sealed plug','Isolated equipment foot','Cassette extraction contact track')
    oldxs=(-185.5,-182.1,-178.7);newcs=((-184.7,-26.55,34.5),(-181.4,-26.55,34.95),(-178.1,-26.55,35.2))
    canister_names=('Manifold mounting shoe','Vertical service cylinder','Cylinder restraint','Cylinder split collar',
        'Cylinder label','Canister removable end cap','Canister compression flange','Canister bottom coupling',
        'Canister top coupling','Canister top locking nut','Canister instrument saddle','Recessed diagnostic port',
        'Diagnostic port inset','stencil P','Carrier side folded flange','Carrier transverse shoe','Split clamp axial pin','Maintenance replacement tab')
    oldcan=(-169.6,-163.9,-158.8);deltas=((0,-1.1,.8),(0,0,.8),(0,0,1.4))
    shield_names=('Removable equipment shield','Shield compressed gasket','Shield two-piece lid','stencil SVC 07',
        'Recessed guard latch','Latch actuating slot','Folded maintenance grip','Lid tool contact')
    for o in list(bpy.data.collections[NEW].objects):
        name=short(o);c=center(o)
        fixing=name.startswith('Captive hex fixing')
        idx=int(name.rsplit('.',1)[1]) if fixing and '.' in name else 0
        if name.startswith(cassette_names) or (fixing and 10<=idx<=15):
            i=min(range(3),key=lambda i:abs(c.x-oldxs[i]))
            transform(o,(oldxs[i],-23,33.1+i*.12),newcs[i],(1,1,.75));o['assembly_group']='E'+str(i+1)
        elif name.startswith(canister_names) or (fixing and 16<=idx<=21):
            i=min(range(3),key=lambda i:abs(c.x-oldcan[i]))
            o.matrix_world=Matrix.Translation(deltas[i])@o.matrix_world;o['assembly_group']='P'+str(i+1)
            if name.startswith('Manifold mounting shoe'):
                o.scale.z*=4.6/6.5;o.scale.y*=.5;o.location.y-=.25
        elif name.startswith(shield_names) or (fixing and idx>=34):
            transform(o,(-169.05,-28.35,34.55),(-166.8,-27.65,34.3),(.55,1,.65));o['assembly_group']='guard'
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    hullnames=['BRIDGE01 / Tapered bridge plinth','FORM03 / Prow upper wedge',PREFIX+'Opened structural abutment',
               PREFIX+'Service bay pressure boundary 0',PREFIX+'Service bay pressure boundary 1']
    hulls={n:tree(bpy.data.objects[n],dg) for n in hullnames}
    # Each cassette anchors to the first actual hull surface behind it.
    for i,(x,y,z) in enumerate(newcs):
        for dz in (-.95,.95):
            start=Vector((x,y+1.20,z+dz));end=wall_at(*start,hulls)
            arm=s.beam('Cassette wall support',start,end+Vector((0,.035,0)),.24,.28,'s_pipe')
            arm['wall_attachment']=True
            support_contacts(arm,start,end+Vector((0,.035,0)),obj('Isolated cassette cradle'+suffix(i)).name,LAST_WALL)
            plate=s.box('Cassette anchor shoe',(end.x,end.y-.015,end.z),(.62,.10,.64),'s_paint',.035)
            plate['wall_attachment']=True

    # Independent cable lanes, real module plugs, separate junction sockets.
    junction=s.box('Electronics junction',(-177.05,-27.15,32.8),(.92,.72,1.08),'s_dark',.08)
    for i in range(3):
        port=obj('Cassette sealed plug'+suffix(i));p=point(port)
        level=32.42+i*.29
        inlet=cylinder('Junction inlet '+str(i+1),(-177.05,-27.56,level),.13,.23,'s_connector',(0,1,0))
        start=p+Vector((0,0,-.07))
        route('Cassette connected cable '+str(i+1),[start,(p.x,-27.88,p.z-.20),(p.x,-27.88,level),
              (-177.05,-27.88,level),(-177.05,-27.54,level)],.072,port,inlet)
    signalout=cylinder('Junction rear gland',(-177.05,-26.75,32.8),.17,.25,'s_metal',(0,1,0))
    wall=wall_at(-177.05,-26.65,32.8,hulls);socket=bulkhead('Electronics hull entry',wall,.32)
    route('Junction hull cable',[(-177.05,-26.71,32.8),(-177.05,wall.y-.26,32.8)],.085,signalout,socket)

    # Cylinders retain their surface detail but have clear space around their outlet fittings.
    cpos=[]
    for i,x in enumerate(oldcan):
        c=point(obj('Vertical service cylinder'+suffix(i)));cpos.append(c)
        shoe=obj('Manifold mounting shoe'+suffix(i))
        for dx in (-1.55,1.55):
            for dz in (-1.7,1.7):
                start=Vector((c.x+dx,c.y+.94,c.z+dz));end=wall_at(*start,hulls)
                arm=s.beam('Equipment rear support',start,end+Vector((0,.03,0)),.20,.24,'s_pipe');arm['wall_attachment']=True
                support_contacts(arm,start,end+Vector((0,.03,0)),shoe.name,LAST_WALL)
                plate=s.box('Equipment wall pad',(end.x,end.y-.015,end.z),(.42,.10,.50),'s_paint',.025);plate['wall_attachment']=True
    # Narrow guard lies between instrument panels; attach it to the two carrier shoes.
    for i,x in enumerate((-167.9,-165.7)):
        c=cpos[i]
        start=(x,-27.55,34.3);end=(x,c.y+.56,34.3)
        arm=s.beam('Guard support to carrier',start,end,.20,.23,'s_dark')
        support_contacts(arm,start,end,obj('Removable equipment shield').name,obj('Manifold mounting shoe'+suffix(i)).name)
        s.box('Guard carrier fastener',end,(.34,.14,.36),'s_metal',.025)

    # Supply manifold has an actual wall inlet and a removable blind cap at the far end.
    wp=wall_at(-171.8,-21.5,40.4,hulls);supplyport=bulkhead('Supply bulkhead',wp,.42)
    mainpoints=[(-171.8,wp.y-.25,40.4),(-171.8,-21.5,40.4),(-170,-21.5,40.4),
                (-163,-20.6,40.4),(-158.8,-19.0,37.8),(-155.5,-18.4,36.7)]
    tangent=(Vector(mainpoints[-1])-Vector(mainpoints[-2])).normalized()
    cap=cylinder('Supply removable blind cap',mainpoints[-1],.34,.24,'s_metal',tangent)
    supply=route('Upper supply manifold',mainpoints,.22,supplyport,cap)
    for i,c in enumerate(cpos):
        upper=40.4 if i<2 else 37.8
        uy=-21.5+(c.x+170)*.9/7 if i<2 else -19
        end=Vector((c.x,uy,upper))
        fitting=cylinder('Supply branch tee '+str(i+1),end,.30,.62,'s_paint',(1,.9/7,0) if i<2 else (1,.3,-.6))
        bottom=obj('Canister top coupling'+suffix(i));p=point(bottom)
        route('Cylinder supply '+str(i+1),[p,(p.x,p.y,p.z+.54),(p.x,p.y+.35,p.z+.84),
               (p.x,p.y+.35,upper-.55),end],.18,bottom,fitting)
        fitting['mate_manifold']=supply.name

    # One return header; each cylinder uses a separate tee, and the header enters a wall fitting.
    rpoints=[(-170.7,-26.55,31.9),(-165,-25.2,31.9),(-159,-22.9,30.45),(-156.4,-21.5,30.45)]
    rw=wall_at(-156.4,-21.5,30.45,hulls);rport=bulkhead('Return bulkhead',rw,.40)
    rpoints.append((-156.4,rw.y-.25,30.45))
    rcap=cylinder('Return header blind cap',rpoints[0],.26,.20,'s_metal',(1,.237,0))
    mainreturn=route('Lower return manifold',rpoints,.16,rcap,rport)
    for i,c in enumerate(cpos):
        segment=next((a,b) for a,b in zip(rpoints,rpoints[1:]) if a[0]<=c.x<=b[0] and b[0]>a[0])
        a,b=map(Vector,segment);t=(c.x-a.x)/(b.x-a.x);end=a.lerp(b,t)
        tee=cylinder('Return branch tee '+str(i+1),end,.23,.48,'s_metal',b-a);tee['mate_manifold']=mainreturn.name
        outlet=obj('Canister bottom coupling'+suffix(i));p=point(outlet)
        route('Cylinder return '+str(i+1),[p,(p.x,p.y,p.z-.28),(p.x,p.y,end.z),end],.10,outlet,tee)
    # Fixed clamps are behind the two headers, not in front of inspection ports.
    for name,points in (('Supply',mainpoints[2:4]),('Return',rpoints[1:3])):
        for p in points:
            q=Vector(p);end=wall_at(q.x,q.y+.35,q.z,hulls)
            support=s.beam(name+' manifold wall support',(q.x,q.y+.10,q.z),end+Vector((0,.02,0)),.16,.18,'s_pipe')
            support['wall_attachment']=True
            support_contacts(support,(q.x,q.y+.10,q.z),end+Vector((0,.02,0)),supply.name if name=='Supply' else mainreturn.name,LAST_WALL)
    # Add one orthographic-facing perspective for assembly review; existing cameras remain exact.
    base.camera('side05_front',(-172,-126,37.2),(-172,-24,35.8),lens=66)
    bpy.context.view_layer.update()
    # The added camera is excluded from the unchanged-source comparison.
    newcam=bpy.data.objects['side05_front'];newcam.name=PREFIX+'front inspection camera'
    after=f.protected();before_cameras=protected['cameras'];after['cameras'].pop(newcam.name,None)
    assert after==protected,'Prior content changed'
    newcam.name='side05_front'
    scene=bpy.context.scene;scene.name='KUHAI — Port assembly repair 05';scene['revision']='side-assembly-05'
    scene['assembly_routes']=json.dumps(ROUTES);scene.camera=bpy.data.objects['side03_context']
    output.parent.mkdir(parents=True,exist_ok=True)
    for img in bpy.data.images:
        if img.type=='IMAGE' and img.users:
            assert img.packed_file
            p=output.parent/'textures'/Path(img.filepath).name;p.parent.mkdir(exist_ok=True)
            p.write_bytes(img.packed_file.data);img.filepath='//textures/'+p.name
            for packed in img.packed_files:packed.filepath=img.filepath
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(output.resolve()),compress=True,relative_remap=False)
    output.with_suffix('.json').write_text(json.dumps({'source_sha256':sha(output),'input_sha256':EXPECTED,
        'routes':ROUTES,'cassette_centers':newcs,'canister_centers':[list(p) for p in cpos]},indent=2)+'\n')
    assert sha(source)==EXPECTED
    print('SAVED',sha(output),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    build(a.source,a.output)
