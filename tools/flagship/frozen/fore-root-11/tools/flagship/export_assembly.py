"""Explicit fingerprint registry for the recovered source and approved test export.

The validator must already have passed the chosen scene. This exports a
simple-PBR geometry study; no claim that procedural coatings were baked.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import export_review as web

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--registry',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    registry=json.loads(a.registry.read_text())
    if web.digest(a.source) not in registry['validated_sources']:
        raise SystemExit('Source must pass inspection and be explicitly registered')
    if a.output.exists():raise SystemExit('Export destination exists; choose a new directory')
    web.SOURCE_REVISIONS.update(registry['validated_sources'])
    web.GROUPS['SIDE05_STRUCTURE']='hull'
    web.export(a.source,a.output)
    p=a.output/'model-manifest.json'
    m=json.loads(p.read_text())
    m['revision']='side-assembly-05-web'
    m['browser_performance_tested']=False
    m['materials']='Simple untextured PBR; source coating variation and micro bump are not baked. Solid seams, fittings, markings and repair contact strips are exported geometry.'
    p.write_text(json.dumps(m,indent=2)+'\n')
