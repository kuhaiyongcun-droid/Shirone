"""Validate the integration scene, its resources and unchanged archive contract."""
import argparse
import json
import sys
from pathlib import Path

import bpy
import bmesh
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from integration_study import SHIP_GROUPS, archive_fingerprint, switch_comparison


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scene", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(argv)
    bpy.ops.wm.open_mainfile(filepath=str(a.scene.resolve()))
    scene = bpy.context.scene
    checks, invalid, stats = {}, [], {}
    dg = bpy.context.evaluated_depsgraph_get()
    for group in SHIP_GROUPS:
        objects = list(bpy.data.collections[group].objects)
        triangles = 0
        for obj in objects:
            if obj.type != "MESH":
                continue
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            if not all(e.is_manifold for e in bm.edges) or bm.calc_volume(signed=True) <= 0 or obj.matrix_world.determinant() <= 0:
                invalid.append(obj.name)
            bm.free()
            evaluated = obj.evaluated_get(dg)
            mesh = evaluated.to_mesh()
            mesh.calc_loop_triangles()
            triangles += len(mesh.loop_triangles)
            evaluated.to_mesh_clear()
        stats[group] = {"objects": len(objects), "evaluated_mesh_triangles": triangles}
    checks["independent_closed_positive_ship_meshes"] = not invalid
    checks["archive_geometry_materials_transforms_preserved"] = archive_fingerprint() == scene["archive_original_fingerprint"]
    images = [{"name": i.name, "packed": bool(i.packed_file), "path": i.filepath,
               "packed_paths": [f.filepath for f in i.packed_files], "colorspace": i.colorspace_settings.name}
              for i in bpy.data.images if i.type == "IMAGE" and i.users]
    def portable(path):
        return path.startswith("//") and ".." not in Path(path[2:]).parts
    checks["images_packed_and_relative"] = bool(images) and all(i["packed"] and portable(i["path"]) and all(portable(p) for p in i["packed_paths"]) for i in images)
    reflection = Matrix.Diagonal((1, -1, 1, 1))
    mirror_errors = []
    for ob in bpy.data.collections["PORT_DETAILS"].objects:
        if ob.type != "MESH":
            continue
        twin = bpy.data.objects.get("STBD / " + ob.name)
        if twin is None or len(twin.data.vertices) != len(ob.data.vertices):
            mirror_errors.append(ob.name)
            continue
        if any((reflection @ ob.matrix_world @ v.co - twin.matrix_world @ twin.data.vertices[v.index].co).length > .0001 for v in ob.data.vertices):
            mirror_errors.append(ob.name)
    checks["mirrored_details_match_world_geometry"] = not mirror_errors
    checks["no_linked_libraries"] = not bpy.data.libraries
    checks["relative_render_path"] = scene.render.filepath.startswith("//")
    before = {o.name: o.matrix_world.copy() for o in scene.objects}
    switch_comparison(True)
    switch_comparison(False)
    checks["comparison_keeps_all_transforms"] = all(o.matrix_world == before[o.name] for o in scene.objects)
    hull = set(bpy.data.collections["SHIP_HULL"].objects)
    shell = set(bpy.data.collections["ARCHIVE_SHELL"].objects)
    interior = set(bpy.data.collections["ARCHIVE_INTERIOR"].objects)
    checks["archive_shell_separate"] = not (shell & hull or shell & interior)
    bpy.data.collections["ARCHIVE_SHELL"].hide_render = True
    bpy.data.collections["ARCHIVE_SHELL"].hide_render = False
    checks["cutaway_keeps_all_transforms"] = all(o.matrix_world == before[o.name] for o in scene.objects)
    sun = bpy.data.objects["ORBIT shared stellar key"]
    direction = (sun.matrix_world.to_quaternion() @ Vector((0, 0, 1))).normalized()
    target = Vector(scene["stellar_direction"])
    checks["one_shared_stellar_direction"] = sum(o.type == "LIGHT" and o.data.type == "SUN" for o in scene.objects) == 1 and (direction - target).length < 1e-5
    rim = bpy.data.materials["ORBIT_atmosphere_preview"]
    dot = next(n for n in rim.node_tree.nodes if n.type == "VECT_MATH" and n.operation == "DOT_PRODUCT")
    checks["limb_uses_shared_stellar_direction"] = (Vector(dot.inputs[1].default_value) - target).length < 1e-5
    frames = {}
    bounds = [o.matrix_world @ Vector(v) for group in SHIP_GROUPS for o in bpy.data.collections[group].objects if o.type == "MESH" for v in o.bound_box]
    for view in ("overview", "stern", "port"):
        camera = bpy.data.objects[view]
        coords = [world_to_camera_view(scene, camera, v) for v in bounds]
        frame = {"left": min(v.x for v in coords), "right": max(v.x for v in coords),
                 "bottom": min(v.y for v in coords), "top": max(v.y for v in coords),
                 "min_depth": min(v.z for v in coords)}
        frames[view] = frame
        checks[view + "_whole_ship_in_frame"] = frame["left"] > .015 and frame["right"] < .985 and frame["bottom"] > .015 and frame["top"] < .985 and frame["min_depth"] > 0
    report = {"passed": all(checks.values()), "checks": checks, "invalid_meshes": invalid,
              "stats": stats, "images": images, "frames": frames, "mirror_errors": mirror_errors,
              "blender": bpy.app.version_string,
              "limits": "Closure is not collision/engineering validation. Framing is for the recorded 960x600 cameras. No browser/GPU performance acceptance."}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
