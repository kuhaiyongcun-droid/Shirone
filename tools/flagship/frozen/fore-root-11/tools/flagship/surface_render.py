"""Matched source/web CPU previews; geometry gate required before any render."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import side_study as s
from surface_gate import require
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--scene',type=Path,required=True);p.add_argument('--validation',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--views',default='side03_detail,side03_context')
 p.add_argument('--width',type=int,default=960);p.add_argument('--height',type=int,default=600);p.add_argument('--samples',type=int,default=32)
 p.add_argument('--neutral',action='store_true');p.add_argument('--previous',action='store_true');p.add_argument('--web-model',type=Path)
 a=p.parse_args();require(a.scene,a.validation);a.device='cpu'
 s.NEW,s.OLD='SIDE06_STRUCTURE','SIDE05_STRUCTURE';s.CONFIG['revision']='side-surface-06'
 original=s.base.light
 def fill(name,*args,**kwargs):
  o=original(name,*args,**kwargs)
  if name=='SIDE03 neutral fill':original('SIDE04 neutral frontal fill','AREA',(-170,-86,49),(-171,-23,35),35000,(1,1,1),38)
  return o
 s.base.light=fill;s.render(a)
