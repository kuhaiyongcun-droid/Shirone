"""Create an engineering comparison board from existing renders; Pillow 12.3.0."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--current", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGB", (1512, 1172), "#0c141a")
    d = ImageDraw.Draw(sheet)
    d.text((24, 20), "KUHAI / LOCAL MATERIAL STUDY 01", font=font(31), fill="#e2e7e8")
    d.text((24, 66), "COATED ARMOR + METAL EDGES + RECESSED ENGINE / NOT FINAL ART", font=font(16), fill="#c6ae89")
    for col, (directory, label) in enumerate(((a.baseline, "BLOCKOUT 02 / LOCAL LIGHT RIG"),
                                             (a.current, "MATERIAL STUDY / SAME LIGHT RIG"))):
        x = 24 + 744 * col
        d.text((x, 111), label, font=font(20), fill="#d7bb8d" if col else "#a8b7bf")
        for row, (view, caption) in enumerate((("shoulder", "01  SHOULDER / SURFACE + ASSEMBLY"),
                                               ("engine", "02  ENGINE / REAL CAVITY + LAYERED LIGHT"))):
            y = 149 + row * 496
            with Image.open(directory / (view + ".png")) as image:
                if image.size != (960, 600):
                    raise ValueError("Expected the matched 960 x 600 source frames")
                sheet.paste(image.convert("RGB").resize((720, 450), Image.Resampling.LANCZOS), (x, y))
            d.text((x, y + 458), caption, font=font(15), fill="#bec9cf")
    d.line((24, 1121, 1488, 1121), fill="#35434c")
    d.text((24, 1138), "Cycles CPU / 960 x 600 / 32 samples | Matching cameras + lights | Source renders resized only", font=font(15), fill="#92a2ab")
    sheet.save(a.output, quality=92)


if __name__ == "__main__":
    main()
