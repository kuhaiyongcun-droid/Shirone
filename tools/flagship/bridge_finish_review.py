"""Arrange unretouched bridge/coating renders; requires Pillow 12.3.0."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageStat

from integration_review import font, frame


def paste_image(board, path, xy, size):
    with Image.open(path) as img:
        board.paste(img.convert("RGB").resize(size, Image.Resampling.LANCZOS), xy)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--sample", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    current, previous = a.input/"current", a.input/"previous"
    sheet = Image.new("RGB", (1008, 1140), "#0b1319")
    d = ImageDraw.Draw(sheet)
    d.text((24, 20), "KUHAI / BRIDGE STUDY 02", font=font(29), fill="#e4e8e9")
    d.text((24, 64), "SIDE ARMOR / SERVICE HARDWARE / COATING SAMPLE", font=font(17), fill="#c9b38e")
    d.text((24, 92), "01 / FITTED SIDE ARMOR AND DORSAL CONNECTION", font=font(16), fill="#bbc8cc")
    paste_image(sheet, current/"bridge_side.png", (24, 118), (960, 600))
    for x, name, label in ((24, "bridge_finish_lit", "02 / INSPECTION COVER"),
                           (516, "overview", "03 / WHOLE-SHIP CONTEXT")):
        d.text((x, 746), label, font=font(16), fill="#bbc8cc")
        paste_image(sheet, current/(name+".png"), (x, 774), (468, 293))
    d.text((24, 1098), "Editable local study / original lighting retained / not final ship artwork", font=font(15), fill="#90a4ae")
    sheet.save(a.output/"bridge-study-02.webp", quality=94)

    board = Image.new("RGB", (1512, 1698), "#0b1319")
    d = ImageDraw.Draw(board)
    d.text((24, 20), "KUHAI / STRUCTURE AND COATING COMPARISON", font=font(29), fill="#e4e8e9")
    d.text((24, 65), "STRUCTURE: IDENTICAL CAMERAS + LIGHTING / COATING: SEPARATE NEUTRAL RIG", font=font(17), fill="#c9b38e")
    for row, name in enumerate(("bridge_side", "bridge_rear")):
        for col, (directory, label) in enumerate(((previous, "BRIDGE 01 / PREVIOUS"), (current, "BRIDGE 02 / REVISED"))):
            x, y = 24+744*col, 110+504*row
            d.text((x, y), label, font=font(17), fill="#bbc8cc")
            frame(board, directory, name, x, y+30)
    for i, (name, label) in enumerate((("cover-source", "PROCEDURAL SOURCE"), ("cover-baked", "BAKED PBR"), ("cover-glb-roundtrip", "GLB REIMPORTED"))):
        x = 24+i*492
        d.text((x, 1138), label, font=font(17), fill="#bbc8cc")
        paste_image(board, a.sample/(name+".png"), (x, 1172), (468, 468))
    d.text((24, 1660), "Cover-only sample / fasteners excluded / 1K embedded maps / offline validation, no browser FPS claim", font=font(16), fill="#90a4ae")
    board.save(a.output/"bridge-study-02-comparison.webp", quality=94)

    images = {}
    for name in ("cover-source", "cover-baked", "cover-glb-roundtrip"):
        with Image.open(a.sample/(name+".png")) as img:
            images[name] = img.convert("RGB")
    metrics = {"scope": "Whole 512x512 matched offline renders, including background; not a perceptual or browser benchmark"}
    for name in ("cover-baked", "cover-glb-roundtrip"):
        error = ImageChops.difference(images[name], images["cover-source"])
        histogram = error.histogram()
        distribution = [sum(histogram[v+channel*256] for channel in range(3)) for v in range(256)]
        target, cumulative, percentile = sum(distribution)*.95, 0, 0
        for value, count in enumerate(distribution):
            cumulative += count
            if cumulative >= target:
                percentile = value
                break
        metrics[name] = {"mean_absolute_error_8bit": sum(ImageStat.Stat(error).mean)/3,
                         "p95_absolute_error_8bit": percentile}
    (a.output/"coating-image-comparison.json").write_text(json.dumps(metrics, indent=2)+"\n")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
