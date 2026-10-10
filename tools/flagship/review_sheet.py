"""Lay out unchanged study renders for review; requires Pillow 12.3.0.

python review_sheet.py --before previous/renders --after current/renders --output previews
No image enhancement, color grading, cropping or generated replacement pixels.
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (1512, 1172), "#0f171c")
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 20), "KUHAI / FORM STUDY 02", font=font(31), fill="#e1e6e9")
    draw.text((24, 66), "SAME CAMERAS + LIGHTS / PROVISIONAL GEOMETRY / NOT FINAL ART", font=font(16), fill="#b9a582")
    for col, (directory, label) in enumerate(((args.before, "01  /  PREVIOUS"), (args.after, "02  /  REVISED"))):
        x = 24 + col * 744
        draw.text((x, 108), label, font=font(22), fill="#ebc894" if col else "#9caab3")
        for row, (view, caption) in enumerate((("hero", "BOW + SHOULDER MASS"), ("rear", "OUTBOARD PROPULSION + DECK DEPTH"))):
            y = 149 + row * 496
            with Image.open(directory / (view + ".png")) as source:
                if source.size != (720, 450):
                    raise ValueError("Comparison requires the matching 720 x 450 study frames")
                canvas.paste(source.convert("RGB"), (x, y))
            draw.text((x, y + 457), caption, font=font(15), fill="#c0c9ce")
    draw.line((24, 1121, 1488, 1121), fill="#35434c")
    draw.text((24, 1138), "Cycles CPU / 720 x 450 / 24 samples | Fixed cameras + lights / Matching settings / Unretouched frames", font=font(15), fill="#93a2aa")
    canvas.save(args.output / "blockout-02-comparison.webp", quality=90)

    sheet = Image.new("RGB", (1512, 1218), "#0f171c")
    draw = ImageDraw.Draw(sheet)
    draw.text((24, 20), "KUHAI / STRUCTURE CHECKS 02", font=font(31), fill="#e1e6e9")
    draw.text((24, 67), "ORTHOGRAPHIC VIEWS + LOCAL CUTAWAY / NOT FINAL ART", font=font(16), fill="#b9a582")
    for index, (view, caption) in enumerate((("top", "PLAN / TWO SHOULDER GROUPS"), ("side", "PROFILE / CHAMFERED HULL + LAYERED DECKS"),
                                             ("belly", "VENTRAL STRUCTURE / INCOMPLETE SYSTEM DESIGN"),
                                             ("archive_context", "ARCHIVE / SAME ROOM + INDEPENDENT SHELL"))):
        x, y = 24 + index % 2 * 744, 111 + index // 2 * 516
        with Image.open(args.after / (view + ".png")) as source:
            sheet.paste(source.convert("RGB"), (x, y))
        draw.text((x, y + 460), caption, font=font(15), fill="#c0c9ce")
    draw.text((24, 1165), "Editable source + separate GLB | Whole-ship scale and compartment location remain design assumptions", font=font(15), fill="#93a2aa")
    sheet.save(args.output / "blockout-02-views.webp", quality=90)


if __name__ == "__main__":
    main()
