"""Arrange original home-look renders without retouching lighting or pixels."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw
from integration_review import font


def paste(board, path, xy, size):
    with Image.open(path) as image:
        board.paste(image.convert("RGB").resize(size, Image.Resampling.LANCZOS), xy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with Image.open(args.input/"hero/home.png") as image:
        if image.size != (1280, 800):
            raise ValueError("Expected a 1280 x 800 hero")
        image.convert("RGB").save(args.output/"home-look-01.webp", quality=95)
    board = Image.new("RGB", (1512, 1192), "#0b1319")
    draw = ImageDraw.Draw(board)
    draw.text((24, 20), "KUHAI / HOME LOOK 01", font=font(30), fill="#e4e8e9")
    draw.text((24, 68), "FIXED CAMERA / SAME GEOMETRY / CONTROLLED FINISH + LIGHTING COMPARISONS", font=font(17), fill="#c9b38e")
    cases = [
        ("baseline", "01 / ORIGINAL", "Original finish, original lighting and planet"),
        ("materials", "02 / FINISH ONLY", "New exterior finish; original lighting and planet"),
        ("day", "03 / DAYLIGHT STUDY", "New finish, reduced planet and neutral stellar key"),
        ("current", "04 / SELECTED RIM STUDY", "New finish, warm backlight and cool art fill"),
    ]
    for i, (directory, title, note) in enumerate(cases):
        x, y = 24+(i % 2)*744, 114+(i//2)*516
        draw.text((x, y), title, font=font(19), fill="#dce5e7")
        paste(board, args.input/directory/"home.png", (x, y+30), (720, 450))
        draw.text((x, y+488), note, font=font(14), fill="#9bb0bb")
    draw.text((24, 1158), "Unretouched Cycles previews / creative interpretation / source scene remains editable", font=font(16), fill="#90a4ae")
    board.save(args.output/"home-look-01-comparison.webp", quality=94)

    views = Image.new("RGB", (1512, 988), "#0b1319")
    draw = ImageDraw.Draw(views)
    draw.text((24, 20), "KUHAI / LOOK VALIDATION", font=font(30), fill="#e4e8e9")
    draw.text((24, 68), "FIXED PORTRAIT COMPOSITION / BRIDGE FINISH / RETAINED ENGINE LIGHTS", font=font(17), fill="#c9b38e")
    paste(views, args.input/"portrait/home_portrait.png", (24, 122), (510, 816))
    for i, (name, title) in enumerate((("finish_detail", "BRIDGE / PAINT + ALLOY"), ("stern", "STERN / ORIGINAL EMISSION RETAINED"))):
        y = 122+i*408
        draw.text((558, y), title, font=font(17), fill="#c9b38e")
        paste(views, args.input/"details"/(name+".png"), (558, y+30), (585, 366))
    draw.text((1170, 160), "PORTRAIT", font=font(18), fill="#dce5e7")
    for i, line in enumerate(("A fixed camera", "for narrow screens.", "", "Fixed still cameras.", "", "Offline composition;", "browser testing", "is still pending.")):
        draw.text((1170, 205+i*26), line, font=font(16), fill="#9bb0bb")
    views.save(args.output/"home-look-01-views.webp", quality=94)
    print("Created clean hero, controlled comparisons and composition checks")


if __name__ == "__main__":
    main()
