"""Lay out unchanged renders and quantify one controlled far-detail comparison."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw
from integration_review import font, frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    current,previous = args.input/"current",args.input/"previous"
    sheet = Image.new("RGB",(1008,1140),"#0b1319")
    d = ImageDraw.Draw(sheet)
    d.text((24,20),"KUHAI / SURFACE STUDY 03",font=font(29),fill="#e4e8e9")
    d.text((24,65),"LONGITUDINAL PLATES / QUIET FAR VIEW / SERVICE DETAILS AT CLOSE RANGE",font=font(15),fill="#c9b38e")
    d.text((24,90),"01 / ORBITAL OVERVIEW",font=font(16),fill="#bbc8cc")
    with Image.open(current/"overview.png") as image:
        if image.size!=(960,600):raise ValueError("Expected 960 x 600 overview")
        sheet.paste(image.convert("RGB"),(24,118))
    for x,name,label in ((24,"surface_bow","02 / BOW PLATE RHYTHM"),(516,"surface_archive","03 / ARCHIVE SERVICE STRIP")):
        d.text((x,746),label,font=font(16),fill="#bbc8cc")
        with Image.open(current/(name+".png")) as image:
            sheet.paste(image.convert("RGB").resize((468,293),Image.Resampling.LANCZOS),(x,774))
    d.text((24,1098),"Cycles CPU / unchanged cameras + lighting / editable study, not final art",font=font(16),fill="#90a4ae")
    sheet.save(args.output/"surface-study-03.webp",quality=94)

    comparison = Image.new("RGB",(1512,1172),"#0b1319")
    d = ImageDraw.Draw(comparison)
    d.text((24,20),"KUHAI / PANEL RHYTHM — BEFORE AND AFTER",font=font(29),fill="#e4e8e9")
    d.text((24,65),"IDENTICAL CAMERAS + LIGHTING / SOURCE HARDWARE AND ROOM UNCHANGED",font=font(16),fill="#c9b38e")
    for row,name in enumerate(("surface_bow","surface_archive")):
        for col,(directory,label) in enumerate(((previous,"SURFACE 02 / PREVIOUS"),(current,"SURFACE 03 / REVISED"))):
            x,y = 24+744*col,110+504*row
            d.text((x,y),label,font=font(17),fill="#bbc8cc")
            frame(comparison,directory,name,x,y+30)
    d.text((24,1134),"47 local plates > 23 / nominal coplanar gap 0.20 m / provisional visual scale",font=font(16),fill="#90a4ae")
    comparison.save(args.output/"surface-study-03-comparison.webp",quality=94)

    with Image.open(args.input/"small-full/overview.png") as f,Image.open(args.input/"small-far/overview.png") as l:
        full,far = f.convert("RGB"),l.convert("RGB")
    if full.size!=(384,240) or far.size!=full.size:raise ValueError("Expected matched 384 x 240 images")
    delta = list(ImageChops.difference(full,far).get_flattened_data())
    per_pixel = [max(rgb) for rgb in delta]
    record = {"resolution":[384,240],"camera":"overview","method":"Compare 8-bit RGB output of two matched Cycles renders",
              "whole_image_mae_255":sum(sum(rgb) for rgb in delta)/(len(delta)*3),
              "pixels_max_channel_delta_gt_2":sum(value>2 for value in per_pixel),
              "pixels_total":len(per_pixel),"max_channel_delta":max(per_pixel),
              "limitations":"Single static image; includes sampling noise. Not browser FPS, motion, LOD popping or GPU validation."}
    (args.output/"far-detail-comparison.json").write_text(json.dumps(record,indent=2)+"\n")
    strip = Image.new("RGB",(816,388),"#0b1319")
    d = ImageDraw.Draw(strip)
    d.text((16,18),"KUHAI / SMALL-WIDTH DETAIL TEST",font=font(23),fill="#e4e8e9")
    d.text((16,61),"FULL SOURCE HARDWARE",font=font(15),fill="#bbc8cc")
    d.text((416,61),"TINY HARDWARE OMITTED",font=font(15),fill="#bbc8cc")
    strip.paste(full,(16,88));strip.paste(far,(416,88))
    d.text((16,345),"384 x 240 at native pixels / static visual test / no browser performance claim",font=font(14),fill="#90a4ae")
    strip.save(args.output/"surface-study-03-small-width.webp",quality=96)
    print(json.dumps(record,indent=2))


if __name__=="__main__":
    main()
