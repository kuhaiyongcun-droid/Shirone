"""Matched CPU renders of side05 and its preserved side04 comparison."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import side_study as s
import bpy

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scene',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--views',default='side03_detail,side03_context')
    p.add_argument('--width',type=int,default=960)
    p.add_argument('--height',type=int,default=600)
    p.add_argument('--samples',type=int,default=32)
    p.add_argument('--neutral',action='store_true')
    p.add_argument('--previous',action='store_true')
    p.add_argument('--web-model',type=Path)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    a.device='cpu'
    s.NEW,s.OLD='SIDE05_STRUCTURE','SIDE04_STRUCTURE'
    s.CONFIG['revision']='side-assembly-05'
    # Same added neutral fill in both sides of every new comparison; no source mutation.
    original_light=s.base.light
    def inspection_light(name,*args,**kwargs):
        obj=original_light(name,*args,**kwargs)
        if name=='SIDE03 neutral fill':
            original_light('SIDE04 neutral frontal fill','AREA',(-170,-86,49),(-171,-23,35),
                           35000,(1,1,1),38)
        return obj
    s.base.light=inspection_light
    s.render(a)
