"""Build/render a portable local material study on blockout-02 shoulder geometry.

python material_study.py build --output ./material-output --roughness-texture image.jpg
python material_study.py render --scene material-output/shoulder-material-study.blend
Desktop Blender: blender -b --python-exit-code 1 --python material_study.py -- <command> ...
CPU by default. No network, automatic GPU use, or overwrite of the base model.
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
from render_study import peak_process_rss_mib, select_device

CONFIG = json.loads((ROOT / "material-study.json").read_text(encoding="utf-8"))
RNG = random.Random(71)
GROUP = "MATERIAL_DETAILS"


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--roughness-texture", type=Path, required=True)
    build.add_argument("--overwrite", action="store_true")
    render = sub.add_parser("render")
    render.add_argument("--scene", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--views", default="shoulder,engine,armor")
    render.add_argument("--baseline", action="store_true")
    render.add_argument("--width", type=int, default=960)
    render.add_argument("--height", type=int, default=600)
    render.add_argument("--samples", type=int, default=32)
    render.add_argument("--device", choices=("cpu", "optix"), default="cpu")
    render.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def math_node(nodes, op, value=None):
    n = nodes.new("ShaderNodeMath")
    n.operation = op
    if value is not None:
        n.inputs[1].default_value = value
    return n


def surface(name, color, metal, rough_min, rough_max, texture=None, grain=.0015):
    mat = base.material(name, color, metal, (rough_min + rough_max) / 2)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    # Ordinary opaque paint is a dielectric; exposed alloy is a separate material.
    bsdf.inputs["Coat Weight"].default_value = 0
    coord = nodes.new("ShaderNodeTexCoord")
    macro = nodes.new("ShaderNodeTexNoise")
    macro.inputs["Scale"].default_value = .32
    macro.inputs["Detail"].default_value = 2
    links.new(coord.outputs["Object"], macro.inputs["Vector"])
    tint = nodes.new("ShaderNodeValToRGB")
    tint.color_ramp.elements[0].color = tuple(v * .94 for v in color) + (1,)
    tint.color_ramp.elements[1].color = tuple(v * 1.04 for v in color) + (1,)
    links.new(macro.outputs["Fac"], tint.inputs["Fac"])
    links.new(tint.outputs["Color"], bsdf.inputs["Base Color"])
    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = rough_min
    rough.inputs["To Max"].default_value = rough_max
    links.new(macro.outputs["Fac"], rough.inputs["Value"])
    if texture:
        scale = nodes.new("ShaderNodeVectorMath")
        scale.operation = "SCALE"
        scale.inputs[3].default_value = 1 / CONFIG["roughness_asset"]["tile_width_m"]
        links.new(coord.outputs["Object"], scale.inputs[0])
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = texture
        tex.projection = "BOX"
        tex.projection_blend = .2
        links.new(scale.outputs["Vector"], tex.inputs["Vector"])
        spread = nodes.new("ShaderNodeMapRange")
        spread.inputs["To Min"].default_value = -.065
        spread.inputs["To Max"].default_value = .065
        links.new(tex.outputs["Color"], spread.inputs["Value"])
        add = math_node(nodes, "ADD")
        links.new(rough.outputs["Result"], add.inputs[0])
        links.new(spread.outputs["Result"], add.inputs[1])
        links.new(add.outputs[0], bsdf.inputs["Roughness"])
    else:
        links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    fine = nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 7
    fine.inputs["Detail"].default_value = 2
    links.new(coord.outputs["Object"], fine.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .23
    bump.inputs["Distance"].default_value = grain
    links.new(fine.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    mat["study_surface"] = name
    return mat


def materials(texture):
    surface("STUDY_naval_paint", (.043, .062, .067), 0, .40, .55, texture)
    surface("STUDY_light_paint", (.094, .115, .115), 0, .39, .53, texture)
    surface("STUDY_alloy", (.27, .31, .33), 1, .32, .43, grain=.0005)
    surface("STUDY_graphite", (.018, .024, .025), 0, .55, .70, grain=.001)
    surface("STUDY_hot_liner", (.19, .083, .038), 1, .34, .53, grain=.002)
    surface("STUDY_ochre_paint", (.29, .15, .045), 0, .45, .6, texture)
    base.material("STUDY_amber", (1, .34, .06), 0, .3, 2.4)
    base.material("STUDY_cool", (.08, .45, .8), 0, .25, 2.8)
    mat = base.material("STUDY_plasma", (.055, .38, .7), 0, .3, 4)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    coord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 8
    noise.inputs["Detail"].default_value = 3
    links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = .28
    ramp.color_ramp.elements[0].color = (.009, .034, .075, 1)
    ramp.color_ramp.elements[1].position = .72
    ramp.color_ramp.elements[1].color = (.35, .78, 1, 1)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], nodes.get("Principled BSDF").inputs["Emission Color"])


def box(name, loc, dims, mat, edge=.12):
    return base.box(name, loc, dims, mat, GROUP, edge, "material_study")


def cylinder(name, loc, radius, depth, mat, axis="X", vertices=48):
    obj = base.cylinder(name, loc, radius, depth, mat, axis, GROUP, "material_study", vertices)
    if vertices >= 24:
        for face in obj.data.polygons:
            face.use_smooth = len(face.vertices) == 4
    return obj


def ring(name, loc, radius, tube, mat):
    return base.torus(name, loc, radius, tube, mat, "X", GROUP)


def sleeve(name, y, z, profile, mat, sides=72, start=0, end=math.tau):
    # Each profile point is (x, outer_radius, inner_radius). Sector ends are
    # capped as well as the front/back annulus. Recesses are true open cavities.
    full = abs(end - start - math.tau) < 1e-6
    count = sides if full else sides + 1
    verts = []
    for x, outer, inner in profile:
        for radius in (outer, inner):
            for j in range(count):
                a = start + (end - start) * j / sides
                verts.append((x, y + radius * math.cos(a), z + radius * math.sin(a)))
    faces = []
    stride = count * 2
    for k in range(len(profile) - 1):
        for j in range(sides):
            jj = (j + 1) % count
            a, b = k * stride, (k + 1) * stride
            faces.append((a + j, a + jj, b + jj, b + j))
            faces.append((a + count + jj, a + count + j, b + count + j, b + count + jj))
    for k in (0, len(profile) - 1):
        for j in range(sides):
            jj = (j + 1) % count
            a = k * stride
            f = (a + j, a + count + j, a + count + jj, a + jj)
            faces.append(tuple(reversed(f)) if k else f)
    if not full:
        for k in range(len(profile) - 1):
            a, b = k * stride, (k + 1) * stride
            faces.append((a, b, b + count, a + count))
            j = count - 1
            faces.append((a + j, a + count + j, b + count + j, b + j))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    if full:
        curved_faces = 2 * (len(profile) - 1) * sides
        for face in mesh.polygons:
            face.use_smooth = face.index < curved_faces
    obj = bpy.data.objects.new(name, mesh)
    base.COLLECTIONS[GROUP].objects.link(obj)
    mesh.materials.append(base.MATERIALS[mat])
    obj["role"] = "material_study"
    base.bevel(obj, .07 if full else .04, 2)
    return obj


def engine(y, z, radius):
    scale = radius / 24
    # Forebody terminates ahead of the luminous throat, so no solid cap can hide it.
    cylinder("Propulsion outer pressure body", (174, y, z), radius + 4 * scale, 58,
             "STUDY_naval_paint", vertices=24)
    sleeve("Thick nozzle shroud", y, z, [(201, radius * 1.15, radius * .71),
           (216, radius * 1.14, radius * .79), (229, radius * 1.02, radius * .84),
           (239, radius, radius * .84)], "STUDY_naval_paint")
    cylinder("Deep dark nozzle backing", (206, y, z), radius * .75, 1, "STUDY_graphite")
    cylinder("Recessed turbulent luminous throat", (208, y, z), radius * .72, .6, "STUDY_plasma", vertices=72)
    ring("Internal luminous collar", (215, y, z), radius * .69, radius * .023, "STUDY_cool")
    ring("Thin near-mouth running seal", (234, y, z), radius * .837, radius * .007, "STUDY_cool")
    for x, r in ((220, .76), (232, .82), (239, .92)):
        ring("Nozzle retaining lip", (x, y, z), radius * r, radius * .019, "STUDY_alloy")
    # Segmented thermal liner: small angular gaps reveal the deeper dark structure.
    for i in range(24):
        a = i * math.tau / 24 + .018
        sleeve("Replaceable thermal liner segment", y, z,
               [(217, radius * .85, radius * .78), (236, radius * .9, radius * .835)],
               "STUDY_hot_liner" if i % 3 else "STUDY_graphite", 3, a, a + math.tau / 24 - .036)
    for i in range(12):
        a = i * math.tau / 12
        yy, zz = y + radius * 1.08 * math.cos(a), z + radius * 1.08 * math.sin(a)
        obj = box("Nozzle external longitudinal stiffener", (216, yy, zz),
                  (29, radius * .09, radius * .045), "STUDY_naval_paint", .15 * scale)
        obj.rotation_euler[0] = a
        cylinder("Recessed shroud fastener", (231, yy, zz), .36 * scale, .32,
                 "STUDY_alloy", vertices=8)
    for x in (147, 171, 197):
        ring("Segmented casing collar", (x, y, z), radius * 1.13, .45 * scale, "STUDY_graphite")
    # A central refractory hub occludes part of the source and adds readable depth.
    cylinder("Central refractory hub", (216, y, z), radius * .18, 14, "STUDY_graphite")
    ring("Hub restrained luminous seal", (224, y, z), radius * .16, radius * .015, "STUDY_cool")
    for i in range(6):
        a = i * math.tau / 6
        rr = radius * .42
        obj = box("Internal radial support", (214, y + rr * math.cos(a), z + rr * math.sin(a)),
                  (5, radius * .47, radius * .035), "STUDY_hot_liner", .10 * scale)
        obj.rotation_euler[0] = a


def armor_details():
    # Face panels follow the source outboard wall. The bolts are 0.16 m across,
    # not metre-scale decorative rivets; most disappear at whole-ship distance.
    for x in (91, 118, 145, 172):
        for z in (-20, -3, 29):
            box("Painted removable side plate", (x, -152.4, z), (22, 1.3, 9),
                "STUDY_naval_paint" if (x + z) % 3 else "STUDY_light_paint", .22)
            for dx in (-9, 9):
                for dz in (-3.3, 3.3):
                    cylinder("Captive armor fastener", (x + dx, -153.12, z + dz), .08, .08,
                             "STUDY_alloy", "Y", vertices=8)
            # A few chips are limited to accessible lower/side edges, with gaps.
            for j in range(4):
                xx = x + RNG.uniform(-9, 9)
                box("Local maintenance edge abrasion", (xx, -153.08, z - 4.27),
                    (RNG.uniform(.18, .75), .035, RNG.uniform(.025, .07)), "STUDY_alloy", .006)
        box("Inset equipment junction", (x + 11.7, -153, 8), (1.7, 2, 10), "STUDY_graphite", .16)
        box("Junction inspection cover", (x + 11.7, -154.1, 8.2), (1.35, .25, 4), "STUDY_light_paint", .08)
    # Access recess and pipes are concentrated in one service section.
    box("Recess backing", (139, -154, -4), (14, 1, 10), "STUDY_graphite", .2)
    for z in (-7, -4, -1):
        cylinder("Protected service manifold", (139, -155.1, z), .32, 12, "STUDY_alloy", vertices=20)
    for x in (134, 144):
        box("Service manifold bracket", (x, -155.45, -4), (.6, 1.2, 8), "STUDY_naval_paint", .12)
    # Sparse hazard paint and built-in-font stencils act as scale clues.
    for x in (82, 85, 88):
        mark = box("Small caution marking", (x, -153.15, 28.5), (1.2, .05, 3.3), "STUDY_ochre_paint", .025)
        mark.rotation_euler[1] = -.25
    text = bpy.data.curves.new("Maintenance identification stencil", "FONT")
    text.body = "K-03"
    text.size = 2.6
    text.extrude = .004
    obj = bpy.data.objects.new(text.name, text)
    obj.location = (163, -153.13, 28)
    obj.rotation_euler[0] = math.pi / 2
    base.COLLECTIONS[GROUP].objects.link(obj)
    text.materials.append(base.MATERIALS["STUDY_ochre_paint"])


def build(a):
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    target = out / "shoulder-material-study.blend"
    if target.exists() and not a.overwrite:
        raise SystemExit("Scene exists; use a new output directory or --overwrite")
    if not a.roughness_texture.is_file():
        raise SystemExit("Supply the documented roughness image; this builder never downloads assets")
    scene = base.setup()
    scene.name = "KUHAI — Shoulder Material Study 01"
    scene["revision"] = CONFIG["revision"]
    scene["status"] = CONFIG["status"]
    base.hull()
    bpy.context.view_layer.update()
    for ob in list(base.COLLECTIONS["SHIP_HULL"].objects):
        center = sum((ob.matrix_world @ Vector(c) for c in ob.bound_box), Vector()) / 8
        if center.x < 25 or center.y > -40:
            bpy.data.objects.remove(ob, do_unlink=True)
    baseline = base.collection("BASELINE")
    for ob in list(base.COLLECTIONS["SHIP_HULL"].objects):
        copy = ob.copy()
        copy.name = "BASELINE / " + ob.name
        baseline.objects.link(copy)
    baseline.hide_render = baseline.hide_viewport = True
    base.collection(GROUP)
    texture = bpy.data.images.load(str(a.roughness_texture.resolve()), check_existing=False)
    texture.colorspace_settings.name = "Non-Color"
    texture.scale(CONFIG["roughness_asset"]["preview_size"], CONFIG["roughness_asset"]["preview_size"])
    texture.name = "Blue Metal Plate roughness 1024 - CC0"
    (out / "textures").mkdir(exist_ok=True)
    texture.filepath_raw = str(out / "textures/blue_metal_plate_rough_1k.png")
    texture.file_format = "PNG"
    texture.save()
    texture.pack()
    texture.filepath = "//textures/blue_metal_plate_rough_1k.png"
    materials(texture)
    replacement = {"armor": "STUDY_naval_paint", "paint": "STUDY_light_paint", "edge": "STUDY_alloy",
                   "dark": "STUDY_graphite", "amber": "STUDY_amber", "cyan": "STUDY_cool"}
    engines = ("Shoulder propulsion casing", "Propulsion casing retaining band", "Hollow nozzle shroud",
               "Recessed nozzle lip", "Engine luminous throat", "Engine center cone")
    for ob in list(base.COLLECTIONS["SHIP_HULL"].objects):
        if ob.name.startswith(engines):
            bpy.data.objects.remove(ob, do_unlink=True)
            continue
        # Baseline copies share mesh data, so copy it before assigning new materials.
        ob.data = ob.data.copy()
        for slot in ob.material_slots:
            if slot.material and slot.material.name in replacement:
                slot.material = base.MATERIALS[replacement[slot.material.name]]
    engine(-92, 30, 24)
    engine(-72, -13, 11)
    engine(-114, -13, 11)
    armor_details()
    base.light("Warm broad stellar key", "AREA", (80, -260, 280), (140, -100, 15), 850000, (1, .88, .73), 175)
    base.light("Cool reflected fill", "AREA", (380, -40, 155), (190, -90, 20), 450000, (.36, .57, 1), 150)
    base.light("Distant warm rim", "AREA", (60, 130, 180), (150, -100, 10), 1000000, (1, .51, .23), 100)
    for name, c in CONFIG["cameras"].items():
        base.camera(name, c["position"], c["target"], lens=c["lens"])
    scene.camera = bpy.data.objects["shoulder"]
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (.028, .04, .055, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = .18
    scene.render.resolution_x = CONFIG["preview"]["width"]
    scene.render.resolution_y = CONFIG["preview"]["height"]
    scene.cycles.samples = CONFIG["preview"]["samples"]
    scene.render.filepath = "//renders/shoulder.png"
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.clip_end = 5000
                area.spaces.active.region_3d.view_distance = 240
                area.spaces.active.region_3d.view_location = (150, -100, 15)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(target), compress=True)
    report = {**CONFIG, "blender": bpy.app.version_string,
              "source_texture_sha256": hashlib.sha256(a.roughness_texture.read_bytes()).hexdigest(),
              "source_texture_bytes": a.roughness_texture.stat().st_size,
              "packed_images": [i.name for i in bpy.data.images if i.packed_file],
              "objects": {name: len(base.COLLECTIONS[name].objects) for name in ("SHIP_HULL", GROUP, "BASELINE")},
              "render_file": target.name, "gpu_used": False}
    (out / "material-manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("MATERIAL_BUILD " + json.dumps(report, ensure_ascii=False), flush=True)


def render(a):
    if not (64 <= a.width <= 4096 and 64 <= a.height <= 4096 and 1 <= a.samples <= 1024):
        raise SystemExit("Invalid sample dimensions")
    views = a.views.split(",")
    if any(v not in CONFIG["cameras"] for v in views):
        raise SystemExit("Unknown view")
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not a.overwrite and any((out / (v + ".png")).exists() for v in views):
        raise SystemExit("Render exists; use a new directory or --overwrite")
    bpy.ops.wm.open_mainfile(filepath=str(a.scene.resolve()))
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = a.width, a.height
    scene.cycles.samples = a.samples
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.max_bounces = 4
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 6
    for name in ("SHIP_HULL", GROUP):
        bpy.data.collections[name].hide_render = bpy.data.collections[name].hide_viewport = a.baseline
    bpy.data.collections["BASELINE"].hide_render = bpy.data.collections["BASELINE"].hide_viewport = not a.baseline
    devices = select_device(scene, a.device)
    report = {"revision": CONFIG["revision"], "baseline": a.baseline, "devices": devices,
              "device": a.device, "width": a.width, "height": a.height, "samples": a.samples,
              "threads": 6, "denoise": True, "blender": bpy.app.version_string, "renders": [],
              "note": "Offline sample, not browser FPS or measured GPU memory"}
    for view in views:
        scene.camera = bpy.data.objects[view]
        scene.render.filepath = str(out / (view + ".png"))
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        report["renders"].append({"view": view, "seconds": round(time.perf_counter() - start, 3),
                                  "peak_process_rss_mib": peak_process_rss_mib()})
        (out / "benchmark.json").write_text(json.dumps(report, indent=2) + "\n")
        print("MATERIAL_RENDER " + json.dumps(report["renders"][-1]), flush=True)


if __name__ == "__main__":
    options = args()
    build(options) if options.command == "build" else render(options)
