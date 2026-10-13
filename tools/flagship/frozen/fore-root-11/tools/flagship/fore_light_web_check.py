"""Reuse 554 real decoded-mesh rays with the exact fore10 source gate."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import check_fore_web_geometry as inspection
from fore_light_check import require
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 inspection.require=require;inspection.main(p.parse_args())
