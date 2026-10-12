"""Add editable, local armor panels to form-study-03; input and rooms stay intact.

All added geometry is original and grouped for reversible comparisons. CPU is
the default. No network, implicit GPU selection, or changes to published sites.
"""
import argparse
import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import build_scene as base
from form_study import contract
from integration_study import archive_fingerprint
from render_study import peak_process_rss_mib, select_device

CONFIG = json.loads((ROOT / "surface-study-02.json").read_text())
HULL = "SURFACE02_HULL"
ROOM = "SURFACE02_ARCHIVE"
PREFIX = "SURFACE02 / "
RNG = random.Random(CONFIG["seed"])


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clip(poly, axis, boundary, greater):
    result = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        ain = a[axis] >= boundary if greater else a[axis] <= boundary
        bin = b[axis] >= boundary if greater else b[axis] <= boundary
        if ain:
            result.append(a)
        if ain != bin:
            result.append(a.lerp(b, (boundary - a[axis]) / (b[axis] - a[axis])))
    return result


def surface_material(name, tint, roughness):
    mat = base.material(name, tint, 0, roughness)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    geometry = nodes.new("ShaderNodeNewGeometry")
    macro = nodes.new("ShaderNodeTexNoise")
    macro.inputs["Scale"].default_value = .24
    macro.inputs["Detail"].default_value = 3
    links.new(geometry.outputs["Position"], macro.inputs["Vector"])
    tone = nodes.new("ShaderNodeValToRGB")
    tone.color_ramp.elements[0].color = tuple(c * .92 for c in tint) + (1,)
    tone.color_ramp.elements[1].color = tuple(c * 1.06 for c in tint) + (1,)
    links.new(macro.outputs["Fac"], tone.inputs["Fac"])
    links.new(tone.outputs["Color"], shader.inputs["Base Color"])
    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = roughness - .055
    rough.inputs["To Max"].default_value = roughness + .055
    links.new(macro.outputs["Fac"], rough.inputs["Value"])
    links.new(rough.outputs["Result"], shader.inputs["Roughness"])
    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 110
    grain.inputs["Detail"].default_value = 2
    links.new(geometry.outputs["Position"], grain.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .17
    bump.inputs["Distance"].default_value = .0007
    links.new(grain.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    mat["scale_note"] = "World meters: restrained tint/roughness variation; 0.7 mm microheight"
    return mat


def new_object(name, vertices, faces, group, material, edge=.07):
    mesh = bpy.data.meshes.new(PREFIX + name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(mesh.name, mesh)
    bpy.data.collections[group].objects.link(obj)
    mesh.materials.append(bpy.data.materials[material])
    obj["role"] = "archive_shell" if group == ROOM else "hull"
    obj["study_revision"] = CONFIG["revision"]
    if group == ROOM:
        obj["room_id"] = "archive"
    base.bevel(obj, edge, 3)
    return obj


def panel(poly, normal, group, name, material, thickness=None, lift=None):
    center = sum(poly, Vector()) / len(poly)
    inset = CONFIG["panel_inset_ratio"]
    poly = [center + (p - center) * (1 - inset) for p in poly]
    if (poly[1] - poly[0]).cross(poly[2] - poly[0]).dot(normal) < 0:
        poly.reverse()
    lift = CONFIG["plate_lift_m"] if lift is None else lift
    thickness = CONFIG["plate_thickness_m"] if thickness is None else thickness
    n = len(poly)
    vertices = [p + normal * h for h in (lift, lift + thickness) for p in poly]
    faces = [tuple(reversed(range(n))), tuple(range(n, 2*n))]
    faces += [(i, (i+1)%n, (i+1)%n+n, i+n) for i in range(n)]
    ob = new_object(name, vertices, faces, group, material, min(.07, thickness * .22))
    ob["surface_normal"] = list(normal)
    return ob


def populate(host, group, step_x, step_y, zone):
    count = 0
    for face in host.data.polygons:
        normal = (host.matrix_world.to_3x3() @ face.normal).normalized()
        if normal.z < (.75 if zone == "bow" else .99):
            continue
        poly = [host.matrix_world @ host.data.vertices[v].co for v in face.vertices]
        if zone == "bow":
            for axis, bound, greater in ((0,-251,True),(0,-215,False),(1,-12,True),(1,12,False)):
                poly = clip(poly, axis, bound, greater) if poly else []
        if len(poly) < 3:
            continue
        xmin, xmax = min(p.x for p in poly), max(p.x for p in poly)
        ymin, ymax = min(p.y for p in poly), max(p.y for p in poly)
        for ix in range(math.floor(xmin / step_x), math.ceil(xmax / step_x)):
            for iy in range(math.floor(ymin / step_y), math.ceil(ymax / step_y)):
                part = poly[:]
                for axis, bound, greater in ((0,ix*step_x,True),(0,(ix+1)*step_x,False),
                                             (1,iy*step_y,True),(1,(iy+1)*step_y,False)):
                    part = clip(part, axis, bound, greater) if part else []
                if len(part) < 3:
                    continue
                center = sum(part, Vector()) / len(part)
                area = sum((part[i] - part[0]).cross(part[i+1] - part[0]).length / 2 for i in range(1,len(part)-1))
                if area < 12:
                    continue
                # Keep plates clear of existing turret mount and roof-lock envelopes.
                if zone == "shoulder" and abs(center.x + 211) < 7 and abs(abs(center.y) - 56) < 7:
                    continue
                if zone == "archive" and any(abs(center.x - x) < 6 and abs(center.y + 38) < 8 for x in (-103,-60)):
                    continue
                variant = RNG.choices([0,1,2], weights=[7,2,1])[0]
                obj = panel(part, normal, group, f"{zone} armor panel {count:02d}", f"SURFACE02_paint_{variant}")
                obj["host_object"] = host.name
                count += 1
    return count


def box(name, loc, dims, material, edge=.03):
    obj = base.box(PREFIX + name, loc, dims, material, ROOM, edge, "archive_shell")
    obj["study_revision"] = CONFIG["revision"]
    return obj


def maintenance():
    # A real, 4 x 3.2 m panel becomes the web-material sample. Its original
    # geometry and world-space shading are used for the bake, not a new plane.
    box("Hatch dark gasket", (-80,-39,29.66), (4.5,3.7,.12), "STUDY_graphite")
    hatch = box("Archive maintenance cover", (-80,-39,29.79), (4,3.2,.20), "SURFACE02_paint_2", .045)
    hatch["web_bake_sample"] = True
    for x in (-81.45,-78.55):
        for y in (-40.1,-37.9):
            box("Recessed fastener pocket", (x,y,29.903), (.43,.38,.026), "STUDY_graphite", .025)
            base.cylinder(PREFIX + "Captive fastener", (x,y,29.934), .13, .055, "STUDY_alloy", "Z", ROOM, "archive_shell", 12)
    for x in (-81.25,-78.75):
        box("Latch pocket", (x,-39,29.91), (.55,1.2,.025), "STUDY_graphite")
        box("Latch exposed contact", (x,-39,29.96), (.14,.82,.08), "STUDY_alloy", .02)
    box("Hatch direction stripe", (-80,-38.1,29.903), (1.2,.16,.006), "STUDY_ochre_paint", .002)
    # Short service grille stays with the removable roof during cutaway.
    box("Service grille backing", (-91,-43,29.68), (5.2,3.4,.16), "STUDY_graphite")
    for index in range(8):
        box("Service grille louver", (-93+index*.55,-43,29.90), (.24,2.9,.22), "SURFACE02_paint_1", .04)
    # Project-owned serial markings; not official ship typography or labels.
    data = bpy.data.curves.new(PREFIX + "Service identifier", "FONT")
    data.body = "AR / 01"
    data.size = 1.05
    data.extrude = .001
    obj = bpy.data.objects.new(data.name, data)
    bpy.data.collections[ROOM].objects.link(obj)
    obj.location = (-83,-35,29.615)
    obj.data.materials.append(bpy.data.materials["SURFACE02_stencil"])
    obj["role"], obj["room_id"] = "archive_shell", "archive"


def build(args):
    if checksum(args.scene) != CONFIG["input_sha256"]:
        raise SystemExit("Input fingerprint differs from unchanged form-study-03")
    target = args.output.resolve() / "flagship-surface-study-02.blend"
    if target.exists() and not args.overwrite:
        raise SystemExit("Output exists; choose another directory")
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    scene = bpy.context.scene
    archive_before, contract_before = archive_fingerprint(), contract()
    base.COLLECTIONS.clear()
    base.COLLECTIONS.update({c.name:c for c in bpy.data.collections})
    base.MATERIALS.clear()
    base.MATERIALS.update({m.name:m for m in bpy.data.materials})
    for name, parent in ((HULL, scene.collection), (ROOM, bpy.data.collections["ARCHIVE_SHELL"])):
        collection = bpy.data.collections.new(name)
        parent.children.link(collection)
        base.COLLECTIONS[name] = collection
    for i,(color,rough) in enumerate((((.052,.069,.071),.47),((.067,.085,.086),.49),((.088,.103,.099),.43))):
        surface_material(f"SURFACE02_paint_{i}", color, rough)
    base.material("SURFACE02_stencil", (.29,.30,.245), 0, .58)
    bpy.context.view_layer.update()
    counts = {}
    for obj in list(bpy.data.collections["SHIP_HULL"].objects):
        if obj.name == "FORM03 / Prow upper wedge":
            counts[obj.name] = populate(obj, HULL, 9, 12, "bow")
        elif obj.name.startswith("FORM03 / Forward root armor island"):
            counts[obj.name] = populate(obj, HULL, 15, 11, "shoulder")
    host = bpy.data.objects["FORM03 / Port bay removable fitted roof"]
    counts[host.name] = populate(host, ROOM, 14, 12, "archive")
    maintenance()
    for name, cfg in CONFIG["cameras"].items():
        camera = base.camera(name, cfg["position"], cfg["target"], lens=cfg["lens"])
        camera.data.clip_end = 100000000
    bpy.context.view_layer.update()
    assert archive_fingerprint() == archive_before
    assert contract() == contract_before
    scene["surface_archive_fingerprint"] = archive_before
    scene["surface_preserved_contract"] = contract_before
    scene["revision"] = CONFIG["revision"]
    scene.name = "KUHAI — Local Armor Surface Study 02"
    scene.camera = bpy.data.objects["surface_archive"]
    scene.render.filepath = "//renders/surface_archive.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    for image in bpy.data.images:
        if image.type == "IMAGE" and image.packed_file and image.users:
            path = target.parent / "textures" / Path(image.filepath).name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(image.packed_file.data)
            image.filepath = "//textures/" + path.name
            for packed in image.packed_files:
                packed.filepath = image.filepath
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(target), compress=True, relative_remap=False)
    assert checksum(args.scene) == CONFIG["input_sha256"]
    report = {**CONFIG, "source_sha256": checksum(target), "source_bytes": target.stat().st_size,
              "input_unchanged": True, "archive_unchanged": True, "environment_unchanged": True,
              "panel_counts": counts, "new_objects": sum(len(bpy.data.collections[n].objects) for n in (HULL,ROOM)),
              "archive_details_follow_cutaway": bpy.data.collections[ROOM].name in bpy.data.collections["ARCHIVE_SHELL"].children,
              "blender": bpy.app.version_string, "gpu_used": False}
    (target.parent / "surface-manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


def render(args):
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    scene = bpy.context.scene
    for name in (HULL,ROOM):
        bpy.data.collections[name].hide_render = args.baseline
    if args.cutaway:
        bpy.data.collections["ARCHIVE_SHELL"].hide_render = True
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.resolution_percentage = 100
    scene.render.threads_mode, scene.render.threads = "FIXED", 6
    scene.cycles.samples, scene.cycles.use_adaptive_sampling = args.samples, False
    devices = select_device(scene, args.device)
    args.output.mkdir(parents=True,exist_ok=True)
    report = {"revision":CONFIG["revision"],"baseline":args.baseline,"cutaway":args.cutaway,
              "source_sha256":checksum(args.scene),"device":args.device,"devices":devices,
              "width":args.width,"height":args.height,"samples":args.samples,"threads":6,"renders":[]}
    for view in args.views.split(","):
        if view not in bpy.data.objects or bpy.data.objects[view].type != "CAMERA":
            raise SystemExit("Unknown view: " + view)
        path = args.output.resolve() / (view + ".png")
        if path.exists() and not args.overwrite:
            raise SystemExit("Render already exists")
        scene.camera = bpy.data.objects[view]
        scene.render.filepath = str(path)
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        report["renders"].append({"view":view,"seconds":round(time.perf_counter()-start,3),
                                  "peak_process_rss_mib":peak_process_rss_mib()})
        (args.output / "benchmark.json").write_text(json.dumps(report,indent=2)+"\n")
        print("SURFACE_RENDER " + json.dumps(report["renders"][-1]),flush=True)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command",required=True)
    for command in ("build","render"):
        p = sub.add_parser(command)
        p.add_argument("--scene",type=Path,required=True)
        p.add_argument("--output",type=Path,required=True)
        p.add_argument("--overwrite",action="store_true")
        if command == "render":
            p.add_argument("--views",default="surface_bow,surface_shoulder,surface_archive,surface_hatch")
            p.add_argument("--width",type=int,default=960)
            p.add_argument("--height",type=int,default=600)
            p.add_argument("--samples",type=int,default=32)
            p.add_argument("--baseline",action="store_true")
            p.add_argument("--cutaway",action="store_true")
            p.add_argument("--device",choices=("cpu","optix"),default="cpu")
    a = parser.parse_args(argv)
    if a.command == "render" and not (64<=a.width<=4096 and 64<=a.height<=4096 and 1<=a.samples<=1024):
        raise SystemExit("Invalid bounded preview settings")
    build(a) if a.command == "build" else render(a)
