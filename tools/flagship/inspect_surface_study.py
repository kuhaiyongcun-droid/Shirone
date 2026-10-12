"""Check actual saved geometry, room preservation, and portable image resources."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_study import contract
from integration_study import archive_fingerprint
from surface_study import CONFIG, HULL, ROOM


def main():
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    bpy.ops.wm.open_mainfile(filepath=str(args.baseline.resolve()))
    baseline_room, baseline_contract = archive_fingerprint(), contract()
    bpy.ops.wm.open_mainfile(filepath=str(args.scene.resolve()))
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    checks = {
        "baseline_sha256":hashlib.sha256(args.baseline.read_bytes()).hexdigest() == CONFIG["input_sha256"],
        "archive_matches_baseline":archive_fingerprint() == baseline_room,
        "environment_matches_baseline":contract() == baseline_contract,
        "stored_archive_fingerprint":archive_fingerprint() == scene["surface_archive_fingerprint"],
        "stored_environment_contract":contract() == scene["surface_preserved_contract"],
        "cutaway_parent_owns_details":ROOM in bpy.data.collections["ARCHIVE_SHELL"].children,
    }
    issues, meshes, images = [], [], []
    for collection in (HULL, ROOM):
        for obj in bpy.data.collections[collection].objects:
            if collection == ROOM and (obj.get("role") != "archive_shell" or obj.get("room_id") != "archive"):
                issues.append(obj.name + ": incorrect archive ownership")
            if obj.type != "MESH":
                continue
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            volume = bm.calc_volume(signed=True)
            closed = all(e.is_manifold for e in bm.edges)
            finite = all(math.isfinite(c) for v in bm.verts for c in v.co)
            bm.free()
            if not (closed and finite and volume > 0):
                issues.append(obj.name + ": invalid closed positive-volume mesh")
            evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            mesh.calc_loop_triangles()
            coords = [obj.matrix_world @ v.co for v in mesh.vertices]
            bounds = [[min(v[i] for v in coords) for i in range(3)],
                      [max(v[i] for v in coords) for i in range(3)]]
            if collection == ROOM and all(bounds[0][i] < (-61,-27,22.8)[i] and bounds[1][i] > (-99,-47,16.6)[i] for i in range(3)):
                issues.append(obj.name + ": intersects occupied archive envelope")
            meshes.append({"name":obj.name,"triangles":len(mesh.loop_triangles),
                           "closed":closed,"volume_m3":round(volume,6),"bounds_m":bounds})
            evaluated.to_mesh_clear()
    for image in bpy.data.images:
        if image.type == "IMAGE" and image.users:
            relative = image.filepath.startswith("//")
            packed = image.packed_file is not None
            disk = Path(bpy.path.abspath(image.filepath))
            images.append({"name":image.name,"path":image.filepath,"relative":relative,
                           "packed":packed,"external_exists":disk.is_file()})
            if not (relative and packed and disk.is_file()):
                issues.append(image.name + ": missing portable image resource")
    checks["new_geometry_and_resources_valid"] = not issues
    record = {"revision":CONFIG["revision"],"source_sha256":hashlib.sha256(args.scene.read_bytes()).hexdigest(),
              "checks":checks,"issues":issues,"images":images,"new_meshes":len(meshes),
              "new_mesh_triangles":sum(m["triangles"] for m in meshes),"meshes":meshes,
              "font_object_note":"Archive serial is a native Blender text object, not counted as mesh triangles",
              "passed":all(checks.values())}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({k:v for k,v in record.items() if k not in ("meshes",)},indent=2))
    if not record["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
