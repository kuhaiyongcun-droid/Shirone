"""Build an editable proportion study, plus a separate simple-PBR glTF export.

Desktop: blender -b --python build_scene.py -- --output ./output
Cloud:   python build_scene.py --output ./output  (requires pinned bpy)

This is original provisional geometry, not an extracted game asset. No external
images, add-ons, network requests, GPU selection, or render is needed to build.
"""

import argparse
import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "settings.json").read_text(encoding="utf-8"))
RNG = random.Random(CONFIG["random_seed"])
MATERIALS = {}
COLLECTIONS = {}


def arguments():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    parser.add_argument("--overwrite", action="store_true", help="Replace generated files only")
    return parser.parse_args(argv)


def collection(name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    COLLECTIONS[name] = coll
    return coll


def place(obj, group, material=None, role="hull"):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    COLLECTIONS[group].objects.link(obj)
    obj["role"] = role
    if role in {"archive_shell", "archive_interior"}:
        obj["room_id"] = "archive"
    if material:
        obj.data.materials.append(MATERIALS[material])
    return obj


def material(name, color, metallic=0.0, roughness=0.4, emission=0.0, detail=False):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*color, 1)
        bsdf.inputs["Emission Strength"].default_value = emission
    mat["web_metallic"] = metallic
    mat["web_roughness"] = roughness
    mat["web_emission"] = emission
    if detail:
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        coord = nodes.new("ShaderNodeTexCoord")
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 5.5
        noise.inputs["Detail"].default_value = 2.0
        links.new(coord.outputs["Object"], noise.inputs["Vector"])
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (roughness * 0.75,) * 3 + (1,)
        ramp.color_ramp.elements[1].color = (min(roughness * 1.25, 1),) * 3 + (1,)
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.13
        bump.inputs["Distance"].default_value = 0.035
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    MATERIALS[name] = mat
    return mat


def bevel(obj, width, segments=2):
    if width <= 0:
        return
    mod = obj.modifiers.new("Editable edge bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    weighted = obj.modifiers.new("Weighted surface normals", "WEIGHTED_NORMAL")
    weighted.keep_sharp = True


def box(name, loc, dims, mat="armor", group="SHIP_HULL", edge=0.5, role="hull"):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel(obj, edge)
    return place(obj, group, mat, role)


def prism(name, xy, bottom, top, mat="armor", group="SHIP_HULL", edge=0.8, role="hull"):
    # xy must be counterclockwise. Reversed mirrored outlines are normalized.
    area = sum(xy[i][0] * xy[(i + 1) % len(xy)][1] - xy[(i + 1) % len(xy)][0] * xy[i][1]
               for i in range(len(xy)))
    if area < 0:
        xy = list(reversed(xy))
    count = len(xy)
    verts = [(x, y, z) for z in (bottom, top) for x, y in xy]
    faces = [tuple(reversed(range(count))), tuple(range(count, 2 * count))]
    faces += [(i, (i + 1) % count, (i + 1) % count + count, i + count) for i in range(count)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    COLLECTIONS[group].objects.link(obj)
    obj.data.materials.append(MATERIALS[mat])
    obj["role"] = role
    if role.startswith("archive_"):
        obj["room_id"] = "archive"
    bevel(obj, edge)
    return obj


def cylinder(name, loc, radius, depth, mat="edge", axis="Z", group="SHIP_HULL", role="hull", vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    if axis == "X":
        obj.rotation_euler[1] = math.pi / 2
    if axis == "Y":
        obj.rotation_euler[0] = math.pi / 2
    place(obj, group, mat, role)
    bevel(obj, min(depth * 0.12, radius * 0.04))
    return obj


def torus(name, loc, major, minor, mat="edge", axis="Z", group="SHIP_HULL"):
    bpy.ops.mesh.primitive_torus_add(major_segments=40, minor_segments=8,
                                   major_radius=major, minor_radius=minor, location=loc)
    obj = bpy.context.object
    obj.name = name
    if axis == "X":
        obj.rotation_euler[1] = math.pi / 2
    place(obj, group, mat, "hull" if group == "SHIP_HULL" else "study")
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def nozzle_shroud(loc, radius, depth):
    # Four circular loops form a hollow sleeve; a capped cylinder would hide the throat.
    segments = 40
    x, y, z = loc
    vertices = []
    for xx, rr in ((x - depth / 2, radius), (x + depth / 2, radius),
                   (x - depth / 2, radius * 0.8), (x + depth / 2, radius * 0.8)):
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            vertices.append((xx, y + rr * math.cos(angle), z + rr * math.sin(angle)))
    faces = []
    for a, b in ((0, 1), (3, 2), (1, 3), (2, 0)):
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((a * segments + i, a * segments + j, b * segments + j, b * segments + i))
    mesh = bpy.data.meshes.new("Hollow nozzle shroud")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Hollow nozzle shroud", mesh)
    COLLECTIONS["SHIP_HULL"].objects.link(obj)
    mesh.materials.append(MATERIALS["dark"])
    obj["role"] = "hull"
    return obj


def camera(name, loc, target, ortho=None, lens=44):
    data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, data)
    COLLECTIONS["CAMERAS"].objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    data.lens = lens
    data.clip_start = 0.1
    data.clip_end = 20000
    if ortho:
        data.type = "ORTHO"
        data.ortho_scale = ortho
    return obj


def light(name, kind, loc, target, energy, color, size=100, group="LIGHTING"):
    data = bpy.data.lights.new(name, kind)
    data.energy = energy
    data.color = color
    if kind == "AREA":
        data.shape = "DISK"
        data.size = size
    elif kind == "SUN":
        data.angle = 0.10
    obj = bpy.data.objects.new(name, data)
    COLLECTIONS[group].objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for name in ("SHIP_HULL", "ARCHIVE_SHELL", "ARCHIVE_INTERIOR", "SPACE", "LIGHTING", "COUPON", "COUPON_LIGHTS", "CAMERAS"):
        collection(name)
    material("armor", (0.105, 0.14, 0.16), 0.72, 0.4, detail=True)
    material("paint", (0.22, 0.28, 0.31), 0.48, 0.47, detail=True)
    material("edge", (0.32, 0.37, 0.4), 0.9, 0.27, detail=True)
    material("dark", (0.024, 0.034, 0.041), 0.55, 0.52)
    material("amber", (1.0, 0.43, 0.12), 0.0, 0.33, 3)
    material("cyan", (0.12, 0.65, 1.0), 0.0, 0.24, 4)
    material("stripe", (0.56, 0.29, 0.08), 0.15, 0.5)
    material("paper", (0.39, 0.30, 0.21), 0.0, 0.78)
    material("room", (0.15, 0.18, 0.19), 0.3, 0.5)
    material("person", (0.8, 0.61, 0.29), 0.05, 0.45)
    scene = bpy.context.scene
    scene.name = "KUHAI — Structural Study 01"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    scene["status"] = CONFIG["status"]
    scene["proportions_are_provisional"] = True
    scene["canonical_dimensions_verified"] = False
    scene["room_definition"] = json.dumps(CONFIG["archive"])
    scene.world = bpy.data.worlds.new("Deep space studio ambience")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.08, 0.11, 0.16, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.23
    scene.view_settings.view_transform = "AgX"
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = CONFIG["preview"]["samples"]
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.cycles.seed = CONFIG["random_seed"]
    scene.render.threads_mode = "FIXED"
    scene.render.threads = CONFIG["preview"]["threads"]
    scene.render.resolution_x = CONFIG["preview"]["width"]
    scene.render.resolution_y = CONFIG["preview"]["height"]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.use_nodes = True
    nodes, links = scene.node_tree.nodes, scene.node_tree.links
    nodes.clear()
    layers = nodes.new("CompositorNodeRLayers")
    glow = nodes.new("CompositorNodeGlare")
    glow.glare_type = "FOG_GLOW"
    glow.quality = "MEDIUM"
    glow.threshold = 2.0
    glow.size = 7
    glow.mix = -0.9
    out = nodes.new("CompositorNodeComposite")
    links.new(layers.outputs["Image"], glow.inputs["Image"])
    links.new(glow.outputs["Image"], out.inputs["Image"])
    return scene


def hull():
    # Long central keel; broad rear shoulders and stepped paired engine housings.
    outline = [(-250, -29), (-235, -44), (-165, -43), (-90, -34), (30, -38),
               (112, -58), (221, -49), (239, -32), (239, 32), (221, 49),
               (112, 58), (30, 38), (-90, 34), (-165, 43), (-235, 44), (-250, 29)]
    prism("Longitudinal pressure / service keel", outline, -23, 8)
    prism("Ventral armored spine", [(-245, -20), (190, -26), (231, -13), (231, 13), (190, 26), (-245, 20)], -34, -22, "dark")
    box("Forecastle pressure body", (-204, 0, 16), (79, 68, 25), "armor", edge=4)
    box("Bridge pedestal", (-172, 0, 34), (52, 39, 20), "paint", edge=3)
    prism("Bridge armored brow", [(-207, -18), (-195, -29), (-159, -29), (-145, -16), (-145, 16), (-159, 29), (-195, 29), (-207, 18)], 44, 54, "armor", edge=1.4)
    # Windows are restrained strips; no giant glass facade across the warship.
    for side in (-1, 1):
        box("Bridge amber glazing", (-180, side * 29.15, 48), (33, 0.45, 2.6), "amber", edge=0.1)
        box("Forecastle lateral sill", (-217, side * 51, 6), (61, 22, 18), "paint", edge=2.5)
        box("Forecastle cyan navigation strip", (-225, side * 62.1, 9), (12, 0.45, 0.8), "cyan", edge=0.05)
    cylinder("Communications mast", (-161, 0, 63), 0.65, 21)
    box("Communications crossbar", (-161, 0, 69), (0.8, 13, 0.8), "edge", edge=0.1)

    for x in (-125, -102, -79, -56, -33, -10, 13):
        box("Dorsal service trunk", (x, 0, 14), (19, 33, 13), "dark", edge=1)
        box("Transverse armor rib", (x, 0, 22), (6, 47, 6), "paint", edge=0.8)
        for side in (-1, 1):
            cylinder("Protected longitudinal utility conduit", (x, side * 29, 12), 2, 20, "edge", axis="X", vertices=12)

    wing = [(6, 35), (32, 66), (56, 139), (160, 145), (197, 123), (170, 60), (119, 37)]
    for side in (-1, 1):
        points = [(x, y * side) for x, y in wing]
        prism("Aft shoulder armored volume", points, -10, 20, "armor", edge=3)
        prism("Shoulder upper plating", [(x + 4, y * side * 0.93) for x, y in wing], 20, 25, "paint", edge=1)
        # Stepped upright side fins are silhouette features, not random decoration.
        fin = [(53, 137 * side), (58, 149 * side), (171, 149 * side), (189, 138 * side), (174, 132 * side)]
        prism("Outer shoulder shield", fin, -9, 45, "armor", edge=1.5)
        for x in (66, 90, 114, 138, 162):
            box("Shoulder shield reinforcement", (x, side * 146, 21), (5, 11, 47), "paint", edge=1)
        cylinder("Circular shoulder equipment housing", (104, side * 97, 28), 24, 9, "dark", vertices=48)
        torus("Equipment housing armor ring", (104, side * 97, 33), 20, 2.2)
        cylinder("Circular housing cover", (104, side * 97, 33), 16, 3, "paint", vertices=40)
        torus("Equipment status band", (104, side * 97, 35), 11.5, 0.4, "cyan")
        cylinder("Equipment housing center", (104, side * 97, 35), 8, 2, "dark")
        # Three-dimensional fin vents and panel seams, limited to visible scale.
        for x in (62, 81, 100, 119, 138):
            box("Outer vent recess", (x, side * 150, 6), (12, 0.6, 4), "dark", edge=0.15)
            box("Sparse equipment running light", (x, side * 150.5, 19), (5, 0.4, 0.6), "amber", edge=0.05)
        for x in (35, 59, 83, 107, 131):
            box("Wing underside structural rib", (x, side * 85, -13), (5, 81, 6), "edge", edge=0.6)

    # Paired upper/lower engine banks; engines share a physical aft direction.
    for y in (-29, 29):
        for z, radius, length in ((35, 22, 90), (-19, 16, 64)):
            center = 194 if z > 0 else 207
            cylinder("Octagonal engine pressure casing", (center, y, z), radius + 4, length, "armor", "X", vertices=8)
            for x in (164, 190, 216):
                if z < 0 and x == 164:
                    continue
                torus("Engine casing retaining ring", (x, y, z), radius + 3, 1.1, "edge", "X")
            nozzle_shroud((245, y, z), radius, 14)
            torus("Nozzle lip", (247, y, z), radius - 1, 1.1, "edge", "X")
            cylinder("Engine luminous throat", (246, y, z), radius * 0.79, 0.65, "cyan", "X", vertices=40)
            cylinder("Engine center cone", (248, y, z), radius * 0.22, 3, "edge", "X")
            if z > 0:
                box("Engine dorsal armored rail", (195, y, z + radius + 2), (66, 19, 6), "paint", edge=2)
                box("Engine dorsal status strip", (207, y, z + radius + 5.2), (24, 2, 0.5), "cyan", edge=0.1)

    # Large armor breaks define scale; micro-greebles are deliberately deferred.
    for x in (-234, -217, -200):
        for side in (-1, 1):
            box("Forecastle deck plate", (x, side * 17, 30), (15.5, 30, 2.2), "paint", edge=0.3)
    for side in (-1, 1):
        for x in (56, 78, 100, 122):
            box("Midship exposed maintenance bay", (x, side * 43, 5), (17, 8, 12), "dark", edge=0.6)
            box("Midship amber slit", (x, side * 47.5, 9), (8, 0.45, 0.7), "amber", edge=0.08)
        for x, y, z in ((-227, 32, 33), (33, 65, 29), (159, 115, 29)):
            cylinder("Turret mounting ring", (x, side * y, z), 6.5, 3, "dark", vertices=24)
            box("Turret armored cradle", (x, side * y, z + 4), (12, 9, 6), "paint", edge=1)
            for dy in (-2, 2):
                cylinder("Turret barrel placeholder", (x - 11, side * y + dy, z + 4), 0.7, 19, "edge", "X", vertices=12)
    # Mirror the archive's broad pod on starboard as an unassigned service volume.
    box("Unassigned starboard service bay", (-80, 37, 9), (70, 35, 36), "armor", edge=3)
    box("Starboard service roof", (-80, 37, 28), (69, 34, 2), "paint", edge=1)


def archive():
    group = "ARCHIVE_INTERIOR"
    origin = CONFIG["archive"]["origin_m"]
    ox, oy, oz = origin
    room_role = "archive_interior"

    def part(name, offset, dims, mat="room", edge=0.08):
        return box(name, tuple(a + b for a, b in zip(origin, offset)), dims, mat, group, edge, room_role)

    box("Archive service pod lower hull", (-80, -37, 2), (70, 35, 29), "armor", edge=2)
    box("Archive bay structural deck", (-80, -37, 16), (69, 34, 1.5), "dark", edge=0.4)
    # Removable roof and near wall expose only this bay; everything stays in place.
    box("Archive removable armored roof", (-80, -37, 28), (70, 35, 3), "paint", "ARCHIVE_SHELL", 1, "archive_shell")
    box("Archive removable port hull panel", (-80, -54, 22), (68, 2, 10), "armor", "ARCHIVE_SHELL", 0.5, "archive_shell")
    for x in (-105, -88, -71, -54):
        box("Archive shell reinforcing strap", (x, -37, 30), (2.5, 35, 1), "edge", "ARCHIVE_SHELL", 0.2, "archive_shell")
    for dx in (-34, 34):
        box("Archive bay transverse bulkhead", (-80 + dx, -37, 22), (2, 33, 10), "armor", edge=0.5)
    box("Archive inner hull support", (-80, -20.5, 22), (68, 2, 10), "armor", edge=0.5)
    part("Archive occupied deck 36 x 18 metres", (0, 0, 0), (36, 18, 0.35))
    part("Archive inboard wall", (0, 8.8, 2.5), (36, 0.4, 5))
    part("Archive end bulkhead", (17.8, 0, 2.5), (0.4, 18, 5))
    # Partial front wall demonstrates section thickness without glass transparency.
    part("Archive section sill", (0, -8.8, 0.55), (36, 0.4, 1.1))
    for x in (-16, -8, 0, 8, 16):
        part("Archive overhead transverse beam", (x, 0, 5.3), (0.35, 18, 0.4), "edge")
        part("Archive amber worklight", (x, 7.9, 4.3), (4.6, 0.13, 0.18), "amber", 0.01)
    # Book and data storage, at human scale, behind two generous passages.
    for x in (-13, -5, 3):
        for y in (4,):
            part("Archive rack back", (x, y, 1.4), (5.4, 0.2, 2.8), "dark")
            for side in (-2.65, 2.65):
                part("Archive rack upright", (x + side, y - 0.48, 1.4), (0.14, 1.1, 2.8), "edge", 0.03)
            for z in (0.3, 1.0, 1.7, 2.4):
                part("Archive rack shelf", (x, y - 0.48, z), (5.4, 1.1, 0.1), "edge", 0.02)
                for j in range(14):
                    part("Archive volume", (x - 2.35 + j * 0.35, y - 0.45, z + 0.29),
                         (0.25, 0.68, RNG.uniform(0.35, 0.5)), "paper" if j % 3 else "paint", 0.01)
    for x in (-9, 2, 11):
        part("Reading terminal tabletop", (x, -3.5, 0.95), (3.2, 1.4, 0.14), "paint")
        part("Reading terminal pedestal", (x, -3.5, 0.47), (0.9, 0.7, 0.95), "dark")
        part("Terminal luminous screen", (x, -3.25, 1.43), (1.1, 0.12, 0.66), "cyan", 0.03)
        part("Reading seat", (x, -5, 0.5), (0.64, 0.64, 0.1), "paper", 0.06)
        part("Reading seat pedestal", (x, -5, 0.24), (0.12, 0.12, 0.5), "edge", 0.02)
    part("Archive corridor threshold", (13, 8.5, 0.25), (2.4, 1.4, 0.15), "stripe", 0.02)
    part("Archive exit frame left", (11.8, 8.5, 1.2), (0.14, 0.8, 2.4), "edge", 0.02)
    part("Archive exit frame right", (14.2, 8.5, 1.2), (0.14, 0.8, 2.4), "edge", 0.02)
    # Scale mannequin: 1.8 m total height, intentionally simplified.
    person = (ox - 2, oy - 0.8, oz + 0.18)
    for dy in (-0.13, 0.13):
        cylinder("1.8 m scale figure leg", (person[0], person[1] + dy, person[2] + 0.4), 0.095, 0.8, "person", group=group, role=room_role, vertices=12)
    box("1.8 m scale figure torso", (person[0], person[1], person[2] + 1.13), (0.24, 0.45, 0.65), "person", group, 0.08, room_role)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.16,
                                       location=(person[0], person[1], person[2] + 1.64))
    place(bpy.context.object, group, "person", room_role).name = "1.8 m scale figure head"
    for x in (-12, 0, 12):
        light("Archive recessed working light", "AREA", (ox + x, oy + 3, oz + 4.5),
              (ox + x, oy, oz), 100, (1, 0.62, 0.3), size=3)


def environment():
    # A fictional uninhabited moon: procedural look only, no copied NASA textures.
    mat = material("moon", (0.15, 0.2, 0.26), 0, 0.9)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 5
    noise.inputs["Detail"].default_value = 5
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.035, 0.06, 0.08, 1)
    ramp.color_ramp.elements[1].color = (0.21, 0.25, 0.28, 1)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], nodes.get("Principled BSDF").inputs["Base Color"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.16
    bump.inputs["Distance"].default_value = 0.2
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], nodes.get("Principled BSDF").inputs["Normal"])
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=300, location=(510, 660, -180))
    obj = place(bpy.context.object, "SPACE", "moon", "environment")
    obj.name = "Fictional moon lighting placeholder — not to scale"
    for poly in obj.data.polygons:
        poly.use_smooth = True
    light("Shared stellar key direction", "SUN", (-400, -500, 800), (0, 0, 0), 3.2, (1, 0.83, 0.64))
    light("Planet-side bounced fill approximation", "AREA", (250, 200, 250), (0, 0, 0), 1800000,
          (0.35, 0.58, 1), size=350)
    light("Inspection camera-side fill", "AREA", (-200, -280, 230), (-20, 0, 0), 600000,
          (0.58, 0.72, 1), size=250)


def coupon():
    # A reusable material/edge sample, not detailed whole-ship authoring.
    center = (0, -600, 0)
    def part(name, xyz, dims, mat, edge=0.05):
        return box(name, tuple(a + b for a, b in zip(center, xyz)), dims, mat, "COUPON", edge, "study")
    part("Sample bulkhead substrate", (0, 0, 0), (8, 4.8, 0.28), "dark")
    for x in (-2, 2):
        part("Sample thick armor panel", (x, 0, 0.35), (3.7, 4.5, 0.45), "paint", 0.09)
        part("Sample removable service hatch", (x, 0.1, 0.65), (2.1, 2.8, 0.22), "armor", 0.07)
        for dx in (-1.55, 1.55):
            for y in (-1.95, 1.95):
                cylinder("Sample captive bolt", (x + dx, -600 + y, 0.62), 0.055, 0.075, "edge", group="COUPON", role="study", vertices=6)
        part("Sample exposed metal edge", (x, -2.2, 0.58), (3.5, 0.045, 0.06), "edge", 0.01)
    part("Sample amber maintenance strip", (0, 2, 0.75), (6.4, 0.16, 0.12), "amber", 0.02)
    for x in (-0.4, 0.1, 0.6):
        cylinder("Sample protected conduit", (x, -600, 1), 0.13, 4.2, "edge", "Y", "COUPON", "study", vertices=16)
    for y in (-1.6, 0, 1.6):
        part("Sample conduit bracket", (0.1, y, 0.98), (1.5, 0.12, 0.55), "dark", 0.02)
    light("Coupon warm key", "AREA", (-4, -604, 8), center, 900, (1, 0.79, 0.57), 5, "COUPON_LIGHTS")
    light("Coupon cool rim", "AREA", (5, -597, 5), center, 650, (0.3, 0.61, 1), 4, "COUPON_LIGHTS")
    COLLECTIONS["COUPON"].hide_render = True
    COLLECTIONS["COUPON"].hide_viewport = True
    COLLECTIONS["COUPON_LIGHTS"].hide_render = True
    COLLECTIONS["COUPON_LIGHTS"].hide_viewport = True


def cameras(scene):
    scene.camera = camera("hero", (-550, -600, 390), (0, 0, 8), lens=44)
    camera("top", (0, 0, 900), (0, 0, 0), ortho=620)
    camera("side", (-10, -900, 12), (0, 0, 12), ortho=600)
    camera("rear", (570, -470, 280), (75, 0, 10), lens=44)
    camera("belly", (-500, -510, -290), (-5, 0, -5), lens=42)
    camera("archive_context", (-210, -233, 156), (-80, -37, 18), lens=52)
    camera("archive", (-115, -75, 51), (-80, -37, 18.4), lens=48)
    camera("coupon", (7, -609, 9), (0, -600, 0.4), lens=48)


def source_stats(scene):
    result = {}
    for name, coll in COLLECTIONS.items():
        if name not in {"SHIP_HULL", "ARCHIVE_SHELL", "ARCHIVE_INTERIOR", "COUPON", "SPACE"}:
            continue
        previous_visibility = coll.hide_viewport
        coll.hide_viewport = False
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        objects = [o for o in coll.objects if o.type == "MESH"]
        triangles = 0
        for obj in objects:
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            mesh.calc_loop_triangles()
            triangles += len(mesh.loop_triangles)
            evaluated.to_mesh_clear()
        result[name] = {"editable_mesh_objects": len(objects), "evaluated_triangles": triangles}
        coll.hide_viewport = previous_visibility
    return result


def export_web(path, source_scene):
    # Bake bevel geometry and group by semantic role/material into a separate scene.
    # The source mesh, modifier stack and procedural materials remain untouched.
    depsgraph = bpy.context.evaluated_depsgraph_get()
    grouped = {}
    for name in ("SHIP_HULL", "ARCHIVE_SHELL", "ARCHIVE_INTERIOR"):
        for obj in COLLECTIONS[name].objects:
            if obj.type != "MESH":
                continue
            mat = obj.data.materials[0]
            key = (obj["role"], mat.name)
            verts, faces = grouped.setdefault(key, ([], []))
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            mesh.calc_loop_triangles()
            offset = len(verts)
            verts.extend([tuple(obj.matrix_world @ v.co) for v in mesh.vertices])
            faces.extend([tuple(offset + i for i in tri.vertices) for tri in mesh.loop_triangles])
            evaluated.to_mesh_clear()
    web_scene = bpy.data.scenes.new("WEB_EXPORT — simple PBR / no scene lighting")
    web_scene["status"] = "Uncompressed structure export; procedural materials deliberately simplified; not web performance approved"
    bpy.context.window.scene = web_scene
    web_materials = {}
    for (role, name), (vertices, faces) in grouped.items():
        if name not in web_materials:
            source = MATERIALS[name]
            mat = bpy.data.materials.new("WEB_" + name)
            mat.use_nodes = True
            mat.diffuse_color = source.diffuse_color
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            bsdf.inputs["Base Color"].default_value = source.diffuse_color
            bsdf.inputs["Metallic"].default_value = source["web_metallic"]
            bsdf.inputs["Roughness"].default_value = source["web_roughness"]
            bsdf.inputs["Emission Color"].default_value = source.diffuse_color
            bsdf.inputs["Emission Strength"].default_value = source["web_emission"]
            web_materials[name] = mat
        mesh = bpy.data.meshes.new(role + "__" + name)
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        mesh.materials.append(web_materials[name])
        obj = bpy.data.objects.new(mesh.name, mesh)
        obj["role"] = role
        if role.startswith("archive_"):
            obj["room_id"] = "archive"
        web_scene.collection.objects.link(obj)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_active_scene=True,
                              export_extras=True, export_cameras=False, export_lights=False,
                              export_animations=False, export_apply=True, export_yup=True)
    result = {"batches": len(grouped), "triangles": sum(len(f) for v, f in grouped.values()),
              "materials": len(web_materials), "bytes": path.stat().st_size,
              "textures": 0, "compressed": False, "browser_performance_tested": False}
    bpy.context.window.scene = source_scene
    # Keep the export scene inside the .blend for inspection, physically separate.
    return result


def main():
    args = arguments()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    names = ("flagship-blockout.blend", "flagship-web-study.glb", "scene-manifest.json")
    if not args.overwrite and any((out / n).exists() for n in names):
        raise SystemExit("Output exists. Use a new directory, or --overwrite for generated outputs.")
    scene = setup()
    hull()
    archive()
    environment()
    coupon()
    cameras(scene)
    stats = source_stats(scene)
    web = export_web(out / names[1], scene)
    bpy.context.window.scene = scene
    scene.render.filepath = "//renders/hero.png"
    bpy.ops.object.select_all(action="DESELECT")
    # Open on the useful whole-ship overview; all geometry remains editable.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.clip_end = 20000
                area.spaces.active.region_3d.view_distance = 700
                area.spaces.active.region_3d.view_location = (0, 0, 12)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(out / names[0]), compress=True)
    manifest = {
        "revision": CONFIG["revision"], "status": CONFIG["status"],
        "blender": bpy.app.version_string,
        "source_blend": names[0], "web_glb": names[1],
        "external_texture_dependencies": [],
        "textures_note": "All source materials are procedural; web export uses simpler untextured PBR.",
        "archive": CONFIG["archive"], "source": stats, "web": web,
        "coordinate_system": "Blender Z up; bow -X, stern +X, port -Y. glTF exporter converts Z up to Y up.",
        "cameras": [o.name for o in COLLECTIONS["CAMERAS"].objects],
        "not_done": ["canonical silhouette approval", "production topology and UV", "texture baking",
                     "LOD", "KTX2/Meshopt compression", "browser hardware validation", "final cinematography"],
    }
    (out / names[2]).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("BUILD_RESULT " + json.dumps(manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
