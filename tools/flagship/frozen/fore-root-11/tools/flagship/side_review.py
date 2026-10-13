"""Compose unchanged, matched renders for the port bridge sample."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw
from review_sheet import font


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    with Image.open(a.input/"final-neutral/side03_detail.png") as img:
        img.convert("RGB").save(a.output/"side-study-03.webp",quality=95)
    board=Image.new("RGB",(1512,1172),"#0d151b")
    d=ImageDraw.Draw(board)
    d.text((24,20),"KUHAI / BRIDGE SIDE STRUCTURE 03",font=font(29),fill="#e1e6e9")
    d.text((24,64),"MATCHED NEUTRAL LIGHT / FIXED CAMERAS / ACTUAL 3D GEOMETRY",font=font(16),fill="#b9a582")
    for col,(directory,label) in enumerate((("previous","BEFORE / SOLID SUPPORT"),("final-neutral","AFTER / RECESSED SERVICE BAYS"))):
        x=24+col*744
        d.text((x,108),label,font=font(20),fill="#cfbaa0" if col else "#9caab3")
        for row,view in enumerate(("side03_detail","side03_context")):
            y=149+row*496
            with Image.open(a.input/directory/(view+".png")) as img:
                board.paste(img.convert("RGB").resize((720,450),Image.Resampling.LANCZOS),(x,y))
            d.text((x,y+460),"SERVICE EQUIPMENT + LOAD CONNECTIONS" if row==0 else "SAME BRIDGE / PORT-SIDE SAMPLE ONLY",font=font(15),fill="#c0c9ce")
    d.text((24,1138),"CPU Cycles / 960 x 600 / 32 samples / Structural sample, coating and full-ship detailing remain in progress",font=font(15),fill="#93a2aa")
    board.save(a.output/"side-study-03-comparison.webp",quality=94)


if __name__=="__main__":
    main()

