"""Gate the exact master and its matching baked derivative before GLB export."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import export_review as web
from surface_gate import require
def main(a):
 validation=require(a.source,a.validation);r=json.loads((a.bake/'bake-report.json').read_text());blend=a.bake/'flagship-side-surface-06-web.blend'
 assert r['source_sha256']==validation['source_sha256'] and r['bake_sha256']==web.digest(blend),'Bake provenance mismatch'
 assert r['geometry_validation_sha256']==web.digest(a.validation),'Bake uses a different validation'
 assert not a.output.exists(),'New export directory required'
 web.SOURCE_REVISIONS[r['bake_sha256']]='side-surface-06-baked';web.GROUPS['SIDE06_BAKED']='hull'
 web.export(blend,a.output)
 p=a.output/'model-manifest.json';m=json.loads(p.read_text());m.update(revision='side-surface-06-web',editable_source_sha256=validation['source_sha256'],
  bake_report_sha256=web.digest(a.bake/'bake-report.json'),materials=r['channels'],material_limitations=r['limitation'],browser_performance_tested=False,published=False)
 p.write_text(json.dumps(m,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--bake',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
