"""Check shape-study portability, comparison integrity and archive clearance.

The archive clearance test uses evaluated triangles against a reserved box,
including containment. This is not a whole-ship collision simulation.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inspect_integration
from form_study import CONFIG, PREFIX, contract, exterior_fingerprint
from integration_study import switch_comparison


def triangle_box(points, center, half):
    """Separating-axis test: 3 box axes, triangle normal, 9 edge cross axes."""
    v=[p-center for p in points]
    edges=[v[1]-v[0],v[2]-v[1],v[0]-v[2]]
    units=[Vector((1,0,0)),Vector((0,1,0)),Vector((0,0,1))]
    axes=units+[edges[0].cross(edges[1])]+[edge.cross(axis) for edge in edges for axis in units]
    for axis in axes:
        if axis.length_squared<1e-12:
            continue
        projections=[p.dot(axis) for p in v]
        radius=sum(abs(axis[i])*half[i] for i in range(3))
        if min(projections)>radius+1e-6 or max(projections)<-radius-1e-6:
            return False
    return True


def enters_room(obj, low, high, dg):
    center=(Vector(low)+Vector(high))*.5
    half=(Vector(high)-Vector(low))*.5
    evaluated=obj.evaluated_get(dg)
    mesh=evaluated.to_mesh()
    mesh.calc_loop_triangles()
    points=[obj.matrix_world @ v.co for v in mesh.vertices]
    triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
    # Broad phase only filters; a long tapered hull's global AABB is not proof
    # of an intersection with a room in its narrow middle.
    overlap=all(min(p[i] for p in points)<high[i] and max(p[i] for p in points)>low[i] for i in range(3))
    if not overlap:
        evaluated.to_mesh_clear()
        return False
    intersects=any(triangle_box([points[i] for i in tri],center,half) for tri in triangles)
    if not intersects:
        # Surface tests alone miss a room wholly enclosed by a solid mesh.
        tree=BVHTree.FromPolygons(points,triangles,all_triangles=True)
        direction=Vector((.927,.317,.199)).normalized()
        origin=center.copy()
        count=0
        for _ in range(len(triangles)+1):
            hit,_,_,_=tree.ray_cast(origin,direction)
            if hit is None:
                break
            count+=1
            origin=hit+direction*1e-4
        else:
            raise RuntimeError("Containment ray did not terminate")
        intersects=count%2==1
    evaluated.to_mesh_clear()
    return intersects


def main():
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scene",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    # Reuse the geometry, mirror, lighting, cutaway and resource checks from the
    # input integration study. Then add risks introduced by this shape edit.
    inspect_integration.main()
    report=json.loads(a.output.read_text(encoding="utf-8"))
    checks=report["checks"]
    scene=bpy.context.scene
    local_transforms={o.name:o.matrix_basis.copy() for o in scene.objects}
    # Hidden copies have unevaluated matrix_world after file load. Compare their
    # actual displayed world geometry, not the identity cache of a hidden object.
    switch_comparison(True)
    bpy.context.view_layer.update()
    checks["baseline_is_exact_previous_exterior"]=exterior_fingerprint(True)==scene["form_baseline_fingerprint"]
    switch_comparison(False)
    bpy.context.view_layer.update()
    checks["evaluated_comparison_keeps_authored_transforms"]=all(o.matrix_basis==local_transforms[o.name] for o in scene.objects)
    checks["environment_rear_details_and_original_cameras_unchanged"]=contract()==scene["form_preserved_contract"]
    checks["correct_immediate_baseline"]=scene["comparison_baseline"]=="integration-study-01"
    occupied_min,occupied_max=CONFIG["archive_protected_bounds_m"]
    conflicts=[]
    dg=bpy.context.evaluated_depsgraph_get()
    for o in scene.objects:
        if o.type!="MESH" or not o.name.startswith(PREFIX):
            continue
        if enters_room(o,occupied_min,occupied_max,dg):
            conflicts.append(o.name)
    checks["new_shape_meshes_clear_occupied_archive_volume"]=not conflicts
    report["archive_clearance_conflicts"]=conflicts
    report["archive_protected_bounds_m"]=CONFIG["archive_protected_bounds_m"]
    report["comparison_baseline"]=scene["comparison_baseline"]
    report["passed"]=all(checks.values())
    report["limits"]+=" New evaluated meshes are tested against the occupied archive reserve with triangle-box SAT and solid containment; not full engineering, structural or whole-ship collision validation."
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("FORM_VALIDATION "+json.dumps({"passed":report["passed"],"checks":checks,"conflicts":conflicts},ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
