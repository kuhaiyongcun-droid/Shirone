"""Arrange unretouched matched renders; requires Pillow 12.3.0, not Blender."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw
from integration_review import font, frame


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    current,previous=a.input/"current",a.input/"previous"
    sheet=Image.new("RGB",(1008,1140),"#0b1319")
    d=ImageDraw.Draw(sheet)
    d.text((24,20),"KUHAI / BRIDGE STUDY 01",font=font(29),fill="#e4e8e9")
    d.text((24,64),"ARMORED OVERHANG / RECESSED WINDOWS / SWEPT SUPPORTS",font=font(17),fill="#c9b38e")
    d.text((24,92),"01 / BRIDGE AND DORSAL CONNECTION",font=font(16),fill="#bbc8cc")
    with Image.open(current/"bridge_close.png") as img:
        if img.size!=(960,600):raise ValueError("Expected 960 x 600 frame")
        sheet.paste(img.convert("RGB"),(24,118))
    for x,name,label in ((24,"bridge_low","02 / WINDOW RECESS"),(516,"overview","03 / WHOLE-SHIP CONTEXT")):
        d.text((x,746),label,font=font(16),fill="#bbc8cc")
        with Image.open(current/(name+".png")) as img:
            if img.size!=(960,600):raise ValueError("Expected 960 x 600 frame")
            sheet.paste(img.convert("RGB").resize((468,293),Image.Resampling.LANCZOS),(x,774))
    d.text((24,1098),"Cycles CPU / editable exterior study / lighting and original cameras retained",font=font(15),fill="#90a4ae")
    sheet.save(a.output/"bridge-study-01.webp",quality=94)

    comparison=Image.new("RGB",(1512,1172),"#0b1319")
    d=ImageDraw.Draw(comparison)
    d.text((24,20),"KUHAI / BRIDGE — BEFORE AND AFTER",font=font(29),fill="#e4e8e9")
    d.text((24,65),"IDENTICAL CAMERAS + LIGHTING / CHANGED BRIDGE EXTERIOR ONLY",font=font(17),fill="#c9b38e")
    for row,name in enumerate(("form_close","bridge_low")):
        for col,(directory,label) in enumerate(((previous,"SURFACE 03 / PREVIOUS"),(current,"BRIDGE 01 / REVISED"))):
            x,y=24+744*col,110+504*row
            d.text((x,y),label,font=font(17),fill="#bbc8cc")
            frame(comparison,directory,name,x,y+30)
    d.text((24,1134),"12 crown segments / 16 observation bays / interpretation, not an official blueprint",font=font(17),fill="#90a4ae")
    comparison.save(a.output/"bridge-study-01-comparison.webp",quality=94)
    print("Created two review boards from unretouched renders")


if __name__=="__main__":
    main()
