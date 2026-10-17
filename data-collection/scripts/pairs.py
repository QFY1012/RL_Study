# Checks the renders of one recorded page and cuts out the pairs.
#   python3 -I scripts/pairs.py <dir>
# Isolation: for each swapped section, the page above it must be unchanged and the
# page below it the same once shifted by the height difference.
# Writes pairs/<i>-orig.png and pairs/<i>-gen.png (the section with MARGIN px of
# page above and below), pairs/<i>-side.png (both side by side, for looking at) and
# pairs/report.json, which lists for each pair the checks it failed (none: usable).
import json, os, sys
from PIL import Image, ImageChops, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None
MARGIN = 300
# A pair is usable only if every check passes: the page around the section is
# unchanged (at most ISOLATION of its rows differ), and the content is all there.
ISOLATION = 0.01

d = sys.argv[1]
r = os.path.join(d, "render")
out = os.path.join(d, "pairs")
os.makedirs(out, exist_ok=True)


def differs(a, b):
    """Share of pixel rows that differ between two equally sized images, and the first one."""
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L").point(lambda v: 255 if v > 16 else 0)
    rows = [y for y in range(diff.height) if diff.crop((0, y, diff.width, y + 1)).getbbox()]
    return (len(rows) / max(diff.height, 1), rows[0] if rows else None)


def band(img, top, bottom):
    return img.crop((0, max(top, 0), img.width, min(bottom, img.height)))


orig = Image.open(os.path.join(r, "orig.png"))
ob = json.load(open(os.path.join(r, "orig.json")))["boxes"]
report = {"pairs": {}}

font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
font = ImageFont.truetype(font_path, 22) if os.path.exists(font_path) else ImageFont.load_default()

for f in sorted(os.listdir(r)):
    if not f.endswith(".json") or f == "orig.json":
        continue
    sec = f[:-5]
    meta = json.load(open(os.path.join(r, f)))
    gen = Image.open(os.path.join(r, f"{sec}.png"))
    o, g = ob[sec], meta["boxes"][sec]
    above, _ = differs(band(orig, 0, o["y"]), band(gen, 0, g["y"])) if o["y"] == g["y"] else (1.0, None)
    below_o, below_g = band(orig, o["y"] + o["h"], orig.height), band(gen, g["y"] + g["h"], gen.height)
    n = min(below_o.height, below_g.height)
    below, _ = differs(band(below_o, 0, n), band(below_g, 0, n))
    a = band(orig, o["y"] - MARGIN, o["y"] + o["h"] + MARGIN)
    b = band(gen, g["y"] - MARGIN, g["y"] + g["h"] + MARGIN)
    a.save(os.path.join(out, f"{sec}-orig.png"))
    b.save(os.path.join(out, f"{sec}-gen.png"))
    pad, top = 32, 56
    side = Image.new("RGB", (a.width + b.width + pad * 3, max(a.height, b.height) + top + pad), "white")
    draw = ImageDraw.Draw(side)
    draw.text((pad, 16), f"section {sec}: original", fill="black", font=font)
    draw.text((a.width + pad * 2, 16), f"section {sec}: generated ({MARGIN}px of page above and below)", fill="black", font=font)
    side.paste(a, (pad, top))
    side.paste(b, (a.width + pad * 2, top))
    side.save(os.path.join(out, f"{sec}-side.png"))
    entry = {"orig_box": o, "gen_box": g, "above_rows_differing": round(above, 3), "below_rows_differing": round(below, 3), **meta["checks"]}
    entry["failed"] = [name for name, bad in [
        ("isolation", above > ISOLATION or below > ISOLATION),
        ("text", bool(entry["missingText"])),
        ("images", bool(entry["missingImages"] or entry["brokenImages"])),
        ("overflow", entry["overflow"] > 0),
        ("fonts", bool(entry["fontsMissing"])),
    ] if bad]
    report["pairs"][sec] = entry
    print(f"section {sec}: {'ok' if not entry['failed'] else 'FAILED ' + ', '.join(entry['failed'])} (above differs {above:.1%}, below {below:.1%}, missing text {len(entry['missingText'])}, missing images {len(entry['missingImages'])}, overflow {entry['overflow']})")

json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=1)
