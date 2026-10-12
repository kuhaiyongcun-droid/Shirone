"""Decode web assets in Blender and verify geometry and semantic roles.

Optional uncompressed GLB output is temporary input for Node-only ray tests;
it is not a production asset and does not involve a browser or GPU.
"""
import argparse
import json
from pathlib import Path

import bpy
from mathutils import Vector


def inspect(assets, output, decoded):
    manifest = json.loads((assets / "model-manifest.json").read_text())
    report = {}
    for filename, expected in manifest["files"].items():
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str((assets / filename).resolve()))
        bpy.context.view_layer.update()
        roles = {}
        for obj in bpy.context.scene.objects:
            if obj.type != "MESH":
                continue
            box = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
            role = obj.get("role")
            info = roles.setdefault(role, {"triangles": 0, "meshes": 0, "invalid_normals": 0,
                "bounds_min": [1e10] * 3, "bounds_max": [-1e10] * 3})
            obj.data.calc_loop_triangles()
            info["triangles"] += len(obj.data.loop_triangles)
            info["meshes"] += 1
            info["invalid_normals"] += sum(abs(n.vector.length - 1) > .002 for n in obj.data.corner_normals)
            for axis in range(3):
                info["bounds_min"][axis] = min(info["bounds_min"][axis], *[v[axis] for v in box])
                info["bounds_max"][axis] = max(info["bounds_max"][axis], *[v[axis] for v in box])
        assert sum(r["triangles"] for r in roles.values()) == expected["triangles"]
        assert sum(r["meshes"] for r in roles.values()) == expected["batches"]
        assert not sum(r["invalid_normals"] for r in roles.values()), roles
        report[filename] = roles
        if decoded:
            decoded.mkdir(parents=True, exist_ok=True)
            bpy.ops.export_scene.gltf(filepath=str((decoded / filename).resolve()), export_format="GLB",
                export_extras=True, export_draco_mesh_compression_enable=False)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assets", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--decoded", type=Path)
    args = p.parse_args()
    inspect(args.assets, args.output, args.decoded)
