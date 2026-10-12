"""Combine saved structural/material studies into an editable orbital preview.

Build takes the two existing .blend files; no network or external add-ons.
Render defaults to CPU. The source stays separate from any website GLB.
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
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import build_scene as base
from render_study import peak_process_rss_mib, select_device

CONFIG = json.loads((ROOT / "integration-study.json").read_text(encoding="utf-8"))
SHIP_GROUPS = ("SHIP_HULL", "ARCHIVE_SHELL", "ARCHIVE_INTERIOR", "PORT_DETAILS", "STARBOARD_DETAILS")
OLD_ENGINES = ("Shoulder propulsion casing", "Propulsion casing retaining band", "Hollow nozzle shroud",
               "Recessed nozzle lip", "Engine luminous throat", "Engine center cone")
MATERIAL_MAP = {"armor": "STUDY_naval_paint", "paint": "STUDY_light_paint", "edge": "STUDY_alloy",
                "dark": "STUDY_graphite", "amber": "STUDY_amber", "cyan": "STUDY_cool",
                "stripe": "STUDY_ochre_paint"}


def options():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--base-scene", type=Path, required=True)
    build.add_argument("--material-scene", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--overwrite", action="store_true")
    render = sub.add_parser("render")
    render.add_argument("--scene", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--views", default="overview,stern,port,detail")
    render.add_argument("--width", type=int, default=960)
    render.add_argument("--height", type=int, default=600)
    render.add_argument("--samples", type=int, default=32)
    render.add_argument("--device", choices=("cpu", "optix"), default="cpu")
    render.add_argument("--baseline", action="store_true", help="Old ship in the SAME current environment")
    render.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive_fingerprint():
    records = []
    for ob in sorted(bpy.data.collections["ARCHIVE_INTERIOR"].objects, key=lambda o: o.name):
        records.append({"name": ob.name, "matrix": [list(r) for r in ob.matrix_world],
                        "vertices": [list(v.co) for v in ob.data.vertices] if ob.type == "MESH" else [],
                        "materials": [m.name for m in ob.data.materials]})
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()


def visible_collection(name, visible):
    coll = bpy.data.collections[name]
    coll.hide_render = coll.hide_viewport = not visible


def switch_comparison(baseline=False):
    # Visibility only. This does not change a ship, camera or planet transform.
    for name in SHIP_GROUPS:
        if name != "ARCHIVE_INTERIOR":
            visible_collection(name, not baseline)
    visible_collection("BASELINE_SHIP", baseline)


def node_math(nodes, operation, second=None):
    node = nodes.new("ShaderNodeMath")
    node.operation = operation
    if second is not None:
        node.inputs[1].default_value = second
    return node


def planet():
    p = CONFIG["planet"]
    mat = base.material("ORBIT_planet_surface", (.035, .085, .11), 0, .82)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    coord = nodes.new("ShaderNodeTexCoord")
    terrain = nodes.new("ShaderNodeTexNoise")
    terrain.inputs["Scale"].default_value = 4.2
    terrain.inputs["Detail"].default_value = 7
    terrain.inputs["Roughness"].default_value = .72
    links.new(coord.outputs["Generated"], terrain.inputs["Vector"])
    colors = nodes.new("ShaderNodeValToRGB")
    colors.color_ramp.elements.remove(colors.color_ramp.elements[1])
    for i, (position, color) in enumerate(((.31, (.011, .034, .050)), (.47, (.024, .075, .099)),
                                         (.51, (.105, .124, .117)), (.58, (.22, .20, .15)),
                                         (.72, (.33, .31, .25)))):
        e = colors.color_ramp.elements[0] if i == 0 else colors.color_ramp.elements.new(position)
        e.position, e.color = position, (*color, 1)
    links.new(terrain.outputs["Fac"], colors.inputs["Fac"])
    links.new(colors.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .10
    bump.inputs["Distance"].default_value = 2400
    links.new(terrain.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    sphere("Fictional planetary surface", p["radius_m"], mat)

    # Thin cloud shell is a surface preview, not volumetric weather simulation.
    cloud = base.material("ORBIT_clouds", (.43, .49, .52), 0, .95)
    nodes, links = cloud.node_tree.nodes, cloud.node_tree.links
    coord = nodes.new("ShaderNodeTexCoord")
    warp = nodes.new("ShaderNodeTexNoise")
    warp.inputs["Scale"].default_value = 5
    warp.inputs["Detail"].default_value = 4
    links.new(coord.outputs["Generated"], warp.inputs["Vector"])
    scale = nodes.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    scale.inputs[3].default_value = .20
    links.new(warp.outputs["Color"], scale.inputs[0])
    add = nodes.new("ShaderNodeVectorMath")
    add.operation = "ADD"
    links.new(scale.outputs["Vector"], add.inputs[0])
    links.new(coord.outputs["Generated"], add.inputs[1])
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 23
    noise.inputs["Detail"].default_value = 7
    noise.inputs["Roughness"].default_value = .75
    links.new(add.outputs["Vector"], noise.inputs["Vector"])
    mask = nodes.new("ShaderNodeMapRange")
    mask.inputs["From Min"].default_value = .49
    mask.inputs["From Max"].default_value = .67
    mask.inputs["To Max"].default_value = .86
    links.new(noise.outputs["Fac"], mask.inputs["Value"])
    clear = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(mask.outputs["Result"], mix.inputs[0])
    links.new(clear.outputs[0], mix.inputs[1])
    links.new(nodes.get("Principled BSDF").outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], nodes.get("Material Output").inputs[0])
    sphere("Procedural cloud shell", p["radius_m"] * 1.0025, cloud)

    # View-dependent limb, attenuated on the night side by the SAME stellar vector.
    # Deliberate art approximation; no Rayleigh/Mie integration or airglow claim.
    rim = base.material("ORBIT_atmosphere_preview", (.035, .23, .48), 0, 1)
    nodes, links = rim.node_tree.nodes, rim.node_tree.links
    layer = nodes.new("ShaderNodeLayerWeight")
    layer.inputs["Blend"].default_value = .3
    power = node_math(nodes, "POWER", 3)
    links.new(layer.outputs["Facing"], power.inputs[0])
    geom = nodes.new("ShaderNodeNewGeometry")
    dot = nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    dot.inputs[1].default_value = Vector(CONFIG["stellar_direction"]).normalized()
    radial = nodes.new("ShaderNodeVectorMath")
    radial.operation = "SUBTRACT"
    radial.inputs[1].default_value = p["center_m"]
    links.new(geom.outputs["Position"], radial.inputs[0])
    normalize = nodes.new("ShaderNodeVectorMath")
    normalize.operation = "NORMALIZE"
    links.new(radial.outputs["Vector"], normalize.inputs[0])
    links.new(normalize.outputs["Vector"], dot.inputs[0])
    daylight = nodes.new("ShaderNodeMapRange")
    daylight.inputs["From Min"].default_value = -.08
    daylight.inputs["From Max"].default_value = .3
    links.new(dot.outputs["Value"], daylight.inputs["Value"])
    factor = node_math(nodes, "MULTIPLY")
    links.new(power.outputs[0], factor.inputs[0])
    links.new(daylight.outputs["Result"], factor.inputs[1])
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (.024, .15, .38, 1)
    emission.inputs["Strength"].default_value = 1.4
    clear = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(factor.outputs[0], mix.inputs[0])
    links.new(clear.outputs[0], mix.inputs[1])
    links.new(emission.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], nodes.get("Material Output").inputs[0])
    obj = sphere("Thin lit-limb preview shell", p["radius_m"] * 1.008, rim)
    obj.visible_shadow = False
    obj.visible_diffuse = False
    obj.visible_glossy = False
    obj["stellar_direction"] = list(Vector(CONFIG["stellar_direction"]).normalized())


def sphere(name, radius, material):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=192, ring_count=96, radius=1,
                                       location=CONFIG["planet"]["center_m"])
    obj = base.place(bpy.context.object, "SPACE", role="environment")
    obj.name = name
    obj.scale = (radius,) * 3
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def stars():
    rng = random.Random(CONFIG["seed"])
    vertices, faces = [], []
    distance = 40000000
    for _ in range(5000):
        z, angle = rng.uniform(-1, 1), rng.uniform(0, math.tau)
        direction = Vector((math.sqrt(1 - z * z) * math.cos(angle),
                            math.sqrt(1 - z * z) * math.sin(angle), z))
        tangent = direction.cross(Vector((0, 0, 1))).normalized()
        up = direction.cross(tangent)
        center = direction * distance
        radius = rng.uniform(1700, 5500) if rng.random() < .95 else rng.uniform(5500, 9000)
        start = len(vertices)
        vertices.extend(tuple(center + tangent * x * radius + up * y * radius)
                        for x, y in ((-1, 0), (0, 1), (1, 0), (0, -1)))
        faces.append(tuple(start + i for i in range(4)))
    mesh = bpy.data.meshes.new("Sparse fixed star field")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    ob = bpy.data.objects.new(mesh.name, mesh)
    base.COLLECTIONS["SPACE"].objects.link(ob)
    mat = base.material("ORBIT_starlight", (.40, .46, .53), 0, 1, 1.3)
    mesh.materials.append(mat)
    ob.visible_shadow = ob.visible_diffuse = ob.visible_glossy = False
    ob["role"] = "environment"
    ob["not_astronomical_catalog"] = True


def lighting(scene):
    direction = Vector(CONFIG["stellar_direction"]).normalized()
    sun = base.light("ORBIT shared stellar key", "SUN", direction * 1000, (0, 0, 0),
                     CONFIG["stellar_energy"], (1, .83, .65))
    sun.data.angle = .012
    sun["shared_planet_and_ship_key"] = True
    proxy = Vector(CONFIG["planet"]["center_m"]).normalized() * 1050
    base.light("ORBIT planet-direction fill proxy", "AREA", proxy, (0, 0, 0), 1500000,
               (.31, .48, .68), 850)
    base.light("ORBIT low camera-side art fill", "AREA", (-420, -560, 350), (0, 0, 0),
               950000, (.62, .72, .82), 650)
    world = scene.world.node_tree.nodes.get("Background")
    world.inputs[0].default_value = (.016, .022, .033, 1)
    world.inputs[1].default_value = .10
    scene.view_settings.exposure = .65
    for node in scene.node_tree.nodes:
        if node.type == "GLARE":
            node.threshold = 2.3
            node.mix = -.9
            node.size = 7


def build(a):
    out = a.output.resolve()
    target = out / "flagship-orbit-study.blend"
    if target.exists() and not a.overwrite:
        raise SystemExit("Scene exists; use a new output directory")
    for path in (a.base_scene, a.material_scene):
        if not path.is_file():
            raise SystemExit("Both saved source scenes are required")
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(a.base_scene.resolve()))
    scene = bpy.context.scene
    original_archive = archive_fingerprint()
    for other in list(bpy.data.scenes):
        if other != scene:
            bpy.data.scenes.remove(other)
    # Preserve the archive's existing small working lights, in their own group.
    room_lights = bpy.data.collections.new("ROOM_LIGHTS")
    scene.collection.children.link(room_lights)
    for ob in list(bpy.data.collections["LIGHTING"].objects):
        if ob.name.startswith("Archive recessed working light"):
            room_lights.objects.link(ob)
            bpy.data.collections["LIGHTING"].objects.unlink(ob)
    for name in ("SPACE", "LIGHTING", "COUPON", "COUPON_LIGHTS"):
        coll = bpy.data.collections[name]
        for ob in list(coll.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.collections.remove(coll)
    base.COLLECTIONS.clear()
    base.COLLECTIONS.update({c.name: c for c in scene.collection.children})
    base.MATERIALS.clear()
    base.MATERIALS.update({m.name: m for m in bpy.data.materials})
    for name in ("SPACE", "LIGHTING", "BASELINE_SHIP", "STARBOARD_DETAILS"):
        base.collection(name)
    baseline = base.COLLECTIONS["BASELINE_SHIP"]
    for name in ("SHIP_HULL", "ARCHIVE_SHELL"):
        for ob in list(base.COLLECTIONS[name].objects):
            old = ob.copy()
            old.name = "BASELINE / " + ob.name
            baseline.objects.link(old)
            if ob.data:
                ob.data = ob.data.copy()

    with bpy.data.libraries.load(str(a.material_scene.resolve()), link=False) as (src, dest):
        if "MATERIAL_DETAILS" not in src.collections:
            raise SystemExit("Expected the material-study-01 source collection")
        dest.collections = ["MATERIAL_DETAILS"]
        dest.materials = [name for name in src.materials if name.startswith("STUDY_")]
    port = dest.collections[0]
    port.name = "PORT_DETAILS"
    scene.collection.children.link(port)
    base.COLLECTIONS[port.name] = port
    base.MATERIALS.update({m.name: m for m in bpy.data.materials})
    # Paint samples are in the appended details' dependency graph. Require all.
    assert all(n in bpy.data.materials for n in MATERIAL_MAP.values())
    # A subpixel lip needs a little more radiance at the whole-ship distance.
    # Keep the luminous geometry recessed; do not replace the cavity with a disc.
    bpy.data.materials["STUDY_cool"].node_tree.nodes.get("Principled BSDF").inputs["Emission Strength"].default_value = 6
    bpy.data.materials["STUDY_plasma"].node_tree.nodes.get("Principled BSDF").inputs["Emission Strength"].default_value = 6
    removed_lights = 0
    patterns = (({0, 1}, {1}, {2, 3}, set()), ({2}, {0, 1}, set(), {2, 3}),
                ({0, 1, 2}, set(), {1}, {0, 3}))
    for name in ("SHIP_HULL", "ARCHIVE_SHELL"):
        for ob in list(base.COLLECTIONS[name].objects):
            if ob.name.startswith(OLD_ENGINES):
                bpy.data.objects.remove(ob, do_unlink=True)
                continue
            if ob.name.startswith("Grouped inhabited deck light"):
                block = min(range(4), key=lambda i: abs(ob.location.x - (91 + 27 * i)))
                offset = min(range(4), key=lambda i: abs(ob.location.x - (91 + 27 * block + (-7, -2, 4, 8)[i])))
                row = min(range(3), key=lambda i: abs(ob.location.z - (-12.6, 3.4, 20.4)[i]))
                if offset not in patterns[row][block]:
                    bpy.data.objects.remove(ob, do_unlink=True)
                    removed_lights += 1
                    continue
            for slot in ob.material_slots:
                if slot.material and slot.material.name in MATERIAL_MAP:
                    slot.material = bpy.data.materials[MATERIAL_MAP[slot.material.name]]
    # Mirror the verified source details as editable meshes with positive transforms.
    # Resolve newly appended local transforms before baking their reflected copy.
    bpy.context.view_layer.update()
    reflect = Matrix.Diagonal((1, -1, 1, 1))
    starboard = base.COLLECTIONS["STARBOARD_DETAILS"]
    for ob in list(port.objects):
        twin = ob.copy()
        twin.data = ob.data.copy()
        twin.name = "STBD / " + ob.name
        if ob.type == "MESH":
            twin.data.transform(reflect @ ob.matrix_world)
            twin.data.flip_normals()
            twin.matrix_world = Matrix.Identity(4)
        elif ob.type == "FONT":
            twin.location.y *= -1
            twin.rotation_euler[0] *= -1
            twin.data.body = "K-04"
        starboard.objects.link(twin)
    for image in list(bpy.data.images):
        if image.type == "IMAGE" and image.packed_file:
            texture_dir = out / "textures"
            texture_dir.mkdir(exist_ok=True)
            path = texture_dir / "blue_metal_plate_rough_1k.png"
            # Recreate from packed bytes. Appended images can retain old absolute
            # filenames inside packed_files even when image.filepath is relative.
            path.write_bytes(image.packed_file.data)
            replacement = bpy.data.images.load(str(path), check_existing=False)
            replacement.colorspace_settings.name = image.colorspace_settings.name
            replacement.pack()
            replacement.filepath = "//textures/blue_metal_plate_rough_1k.png"
            for packed in replacement.packed_files:
                packed.filepath = replacement.filepath
            image.user_remap(replacement)
            old_name = image.name
            bpy.data.images.remove(image)
            replacement.name = old_name
    planet()
    stars()
    lighting(scene)
    for name, data in CONFIG["cameras"].items():
        ob = base.camera(name, data["position"], data["target"], lens=data["lens"])
        ob.data.clip_end = 100000000
    scene.name = "KUHAI — Whole Ship Orbital Study 01"
    scene["revision"] = CONFIG["revision"]
    scene["status"] = CONFIG["status"]
    scene["archive_original_fingerprint"] = original_archive
    scene["stellar_direction"] = list(Vector(CONFIG["stellar_direction"]).normalized())
    scene["web_export_status"] = "Separate production study; no updated website asset in this scene"
    scene.camera = bpy.data.objects["overview"]
    scene.render.filepath = "//renders/overview.png"
    scene.render.resolution_x, scene.render.resolution_y = 960, 600
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 6
    scene.cycles.samples = 32
    scene.cycles.max_bounces = 4
    scene.cycles.transparent_max_bounces = 8
    scene.cycles.seed = CONFIG["seed"]
    switch_comparison(False)
    bpy.context.view_layer.update()
    assert archive_fingerprint() == original_archive
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.clip_end = 100000000
                area.spaces.active.region_3d.view_distance = 850
                area.spaces.active.region_3d.view_location = (0, 0, 8)
    bpy.context.preferences.filepaths.save_version = 0
    # The resource paths above are already relative to the NEW delivery folder.
    bpy.ops.wm.save_as_mainfile(filepath=str(target), compress=True, relative_remap=False)
    manifest = {**CONFIG, "blender": bpy.app.version_string,
                "inputs": [{"filename": p.name, "sha256": checksum(p)} for p in (a.base_scene, a.material_scene)],
                "source_blend": target.name, "source_sha256": checksum(target),
                "source_bytes": target.stat().st_size, "removed_repeating_deck_lights": removed_lights,
                "archive_geometry_materials_transforms_preserved": True,
                "packed_images": [i.name for i in bpy.data.images if i.packed_file],
                "objects": {n: len(bpy.data.collections[n].objects) for n in SHIP_GROUPS},
                "gpu_used": False, "browser_tested": False,
                "lighting_limits": "Art-directed fill proxies, procedural fictional planet and approximate limb shell; no physical atmosphere or radiometric claim"}
    (out / "integration-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print("INTEGRATION_BUILD " + json.dumps(manifest, ensure_ascii=False), flush=True)


def render(a):
    views = a.views.split(",")
    if any(v not in CONFIG["cameras"] for v in views):
        raise SystemExit("Unknown view")
    if not (64 <= a.width <= 4096 and 64 <= a.height <= 4096 and 1 <= a.samples <= 1024):
        raise SystemExit("Invalid preview settings")
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not a.overwrite and any((out / (v + ".png")).exists() for v in views):
        raise SystemExit("Render exists; use another directory")
    bpy.ops.wm.open_mainfile(filepath=str(a.scene.resolve()))
    scene = bpy.context.scene
    switch_comparison(a.baseline)
    scene.render.resolution_x, scene.render.resolution_y = a.width, a.height
    scene.cycles.samples = a.samples
    scene.cycles.use_adaptive_sampling = False
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 6
    devices = select_device(scene, a.device)
    report = {"revision": CONFIG["revision"], "baseline": a.baseline, "width": a.width, "height": a.height,
              "samples": a.samples, "threads": 6, "device": a.device, "devices": devices,
              "blender": bpy.app.version_string, "renders": [], "browser_performance_tested": False}
    for view in views:
        scene.camera = bpy.data.objects[view]
        scene.render.filepath = str(out / (view + ".png"))
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        report["renders"].append({"view": view, "seconds": round(time.perf_counter() - start, 3),
                                  "peak_process_rss_mib": peak_process_rss_mib()})
        (out / "benchmark.json").write_text(json.dumps(report, indent=2) + "\n")
        print("INTEGRATION_RENDER " + json.dumps(report["renders"][-1]), flush=True)


if __name__ == "__main__":
    a = options()
    build(a) if a.command == "build" else render(a)
