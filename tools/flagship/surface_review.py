"""Arrange unretouched matched render frames into review sheets; Pillow only."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw
from integration_review import font, frame


def sheet(title, subtitle, rows, output):
    height = 148 + 504 * len(rows)
    canvas = Image.new("RGB", (1512,height), "#0b1319")
    draw = ImageDraw.Draw(canvas)
    draw.text((24,20), title, font=font(30), fill="#e4e8e9")
    draw.text((24,65), subtitle, font=font(16), fill="#c9b38e")
    for row,columns in enumerate(rows):
        for col,(directory,name,label) in enumerate(columns):
            x,y = 24+col*744,110+row*504
            draw.text((x,y), label, font=font(17), fill="#bbc8cc")
            frame(canvas,directory,name,x,y+30)
    draw.text((24,height-26), "Cycles CPU / 960 x 600 / 32 samples | Local material study, not final art",
              font=font(15), fill="#90a4ae")
    canvas.save(output,quality=94)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    current,baseline,cutaway = [a.input/n for n in ("final-renders","baseline-renders","cutaway-renders")]
    sheet("KUHAI / LOCAL ARMOR SURFACE STUDY 02", "EDITABLE PLATE LAYERS / QUIET PAINT / SERVICE HARDWARE",
          [[(current,"surface_bow","01 / BOW UPPER ARMOR"),(current,"surface_shoulder","02 / FORWARD SHOULDER")],
           [(current,"surface_archive","03 / REMOVABLE ARCHIVE ROOF"),(current,"surface_hatch","04 / MAINTENANCE COVER + CAPTIVE LOCKS")]],
          a.output/"surface-study-02.webp")
    sheet("KUHAI / MATCHED BEFORE AND AFTER", "FIXED CAMERAS + LIGHTING / ONLY NEW SURFACE COLLECTIONS TOGGLED",
          [[(baseline,view,"FORM 03 / "+label),(current,view,"SURFACE 02 / "+label)]
           for view,label in (("surface_bow","BOW"),("surface_shoulder","SHOULDER"),("surface_archive","ARCHIVE"))],
          a.output/"surface-study-02-comparison.webp")
    sheet("KUHAI / ARCHIVE SHELL OWNERSHIP", "ALL NEW ROOF DETAILS FOLLOW THE CUTAWAY / INTERIOR UNCHANGED",
          [[(current,"surface_archive","CLOSED / LAYERED SHELL"),(cutaway,"surface_archive","OPEN / INTERIOR CLEARANCE")]],
          a.output/"surface-study-02-structure.webp")


if __name__ == "__main__":
    main()
