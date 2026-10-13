"""Lay out matched raw renders without retouching, using Pillow 12.3.0."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def frame(sheet, directory, name, x, y):
    with Image.open(directory / (name + ".png")) as source:
        if source.size != (960, 600):
            raise ValueError("Expected matched 960 x 600 input frames")
        sheet.paste(source.convert("RGB").resize((720, 450), Image.Resampling.LANCZOS), (x, y))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--current", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGB", (1512, 1172), "#0b1319")
    d = ImageDraw.Draw(sheet)
    d.text((24, 20), "KUHAI / WHOLE-SHIP INTEGRATION 01", font=font(30), fill="#e4e8e9")
    d.text((24, 66), "MATCHED CAMERAS + ORBITAL LIGHTING / PRODUCTION STUDY, NOT FINAL ART", font=font(16), fill="#c9b38e")
    for col, (directory, label) in enumerate(((a.baseline, "BLOCKOUT 02 / CURRENT LIGHT RIG"),
                                             (a.current, "INTEGRATED MATERIALS / SAME LIGHT RIG"))):
        x = 24 + col * 744
        d.text((x, 111), label, font=font(18), fill="#bbc8cc")
        for row, name in enumerate(("overview", "stern")):
            y = 149 + row * 496
            frame(sheet, directory, name, x, y)
            d.text((x, y + 458), "01 / ORBITAL OVERVIEW" if row == 0 else "02 / RECESSED ENGINE GROUPS", font=font(15), fill="#b4c3ca")
    d.line((24, 1121, 1488, 1121), fill="#33414b")
    d.text((24, 1138), "Cycles CPU / 960 x 600 / 32 samples | Comparison changes ship visibility only", font=font(15), fill="#90a4ae")
    sheet.save(a.output / "integration-study-01-comparison.webp", quality=92)
    hero = Image.new("RGB", (1512, 630), "#0b1319")
    d = ImageDraw.Draw(hero)
    d.text((24, 20), "KUHAI / ORBITAL STUDY 01", font=font(30), fill="#e4e8e9")
    d.text((24, 68), "WHOLE-SHIP MATERIALS + SHARED STELLAR LIGHT / NOT FINAL ART", font=font(16), fill="#c9b38e")
    for col, name in enumerate(("overview", "stern")):
        x = 24 + 744 * col
        frame(hero, a.current, name, x, 115)
        d.text((x, 579), "01 / PLANET-SIDE OVERVIEW" if col == 0 else "02 / AFT ENGINE STRUCTURE", font=font(17), fill="#bbc8cc")
    hero.save(a.output / "integration-study-01.webp", quality=93)


if __name__ == "__main__":
    main()
