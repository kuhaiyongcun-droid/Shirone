"""Check source closure, packed resources and static study transforms.

python inspect_material_study.py --scene shoulder-material-study.blend --output validation.json
Does not certify physical systems, artistic quality or browser performance.
"""

import argparse
import json
import sys
from pathlib import Path

import bpy
import bmesh


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scene", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(argv)
    bpy.ops.wm.open_mainfile(filepath=str(a.scene.resolve()))
    scene = bpy.context.scene
    collections = {name: bpy.data.collections[name] for name in ("SHIP_HULL", "MATERIAL_DETAILS", "BASELINE", "CAMERAS")}
    failures = []
    stats = {}
    for name in ("SHIP_HULL", "MATERIAL_DETAILS"):
        coll = collections[name]
        coll.hide_viewport = False
        bpy.context.view_layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        triangles = 0
        for ob in coll.objects:
            if ob.type != "MESH":
                continue
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            if not all(e.is_manifold for e in bm.edges) or bm.calc_volume(signed=True) <= 0:
                failures.append(ob.name)
            bm.free()
            evaluated = ob.evaluated_get(graph)
            mesh = evaluated.to_mesh()
            mesh.calc_loop_triangles()
            triangles += len(mesh.loop_triangles)
            evaluated.to_mesh_clear()
        stats[name] = {"objects": len(coll.objects), "evaluated_mesh_triangles": triangles}
    transforms = {ob.name: list(map(list, ob.matrix_world)) for name in ("SHIP_HULL", "MATERIAL_DETAILS", "CAMERAS") for ob in collections[name].objects}
    collections["BASELINE"].hide_render = collections["BASELINE"].hide_viewport = False
    bpy.context.view_layer.update()
    images = [{"name": i.name, "size": list(i.size), "packed": bool(i.packed_file), "path": i.filepath,
               "colorspace": i.colorspace_settings.name} for i in bpy.data.images if i.source == "FILE"]
    checks = {"closed_outward_detail_volumes": not failures,
              "images_packed_and_relative": bool(images) and all(i["packed"] and i["path"].startswith("//") for i in images),
              "roughness_non_color": all(i["colorspace"] == "Non-Color" for i in images),
              "no_linked_libraries": not bpy.data.libraries,
              "relative_render_path": scene.render.filepath.startswith("//"),
              "comparison_switch_keeps_transforms": transforms == {ob.name: list(map(list, ob.matrix_world)) for name in ("SHIP_HULL", "MATERIAL_DETAILS", "CAMERAS") for ob in collections[name].objects},
              "baseline_separate_mesh_data": not ({o.data for o in collections["SHIP_HULL"].objects} & {o.data for o in collections["BASELINE"].objects}),
              "paint_is_dielectric": bpy.data.materials["STUDY_naval_paint"].node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value == 0,
              "alloy_is_metal": bpy.data.materials["STUDY_alloy"].node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value == 1}
    report = {"passed": all(checks.values()), "checks": checks, "invalid_meshes": failures,
              "stats": stats, "images": images, "blender": bpy.app.version_string,
              "limits": "Independent mesh closure is not collision or engineering validation. No browser test."}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
