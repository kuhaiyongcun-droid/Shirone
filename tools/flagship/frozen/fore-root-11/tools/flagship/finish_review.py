"""Compose unretouched CPU renders into matched review sheets."""
import argparse
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

FONT=next((str(p) for p in (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
    Path('C:/Windows/Fonts/arial.ttf'),Path('/System/Library/Fonts/Helvetica.ttc')) if p.exists()),None)
def font(size):return ImageFont.truetype(FONT,size)
def text(d,pos,value,size=24,color='#aebbc3'):d.text(pos,value,font=font(size),fill=color)
def paste(board,path,pos,size=(960,600)):
    with Image.open(path) as im:
        board.paste(im.convert('RGB').resize(size,Image.Resampling.LANCZOS),pos)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    board=Image.new('RGB',(1992,1470),'#0d151b');d=ImageDraw.Draw(board)
    text(d,(24,20),'KUHAI / PORT SERVICE FINISH 04',35,'#e1e7ea')
    text(d,(24,72),'Same cameras / matched neutral light / actual editable 3D geometry',22,'#c3b093')
    for col,(folder,heading) in enumerate((('final-before','RECOVERED SIDE03'),('final-neutral','SIDE04 / CASINGS + FINISH'))):
        x=24+984*col
        text(d,(x,120),heading,26,'#c9b695' if col else '#9babb5')
        for row,view in enumerate(('side03_detail','side03_context')):
            y=164+row*632
            paste(board,a.input/folder/(view+'.png'),(x,y))
    text(d,(24,1415),'Restored baseline is a verified reconstruction. Coatings and full-ship art remain in development.',21)
    board.save(a.output/'kuhai-side-finish-04-comparison.webp',quality=95)

    board=Image.new('RGB',(1992,1470),'#0d151b');d=ImageDraw.Draw(board)
    text(d,(24,20),'KUHAI / SCALE + LIGHT CHECK',35,'#e1e7ea')
    text(d,(24,72),'Geometry and surface review / CPU Cycles / no generated-image replacement',22,'#c3b093')
    for col,folder,view,heading in ((0,'final-neutral','side03_reverse','REVERSE / NEUTRAL'),(1,'final-rim','side03_context','BRIDGE / EXISTING ATMOSPHERE')):
        x=24+984*col;text(d,(x,120),heading,26)
        paste(board,a.input/folder/(view+'.png'),(x,164))
    text(d,(24,793),'WHOLE SHIP / LOCAL CHANGE IN CONTEXT',24)
    paste(board,a.input/'final-rim/home.png',(516,840),(960,600))
    board.save(a.output/'kuhai-side-finish-04-views.webp',quality=95)
    with Image.open(a.input/'final-neutral/side03_detail.png') as im:
        im.convert('RGB').save(a.output/'kuhai-side-finish-04.webp',quality=96)

if __name__=='__main__':main()
