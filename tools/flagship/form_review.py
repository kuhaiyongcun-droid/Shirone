"""Assemble matched renders; resize only, with no lighting or image retouch."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from integration_review import font, frame


def sheet(title, subtitle, rows, output):
    canvas=Image.new("RGB",(1512,1158),"#0b1319")
    d=ImageDraw.Draw(canvas)
    d.text((24,20),title,font=font(30),fill="#e4e8e9")
    d.text((24,65),subtitle,font=font(16),fill="#c9b38e")
    for row,columns in enumerate(rows):
        for col,(directory,name,label) in enumerate(columns):
            x,y=24+col*744,116+row*504
            d.text((x,y),label,font=font(17),fill="#bbc8cc")
            frame(canvas,directory,name,x,y+30)
    d.text((24,1128),"Cycles CPU / 960 x 600 / 32 samples | Shape study, not final art",font=font(15),fill="#90a4ae")
    canvas.save(output,quality=94)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("baseline","current","cutaway","output"):
        p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    sheet("KUHAI / FOREBODY FORM STUDY 03","BEFORE / AFTER — IDENTICAL CAMERAS, MATERIALS AND ORBITAL LIGHTING",
          [[(a.baseline,"overview","BEFORE / INTEGRATION 01"),(a.current,"overview","AFTER / FORM 03")],
           [(a.baseline,"form_close","BEFORE / FOREBODY"),(a.current,"form_close","AFTER / SWEPT SHOULDERS + TAPERED PROW")]],
          a.output/"form-study-03-comparison.webp")
    sheet("KUHAI / SILHOUETTE + ARCHIVE CLEARANCE","ORTHOGRAPHIC PLAN / LOCAL SHELL REMOVAL — FIXED INTERIOR AND CAMERA",
          [[(a.baseline,"form_top","BEFORE / TOP PLAN"),(a.current,"form_top","AFTER / TOP PLAN")],
           [(a.current,"form_archive","FITTED ARCHIVE SHELL / CLOSED"),(a.cutaway,"form_archive","SAME CAMERA / SHELL HIDDEN")]],
          a.output/"form-study-03-structure.webp")


if __name__=="__main__":
    main()
