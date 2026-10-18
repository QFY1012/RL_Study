"""把一张整页截图从上到下切成等高的块(JPEG),给看不了超长图的模型。contrast-rubric.mjs 调用。

    python3 tile-shot.py <整页截图> <输出前缀> [块高 1440]

写出 <输出前缀>-1.jpg、-2.jpg……,打印块数。最后一块不足块高时照原样(不补白)。
"""
import sys
from PIL import Image

src, prefix = sys.argv[1:3]
step = int(sys.argv[3]) if len(sys.argv) > 3 else 1440
im = Image.open(src).convert("RGB")
n = 0
for top in range(0, im.height, step):
    n += 1
    im.crop((0, top, im.width, min(top + step, im.height))).save(f"{prefix}-{n}.jpg", quality=85)
print(n)
