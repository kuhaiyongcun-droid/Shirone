"""Arrange unretouched aft study renders; requires Pillow 12.3.0."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw
from integration_review import font, frame


def paste(board, path, xy, size):
    with Image.open(path) as img:
        if img.size != (960,600):
            raise ValueError("Expected a 960 x 600 study render")
        board.paste(img.convert("RGB").resize(size,Image.Resampling.LANCZOS),xy)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    current,previous=a.input/"current",a.input/"previous"
    hero=Image.new("RGB",(1008,1140),"#0b1319");d=ImageDraw.Draw(hero)
    d.text((24,20),"KUHAI / STERN STUDY 01",font=font(29),fill="#e4e8e9")
    d.text((24,64),"ROOT CONNECTIONS / SEGMENTED GUARDS / SERVICE ROUTES",font=font(17),fill="#c9b38e")
    d.text((24,92),"01 / WHOLE-SHIP AFT VIEW",font=font(16),fill="#bbc8cc")
    paste(hero,current/"stern.png",(24,118),(960,600))
    for x,name,label in ((24,"stern_connection","02 / CASING-TO-DECK CONNECTION"),(516,"stern_nozzle","03 / ORIGINAL NOZZLE DEPTH RETAINED")):
        d.text((x,746),label,font=font(15),fill="#bbc8cc")
        paste(hero,current/(name+".png"),(x,774),(468,293))
    d.text((24,1098),"Editable exterior study / same original lighting / not final art or propulsion engineering",font=font(14),fill="#90a4ae")
    hero.save(a.output/"stern-study-01.webp",quality=94)
    board=Image.new("RGB",(1512,1172),"#0b1319");d=ImageDraw.Draw(board)
    d.text((24,20),"KUHAI / STERN — BEFORE AND AFTER",font=font(29),fill="#e4e8e9")
    d.text((24,65),"IDENTICAL CAMERAS + LIGHTING / NEW PARTS HIDDEN FOR THE PREVIOUS VIEW",font=font(17),fill="#c9b38e")
    for row,name in enumerate(("stern","stern_connection")):
        for col,(directory,label) in enumerate(((previous,"BRIDGE 02 / PREVIOUS"),(current,"STERN 01 / REVISED"))):
            x,y=24+744*col,110+504*row
            d.text((x,y),label,font=font(17),fill="#bbc8cc")
            frame(board,directory,name,x,y+30)
    d.text((24,1134),"Existing engine layout, inner liners, emission, planet and original hull preserved",font=font(17),fill="#90a4ae")
    board.save(a.output/"stern-study-01-comparison.webp",quality=94)
    print("Created two review boards without retouching renders")


if __name__=="__main__":
    main()
