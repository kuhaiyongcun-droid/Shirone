"""Add reversible engine roots and outer guards to the bridge-study-02 source.

CPU preview defaults; no downloads, physics simulation, or live-site changes.
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import build_scene as base
import material_study as forms
from bridge_study import fingerprint, sha
from form_study import contract
from integration_study import MATERIAL_MAP, archive_fingerprint
from render_study import peak_process_rss_mib, select_device

CONFIG = json.loads((ROOT / "stern-study-01.json").read_text())
GROUP = "STERN01_DETAILS"
PREFIX = "STERN01 / "


def mesh_object(name, vertices, faces, material, bevel=.08):
    mesh = bpy.data.meshes.new(PREFIX + name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(mesh.name, mesh)
    base.COLLECTIONS[GROUP].objects.link(obj)
    mesh.materials.append(base.MATERIALS[material])
    if bevel:
        base.bevel(obj, bevel, 2)
    return obj


def sleeve(name, y, z, profile, material, sides=72, start=0, end=math.tau):
    obj = forms.sleeve(PREFIX + name, y, z, profile, material, sides, start, end)
    # Partial sectors also need smooth curved walls, with flat boundary caps.
    curved = 2 * (len(profile)-1) * sides
    for face in obj.data.polygons:
        face.use_smooth = face.index < curved
    return obj


def saddle(y, x):
    side = -1 if y < 0 else 1
    # Upper points embed in the casing; the foot rests on the existing deck.
    polygon = [(23,15), (33,8), (39,8), (39,10), (30,13), (22,22)]
    vertices = [(xx, y+side*dy, 30+dz) for xx in (x-2.0, x+2.0) for dy,dz in polygon]
    count = len(polygon)
    faces = [tuple(reversed(range(count))), tuple(range(count,2*count))]
    faces += [(i,(i+1)%count,(i+1)%count+count,i+count) for i in range(count)]
    return mesh_object("Casing-to-deck saddle", vertices, faces, "armor", .15)


def tube(name, points, radius, material, sides=12):
    points = [Vector(p) for p in points]
    vertices = []
    for i, point in enumerate(points):
        tangent = (points[min(i+1,len(points)-1)]-points[max(i-1,0)]).normalized()
        u = tangent.cross(Vector((0,0,1))).normalized()
        v = tangent.cross(u).normalized()
        for j in range(sides):
            angle = j*math.tau/sides
            vertices.append(point+radius*(u*math.cos(angle)+v*math.sin(angle)))
    faces = [tuple(reversed(range(sides))),tuple(range((len(points)-1)*sides,len(points)*sides))]
    for i in range(len(points)-1):
        for j in range(sides):
            k = (j+1)%sides
            faces.append((i*sides+j,i*sides+k,(i+1)*sides+k,(i+1)*sides+j))
    obj = mesh_object(name, vertices, faces, material, 0)
    for face in obj.data.polygons:
        face.use_smooth = len(face.vertices) == 4
    return obj


def geometry():
    for y in CONFIG["main_centers_y"]:
        z, r = CONFIG["main_z"], CONFIG["main_radius"]
        for x in (181,198):
            saddle(y,x)
        # Two broad removable shoulders retain the original dorsal fairing.
        for start,end in ((.12,1.12),(2.02,3.02)):
            sleeve("Upper casing access cowl",y,z,
                   [(174,28.45,27.6),(179,29.15,27.8),(194,29.15,27.8),(200,28.45,27.2)],
                   "paint",16,start,end)
        # A capped top clearance avoids piercing the retained dorsal fairing.
        clearance=CONFIG["root_collar_top_clearance_rad"]
        sleeve("Root connection collar",y,z,[(200.3,28.8,26.7),(203,29.3,26.7),(207,28.3,26.5)],
               "alloy",72,math.pi/2+clearance,math.pi/2+math.tau-clearance)
        sleeve("Root separation band",y,z,[(208,28.25,26.8),(209.1,28.2,26.7)],"dark")
        # Twelve guard seams align with the existing twelve longitudinal ribs.
        # Replaceable external guards end before the original nozzle mouth.
        for i in range(CONFIG["guard_sectors"]):
            a=i*math.tau/CONFIG["guard_sectors"]+CONFIG["guard_gap_rad"]
            b=(i+1)*math.tau/CONFIG["guard_sectors"]-CONFIG["guard_gap_rad"]
            sleeve("Tapered outer nozzle guard",y,z,
                   [(210,28.05,27.2),(215,28.0,27.1),(225,26.1,25.0),(230,25.0,24.1)],
                   "armor",8,a,b)
        for angle in (.50, math.pi-.50):
            points=[(x,y+radius*math.cos(angle),z+radius*math.sin(angle))
                    for x,radius in ((177,29.2),(182,30.1),(194,30.1),(200,29.8),(204,29.2))]
            tube("Protected service conduit",points,.28,"alloy")
            for x in (185,194):
                obj=base.box(PREFIX+"Conduit retaining clip",
                    (x,y+29.8*math.cos(angle),z+29.8*math.sin(angle)),
                    (.65,1.1,1.15),"dark",GROUP,.06,"hull")
                obj.rotation_euler[0]=angle
        sleeve("Main aperture outer rim",y,z,[(238.4,24.22,20.35),(239.6,24.22,20.35)],"alloy")
    for y in CONFIG["small_centers_y"]:
        z,r=CONFIG["small_z"],CONFIG["small_radius"]
        sleeve("Auxiliary root collar",y,z,[(219.7,12.7,11.5),(222.2,12.45,11.4)],"dark",48)
        sleeve("Auxiliary aperture outer rim",y,z,[(238.7,r+.12,r*.849),(239.5,r+.12,r*.849)],"alloy",48)
    for obj in base.COLLECTIONS[GROUP].objects:
        obj["role"],obj["revision"]="hull",CONFIG["revision"]
        obj["design_status"]="Exterior interpretation; no engineering certification or canon claim"
        bm=bmesh.new();bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(obj.data);bm.free()


def build(args):
    if sha(args.scene)!=CONFIG["input_sha256"]:
        raise SystemExit("Unexpected bridge-study-02 source")
    target=args.output.resolve()/"flagship-stern-study-01.blend"
    if target.exists() and not args.overwrite:
        raise SystemExit("Output exists; choose another directory")
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    names=sorted(o.name for o in bpy.data.objects)
    before, room, environment=fingerprint(names),archive_fingerprint(),contract()
    base.COLLECTIONS.update({c.name:c for c in bpy.data.collections})
    base.collection(GROUP)
    base.MATERIALS.update({k:bpy.data.materials[v] for k,v in MATERIAL_MAP.items()})
    base.MATERIALS["alloy"]=bpy.data.materials["STUDY_alloy"]
    forms.GROUP=GROUP
    geometry()
    for name,camera in CONFIG["cameras"].items():
        obj=base.camera(name,camera["position"],camera["target"],lens=camera["lens"])
        obj.data.clip_end=100000000
    bpy.context.view_layer.update()
    if fingerprint(names)!=before or archive_fingerprint()!=room or contract()!=environment:
        raise RuntimeError("Original scene changed")
    scene=bpy.context.scene
    scene.name="KUHAI — Stern Connection Study 01"
    scene["revision"],scene["status"]=CONFIG["revision"],CONFIG["status"]
    scene.camera=bpy.data.objects["stern"]
    scene.render.filepath="//previews/stern.png"
    texture_dir=target.parent/"textures";texture_dir.mkdir(parents=True,exist_ok=True)
    for image in bpy.data.images:
        if image.type=="IMAGE" and image.users:
            if not image.packed_file:
                raise RuntimeError("Expected packed input image: "+image.name)
            name=Path(image.filepath).name
            (texture_dir/name).write_bytes(image.packed_file.data)
            image.filepath="//textures/"+name
            for packed in image.packed_files:packed.filepath=image.filepath
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(target),compress=True,relative_remap=False)
    record={**CONFIG,"source_sha256":sha(target),"source_bytes":target.stat().st_size,
            "new_objects":len(base.COLLECTIONS[GROUP].objects),"blender":bpy.app.version_string}
    (target.parent/"stern-manifest.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps(record,indent=2))


def render(args):
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    scene=bpy.context.scene
    bpy.data.collections[GROUP].hide_render=args.previous
    bpy.data.collections[GROUP].hide_viewport=args.previous
    scene.render.resolution_x,scene.render.resolution_y=args.width,args.height
    scene.render.resolution_percentage=100
    scene.render.threads_mode,scene.render.threads="FIXED",6
    scene.cycles.samples,scene.cycles.use_adaptive_sampling=args.samples,False
    devices=select_device(scene,args.device)
    args.output.mkdir(parents=True,exist_ok=True)
    record={"revision":CONFIG["revision"],"previous":args.previous,"source_sha256":sha(args.scene),
            "width":args.width,"height":args.height,"samples":args.samples,"device":args.device,
            "threads":6,"devices":devices,"renders":[]}
    for name in args.views.split(","):
        path=args.output.resolve()/(name+".png")
        if path.exists() and not args.overwrite:raise SystemExit("Render exists")
        camera=bpy.data.objects.get(name)
        if not camera or camera.type!="CAMERA":raise SystemExit("Unknown camera")
        scene.camera,scene.render.filepath=camera,str(path)
        start=time.perf_counter();bpy.ops.render.render(write_still=True)
        record["renders"].append({"view":name,"seconds":round(time.perf_counter()-start,3),"peak_process_rss_mib":peak_process_rss_mib()})
        (args.output/"benchmark.json").write_text(json.dumps(record,indent=2)+"\n")
        print("STERN_RENDER "+json.dumps(record["renders"][-1]),flush=True)


def inspect(args):
    if sha(args.baseline)!=CONFIG["input_sha256"]:raise SystemExit("Wrong baseline")
    bpy.ops.wm.open_mainfile(filepath=str(args.baseline.resolve()))
    names=sorted(o.name for o in bpy.data.objects)
    original, room, environment=fingerprint(names),archive_fingerprint(),contract()
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    checks={"original_objects_preserved":fingerprint(names)==original,"archive_preserved":archive_fingerprint()==room,
            "lighting_planet_and_original_cameras_preserved":contract()==environment,
            "new_details_visible":not bpy.data.collections[GROUP].hide_render}
    issues,meshes,images,vertices,faces=[],[],[],[],[]
    for obj in bpy.data.collections[GROUP].objects:
        evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh=evaluated.to_mesh();mesh.calc_loop_triangles()
        bm=bmesh.new();bm.from_mesh(mesh)
        volume=bm.calc_volume(signed=True)
        if volume<=0 or not all(e.is_manifold for e in bm.edges):issues.append(obj.name+": non-closed or negative volume")
        bm.free()
        coords=[obj.matrix_world@v.co for v in mesh.vertices]
        if not all(math.isfinite(component) for point in coords for component in point):issues.append(obj.name+": nonfinite mesh")
        if min(v.x for v in coords)<170:issues.append(obj.name+": outside aft study region")
        offset=len(vertices);vertices.extend(coords)
        faces.extend(tuple(offset+i for i in tri.vertices) for tri in mesh.loop_triangles)
        meshes.append({"name":obj.name,"triangles":len(mesh.loop_triangles),"volume_m3":round(volume,6)})
        evaluated.to_mesh_clear()
    bvh=BVHTree.FromPolygons(vertices,faces,all_triangles=True)
    rays=[]
    engines=[(y,30,24) for y in CONFIG["main_centers_y"]]+[(y,-13,11) for y in CONFIG["small_centers_y"]]
    for y,z,r in engines:
        for i in range(13):
            angle=(i-1)*math.tau/12
            radius=0 if i==0 else r*.75
            origin=Vector((255,y+radius*math.cos(angle),z+radius*math.sin(angle)))
            location,normal,index,distance=bvh.ray_cast(origin,Vector((-1,0,0)),54)
            rays.append({"engine_y":y,"sample":i,"clear_of_new_parts":location is None})
    checks["sampled_apertures_clear"]=all(r["clear_of_new_parts"] for r in rays)
    for img in bpy.data.images:
        if img.type=="IMAGE" and img.users:
            valid=img.filepath.startswith("//") and bool(img.packed_file) and Path(bpy.path.abspath(img.filepath)).is_file()
            images.append({"name":img.name,"path":img.filepath,"portable":valid})
            if not valid:issues.append(img.name+": missing resource")
    checks["new_meshes_and_resources_valid"]=not issues
    record={"revision":CONFIG["revision"],"checks":checks,"issues":issues,"images":images,"meshes":meshes,
            "new_objects":len(meshes),"new_evaluated_triangles":sum(m["triangles"] for m in meshes),
            "aperture_rays":rays,"aperture_scope":"New geometry only, 13 axial rays per nozzle; not an exhaust flow simulation",
            "browser_tested":False,"passed":all(checks.values())}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({k:v for k,v in record.items() if k not in ("meshes","aperture_rays")},indent=2))
    if not record["passed"]:raise SystemExit(1)


if __name__=="__main__":
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="command",required=True)
    for command in ("build","render","inspect"):
        s=sub.add_parser(command);s.add_argument("--scene",type=Path,required=True);s.add_argument("--output",type=Path,required=True)
        s.add_argument("--overwrite",action="store_true")
        if command=="inspect":s.add_argument("--baseline",type=Path,required=True)
        if command=="render":
            s.add_argument("--views",default="stern,stern_connection,stern_nozzle,overview")
            s.add_argument("--width",type=int,default=960);s.add_argument("--height",type=int,default=600)
            s.add_argument("--samples",type=int,default=32);s.add_argument("--previous",action="store_true")
            s.add_argument("--device",choices=("cpu","optix"),default="cpu")
    a=p.parse_args(argv)
    if a.command=="render" and not (64<=a.width<=4096 and 64<=a.height<=4096 and 1<=a.samples<=1024):raise SystemExit("Invalid preview size")
    {"build":build,"render":render,"inspect":inspect}[a.command](a)
