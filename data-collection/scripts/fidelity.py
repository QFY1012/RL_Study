# Checks, section by section, that the offline render of the original matches the live page.
#   python3 -I scripts/fidelity.py <snapshot-dir>
# Each section is compared with MARGIN px of page above and below (the part a pair
# shows): live.png at the box measured on the live page against render/orig.png at
# the box measured offline. A section is usable when the boxes have the same height
# and at most LIMIT of the rows differ. Writes fidelity.json; generate.mjs only picks
# usable sections.
import json, os, sys
from PIL import Image, ImageChops

Image.MAX_IMAGE_PIXELS = None
MARGIN = 300
LIMIT = 0.03

d = sys.argv[1]
live = Image.open(os.path.join(d, "live.png")).convert("RGB")
orig = Image.open(os.path.join(d, "render", "orig.png")).convert("RGB")
live_boxes = {str(s["i"]): s["box"] for s in json.load(open(os.path.join(d, "sections.json")))["sections"]}
orig_boxes = json.load(open(os.path.join(d, "render", "orig.json")))["boxes"]


def rows_differing(a, b):
    diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 16 else 0)
    return sum(1 for y in range(diff.height) if diff.crop((0, y, diff.width, y + 1)).getbbox()) / max(diff.height, 1)


def band(img, y, h):
    top, bottom = max(y - MARGIN, 0), min(y + h + MARGIN, img.height)
    return img.crop((0, top, img.width, bottom))


sections = {}
for i, lb in live_boxes.items():
    ob = orig_boxes.get(i)
    if ob is None or abs(ob["h"] - lb["h"]) > 1:
        sections[i] = {"ok": False, "why": "height", "live_h": lb["h"], "offline_h": ob and ob["h"]}
    else:
        a, b = band(live, lb["y"], lb["h"]), band(orig, ob["y"], ob["h"])
        n = min(a.height, b.height)
        share = rows_differing(a.crop((0, 0, a.width, n)), b.crop((0, 0, b.width, n)))
        sections[i] = {"ok": share <= LIMIT, "rows_differing": round(share, 3), **({} if share <= LIMIT else {"why": "pixels"})}
    s = sections[i]
    print(f"section {i}: {'ok' if s['ok'] else 'not faithful (' + s['why'] + ')'}" + (f", {s['rows_differing']:.1%} of rows differ" if "rows_differing" in s else f", live {s['live_h']}px, offline {s['offline_h']}px"))

json.dump({"live_height": live.height, "offline_height": orig.height, "sections": sections}, open(os.path.join(d, "fidelity.json"), "w"), indent=1)
print(f"{sum(s['ok'] for s in sections.values())}/{len(sections)} sections render faithfully")
