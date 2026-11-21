"""Draw the cow favicon and write map/favicon.ico (16, 32, 48 and 64 px).

Usage:
    uv run --with pillow python assets/make_favicon.py [out_dir]
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw
N = 512
img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
INK = (40, 32, 28, 255); WHITE = (250, 248, 242, 255); PINK = (240, 160, 165, 255)
HORN = (232, 214, 170, 255); W = 14
# horns
d.polygon([(175, 140), (95, 30), (60, 60), (115, 165)], fill=HORN, outline=INK, width=W)
d.polygon([(337, 140), (417, 30), (452, 60), (397, 165)], fill=HORN, outline=INK, width=W)
# ears
d.ellipse((10, 150, 160, 240), fill=WHITE, outline=INK, width=W)
d.ellipse((352, 150, 502, 240), fill=WHITE, outline=INK, width=W)
d.ellipse((40, 175, 130, 215), fill=PINK)
d.ellipse((382, 175, 472, 215), fill=PINK)
# head
d.rounded_rectangle((110, 110, 402, 440), radius=120, fill=WHITE, outline=INK, width=W)
# patches (clipped to the head)
mask = Image.new("L", (N, N), 0)
ImageDraw.Draw(mask).rounded_rectangle((117, 117, 395, 433), radius=114, fill=255)
spots = Image.new("RGBA", (N, N), (0, 0, 0, 0))
sd = ImageDraw.Draw(spots)
sd.ellipse((90, 90, 230, 250), fill=INK)
sd.ellipse((320, 150, 440, 235), fill=INK)
img.paste(spots, (0, 0), Image.composite(spots.getchannel("A"), Image.new("L", (N, N), 0), mask))
# eyes
d.ellipse((175, 245, 215, 290), fill=INK)
d.ellipse((297, 245, 337, 290), fill=INK)
# muzzle
d.rounded_rectangle((135, 325, 377, 485), radius=80, fill=PINK, outline=INK, width=W)
d.ellipse((190, 380, 225, 425), fill=INK)
d.ellipse((287, 380, 322, 425), fill=INK)
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "map"
img.save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
