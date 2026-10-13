"""Original maintenance print masks, drawn at precise panel coordinates."""
from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
out=Path(__file__).parent/'source-textures'
font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
for unit in (1,2):
 im=Image.new('RGB',(1024,576),'black');d=ImageDraw.Draw(im)
 # Print lies in the free strips on either side of the existing handle/status row.
 d.text((152,90),f'PCU / 0{unit}',font=ImageFont.truetype(font,36),fill=(210,210,210))
 d.text((152,139),'THERMAL CONDITIONING',font=ImageFont.truetype(font,18),fill=(160,160,160))
 d.line((152,176,473,176),fill=(125,125,125),width=2)
 d.text((584,396),'ISOLATE BEFORE OPENING',font=ImageFont.truetype(font,17),fill=(170,170,170))
 d.text((584,423),'RPL 02' if unit==2 else 'REV 01',font=ImageFont.truetype(font,24),fill=(185,185,185))
 d.rectangle((587,372,617,381),fill=(150,150,150));d.rectangle((629,372,659,381),fill=(150,150,150))
 im.save(out/f'fore09-panel-{unit}-print.png')
