"""Shared fail-closed gate for rendering, baking and export."""
import hashlib,json
from pathlib import Path
REQUIRED={'prior_content_preserved','closed_solids','equipment_and_routes_clear_of_hull','all_functional_endpoints_in_fittings',
          'mounts_and_tees_attached','inspection_panels_visible','portable_images','repaired_geometry_unchanged'}
def require(source,report):
 r=json.loads(Path(report).read_text());digest=hashlib.sha256(Path(source).read_bytes()).hexdigest()
 if r.get('source_sha256')!=digest:raise RuntimeError('Validation is stale or belongs to a different scene; rerun surface_check.py')
 if not r.get('passed') or any(r.get('checks',{}).get(k) is not True for k in REQUIRED):raise RuntimeError('Assembly/geometry validation failed or is incomplete')
 if len(r.get('route_endpoints',[]))!=24 or len(r.get('support_endpoints',[]))!=48 or len(r.get('panel_visibility',[]))!=18:
  raise RuntimeError('Assembly inspection coverage has changed; update and review check coverage explicitly')
 return r
