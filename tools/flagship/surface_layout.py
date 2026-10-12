"""Refine local plate rhythm without changing source hardware or hull silhouettes.

Source-study-02 is immutable. Old panels remain in hidden comparison groups.
Renders default to CPU; projected pixel sizes are not browser performance tests.
"""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
import bmesh
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import build_scene as base
from form_study import contract, digest, object_record
from integration_study import archive_fingerprint
from render_study import peak_process_rss_mib, select_device
from surface_study import clip

CONFIG = json.loads((ROOT / "surface-study-03.json").read_text())
HULL, ROOF = "SURFACE03_HULL", "SURFACE03_ARCHIVE"
OLD_HULL, OLD_ROOF = "SURFACE03_PREVIOUS_HULL", "SURFACE03_PREVIOUS_ROOF"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_geometry(names=None):
    bpy.context.view_layer.update()
    objects = [bpy.data.objects[n] for n in names] if names else list(bpy.data.objects)
    return digest([object_record(o) for o in sorted(objects, key=lambda o:o.name)])


def area(poly):
    return sum((poly[i]-poly[0]).cross(poly[i+1]-poly[0]).length / 2 for i in range(1,len(poly)-1))


def clean(poly):
    points = []
    for p in poly:
        if not points or (p-points[-1]).length > 1e-5:
            points.append(p)
    if len(points)>2 and (points[-1]-points[0]).length < 1e-5:
        points.pop()
    return [p for i,p in enumerate(points)
            if (p-points[i-1]).cross(points[(i+1)%len(points)]-p).length > 1e-5]


def inset(poly, normal, distance):
    """Offset each convex edge in its actual face plane, using a meter distance."""
    origin = poly[0]
    u = (poly[1]-origin).normalized()
    v = normal.cross(u).normalized()
    points = [Vector(((p-origin).dot(u),(p-origin).dot(v))) for p in poly]
    if sum(a.x*b.y-b.x*a.y for a,b in zip(points,points[1:]+points[:1])) < 0:
        points.reverse()
    lines = []
    for a,b in zip(points,points[1:]+points[:1]):
        direction = b-a
        inward = Vector((-direction.y,direction.x)).normalized()
        lines.append((a+inward*distance,direction))
    result = []
    for i,(q,b) in enumerate(lines):
        p,a = lines[i-1]
        cross = a.x*b.y-a.y*b.x
        if abs(cross)<1e-8:
            raise ValueError("Degenerate offset edge")
        delta = q-p
        hit = p+a*((delta.x*b.y-delta.y*b.x)/cross)
        result.append(origin+u*hit.x+v*hit.y)
    if area(result)<1:
        raise ValueError("Inset collapsed a panel")
    return result


def add_panel(poly, normal, group, zone, index, host, material):
    poly = inset(clean(poly),normal,CONFIG["joint_width_m"]/2)
    if (poly[1]-poly[0]).cross(poly[2]-poly[0]).dot(normal)<0:
        poly.reverse()
    n = len(poly)
    lift,top = CONFIG["plate_lift_m"],CONFIG["plate_lift_m"]+CONFIG["plate_thickness_m"]
    verts = [p+normal*h for h in (lift,top) for p in poly]
    faces = [tuple(reversed(range(n))),tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    mesh = bpy.data.meshes.new(f"SURFACE03 / {zone} plate {index:02d}")
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    obj = bpy.data.objects.new(mesh.name,mesh)
    bpy.data.collections[group].objects.link(obj)
    mesh.materials.append(bpy.data.materials[material])
    obj["role"] = "archive_shell" if group==ROOF else "hull"
    if group==ROOF:
        obj["room_id"] = "archive"
    obj["host_object"],obj["study_revision"] = host.name,CONFIG["revision"]
    obj["joint_width_m"] = CONFIG["joint_width_m"]
    base.bevel(obj,CONFIG["bevel_m"],3)


def populate(host, regions, group, zone):
    count = 0
    for face in host.data.polygons:
        normal = (host.matrix_world.to_3x3()@face.normal).normalized()
        if normal.z < (.75 if zone=="bow" else .99):
            continue
        original = [host.matrix_world@host.data.vertices[i].co for i in face.vertices]
        for index,(xmin,xmax,ymin,ymax) in enumerate(regions):
            part = original[:]
            for axis,value,greater in ((0,xmin,True),(0,xmax,False),(1,ymin,True),(1,ymax,False)):
                part = clip(part,axis,value,greater) if part else []
            part = clean(part) if len(part)>=3 else []
            if len(part)<3 or area(part)<12:
                continue
            # A deliberately placed maintenance strip replaces random patchwork.
            variant = 1 if zone=="archive" and index==7 else 0
            add_panel(part,normal,group,zone,count,host,f"SURFACE02_paint_{variant}")
            count += 1
    return count


def build(args):
    if sha(args.scene)!=CONFIG["input_sha256"]:
        raise SystemExit("Expected the unchanged surface-study-02 input")
    target = args.output.resolve()/"flagship-surface-study-03.blend"
    if target.exists() and not args.overwrite:
        raise SystemExit("Output exists; choose another directory")
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    scene = bpy.context.scene
    original_names = list(bpy.data.objects.keys())
    geometry_before = source_geometry()
    room_before,environment_before = archive_fingerprint(),contract()
    for name,parent in ((HULL,scene.collection),(ROOF,bpy.data.collections["ARCHIVE_SHELL"]),
                        (OLD_HULL,scene.collection),(OLD_ROOF,bpy.data.collections["ARCHIVE_SHELL"])):
        group = bpy.data.collections.new(name)
        parent.children.link(group)
    old_count = 0
    for group,destination in (("SURFACE02_HULL",OLD_HULL),("SURFACE02_ARCHIVE",OLD_ROOF)):
        for obj in list(bpy.data.collections[group].objects):
            if " armor panel " in obj.name:
                bpy.data.collections[destination].objects.link(obj)
                bpy.data.collections[group].objects.unlink(obj)
                old_count += 1
    counts = {}
    bow_regions = [(a,b,c,d) for a,b in zip(CONFIG["bow_x"],CONFIG["bow_x"][1:])
                   for c,d in zip(CONFIG["bow_y"],CONFIG["bow_y"][1:])]
    counts["bow"] = populate(bpy.data.objects["FORM03 / Prow upper wedge"],bow_regions,HULL,"bow")
    for suffix,side in (("",-1),(".001",1)):
        regions = CONFIG["shoulder_regions_port"]
        if side==1:
            regions = [(x0,x1,-y1,-y0) for x0,x1,y0,y1 in regions]
        counts["port" if side==-1 else "starboard"] = populate(
            bpy.data.objects["FORM03 / Forward root armor island"+suffix],regions,HULL,"shoulder")
    counts["archive"] = populate(bpy.data.objects["FORM03 / Port bay removable fitted roof"],
                                  CONFIG["archive_regions"],ROOF,"archive")
    bpy.context.view_layer.update()
    assert source_geometry(original_names)==geometry_before
    assert archive_fingerprint()==room_before and contract()==environment_before
    for name in (OLD_HULL,OLD_ROOF):
        bpy.data.collections[name].hide_render = bpy.data.collections[name].hide_viewport = True
    scene["revision"] = CONFIG["revision"]
    scene["surface03_original_names"] = json.dumps(original_names)
    scene["surface03_source_geometry"] = geometry_before
    scene["surface03_room"] = room_before
    scene["surface03_environment"] = environment_before
    scene.name = "KUHAI — Plate Rhythm and Scale Study 03"
    scene.camera = bpy.data.objects["overview"]
    scene.render.filepath = "//previews/overview.png"
    target.parent.mkdir(parents=True,exist_ok=True)
    for image in bpy.data.images:
        if image.type=="IMAGE" and image.users and image.packed_file:
            path = target.parent/"textures"/Path(image.filepath).name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(image.packed_file.data)
            image.filepath = "//textures/"+path.name
            for packed in image.packed_files:
                packed.filepath = image.filepath
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(target),compress=True,relative_remap=False)
    assert sha(args.scene)==CONFIG["input_sha256"]
    record = {**CONFIG,"input_unchanged":True,"original_geometry_preserved":True,
              "original_panel_count":old_count,"new_panel_counts":counts,
              "new_panel_count":sum(counts.values()),"source_sha256":sha(target),
              "source_bytes":target.stat().st_size,"blender":bpy.app.version_string}
    (target.parent/"surface-manifest.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps(record,indent=2))


def compare(previous=False,cutaway=False):
    for names,visible in (((HULL,ROOF),not previous),((OLD_HULL,OLD_ROOF),previous)):
        for name in names:
            bpy.data.collections[name].hide_render = bpy.data.collections[name].hide_viewport = not visible
    bpy.data.collections["ARCHIVE_SHELL"].hide_render = cutaway
    bpy.context.view_layer.update()


def render(args):
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    scene = bpy.context.scene
    compare(args.previous,args.cutaway)
    hidden = []
    if args.far_detail_preview:
        prefixes = ("Captive fastener", "Recessed fastener pocket", "Latch pocket",
                    "Latch exposed contact", "Hatch direction stripe", "Service grille louver",
                    "Service identifier")
        for obj in bpy.data.collections["SURFACE02_ARCHIVE"].objects:
            if any(obj.name.startswith("SURFACE02 / "+p) for p in prefixes):
                obj.hide_render = True
                hidden.append(obj.name)
    scene.render.resolution_x,scene.render.resolution_y = args.width,args.height
    scene.render.resolution_percentage = 100
    scene.render.threads_mode,scene.render.threads = "FIXED",6
    scene.cycles.samples,scene.cycles.use_adaptive_sampling = args.samples,False
    devices = select_device(scene,args.device)
    args.output.mkdir(parents=True,exist_ok=True)
    record = {"revision":CONFIG["revision"],"previous":args.previous,"cutaway":args.cutaway,
              "source_sha256":sha(args.scene),"width":args.width,"height":args.height,
              "samples":args.samples,"threads":6,"device":args.device,"devices":devices,
              "far_detail_preview":args.far_detail_preview,"hidden_small_details":hidden,"renders":[]}
    for name in args.views.split(","):
        camera = bpy.data.objects.get(name)
        if camera is None or camera.type!="CAMERA":
            raise SystemExit("Unknown camera: "+name)
        path = args.output.resolve()/(name+".png")
        if path.exists() and not args.overwrite:
            raise SystemExit("Render already exists")
        scene.camera,scene.render.filepath = camera,str(path)
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        record["renders"].append({"view":name,"seconds":round(time.perf_counter()-start,3),
                                  "peak_process_rss_mib":peak_process_rss_mib()})
        (args.output/"benchmark.json").write_text(json.dumps(record,indent=2)+"\n")
        print("SURFACE03_RENDER "+json.dumps(record["renders"][-1]),flush=True)


def projected_bounds(obj,camera,scene,width,height):
    points = [world_to_camera_view(scene,camera,obj.matrix_world@Vector(p)) for p in obj.bound_box]
    return {"name":obj.name,"width_px":round((max(p.x for p in points)-min(p.x for p in points))*width,3),
            "height_px":round((max(p.y for p in points)-min(p.y for p in points))*height,3),
            "note":"Projected bounding box, not a count of visible or unoccluded pixels"}


def inspect(args):
    bpy.ops.wm.open_mainfile(filepath=str(args.baseline.resolve()))
    geometry,room,environment = source_geometry(),archive_fingerprint(),contract()
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    scene = bpy.context.scene
    checks = {"input_sha256":sha(args.baseline)==CONFIG["input_sha256"],
              "all_original_geometry_preserved":source_geometry(json.loads(scene["surface03_original_names"]))==geometry,
              "room_preserved":archive_fingerprint()==room,"environment_preserved":contract()==environment,
              "cutaway_owns_new_roof":ROOF in bpy.data.collections["ARCHIVE_SHELL"].children}
    issues,meshes = [],[]
    for group in (HULL,ROOF):
        for obj in bpy.data.collections[group].objects:
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            volume = bm.calc_volume(signed=True)
            valid = volume>0 and all(e.is_manifold for e in bm.edges) and all(math.isfinite(c) for v in bm.verts for c in v.co)
            bm.free()
            if not valid:
                issues.append(obj.name+": invalid mesh")
            evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            mesh.calc_loop_triangles()
            coords = [obj.matrix_world@v.co for v in mesh.vertices]
            bounds = [[min(v[i] for v in coords) for i in range(3)],[max(v[i] for v in coords) for i in range(3)]]
            if group==ROOF:
                if obj.get("role")!="archive_shell" or obj.get("room_id")!="archive":
                    issues.append(obj.name+": wrong ownership")
                if all(bounds[0][i]<(-61,-27,22.8)[i] and bounds[1][i]>(-99,-47,16.6)[i] for i in range(3)):
                    issues.append(obj.name+": occupied room intrusion")
            meshes.append({"name":obj.name,"triangles":len(mesh.loop_triangles),"volume_m3":round(volume,5)})
            evaluated.to_mesh_clear()
    images = []
    for image in bpy.data.images:
        if image.type=="IMAGE" and image.users:
            valid = image.filepath.startswith("//") and image.packed_file is not None and Path(bpy.path.abspath(image.filepath)).is_file()
            images.append({"name":image.name,"relative_path":image.filepath,"portable":valid})
            if not valid:
                issues.append(image.name+": missing portable resource")
    sizes = []
    feature_names = ["SURFACE02 / Archive maintenance cover","SURFACE02 / Captive fastener","SURFACE02 / Latch exposed contact"]
    for camera,width,height in (("overview",960,600),("overview",384,240),("surface_archive",960,600),("surface_hatch",960,600)):
        scene.render.resolution_x,scene.render.resolution_y = width,height
        scene.render.resolution_percentage = 100
        sizes.append({"camera":camera,"width":width,"height":height,
                      "features":[projected_bounds(bpy.data.objects[n],bpy.data.objects[camera],scene,width,height) for n in feature_names]})
    checks["new_geometry_and_resources_valid"] = not issues
    record = {"revision":CONFIG["revision"],"checks":checks,"issues":issues,"images":images,
              "new_panels":len(meshes),"new_panel_triangles":sum(m["triangles"] for m in meshes),
              "meshes":meshes,"projected_feature_sizes":sizes,"browser_performance_tested":False,
              "passed":all(checks.values())}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({k:v for k,v in record.items() if k!="meshes"},indent=2))
    if not record["passed"]:
        raise SystemExit(1)


if __name__=="__main__":
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command",required=True)
    for command in ("build","render","inspect"):
        s = sub.add_parser(command)
        s.add_argument("--scene",type=Path,required=True)
        s.add_argument("--output",type=Path,required=True)
        s.add_argument("--overwrite",action="store_true")
        if command=="inspect":
            s.add_argument("--baseline",type=Path,required=True)
        if command=="render":
            s.add_argument("--views",default="overview,form_close,surface_bow,surface_archive")
            s.add_argument("--width",type=int,default=960)
            s.add_argument("--height",type=int,default=600)
            s.add_argument("--samples",type=int,default=32)
            s.add_argument("--previous",action="store_true")
            s.add_argument("--cutaway",action="store_true")
            s.add_argument("--far-detail-preview",action="store_true",
                           help="Render-only omission of tiny hardware; keeps the editable source intact")
            s.add_argument("--device",choices=("cpu","optix"),default="cpu")
    a = p.parse_args(argv)
    if a.command=="render" and not (64<=a.width<=4096 and 64<=a.height<=4096 and 1<=a.samples<=1024):
        raise SystemExit("Invalid bounded preview settings")
    {"build":build,"render":render,"inspect":inspect}[a.command](a)
