# Cuts the pairs out of the renders of one recorded page and records their checks.
#   python3 -I scripts/pairs.py <dir>
# A generated section has the original's box, so the generated image is the original
# screenshot with only that box's pixels taken from the render with the section
# swapped in: everything around it is the original's own pixels. How much the page
# around the box did change in that render (scripts reacting to the swap, say) is
# recorded as above/below_rows_differing, for information.
# Writes pairs/<i>-orig.png and pairs/<i>-gen.png (the section with MARGIN px of
# page above and below), pairs/<i>-side.png (both side by side, for looking at) and
# pairs/report.json, which lists for each pair the checks it failed (none: usable), and
# pairs/<i>-gen.jpg, the generated image at half size, which generate.mjs --revise shows
# the model so it sees what it made.
# Seam: the generated image must join the page the way the original does, or a judge
# could tell the two apart by the edge of the box alone. For each side of the box, the
# line of pixels just outside it is compared with the line just inside: the share that
# differ is how much the page breaks there. The original's own break is subtracted (a
# card it has flush with the edge is not a seam), and what is left, if more than SEAM
# on any side, fails the pair (run.mjs then sends it back to the model). A side on the
# edge of the page has nothing outside it and is not measured.
# Replay: the section must have come back the same as recorded (replay.json, written by
# the render that made these images); otherwise what the model was given is not what
# the original image shows.
import json, os, sys
from PIL import Image, ImageChops, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None
MARGIN = 300
SEAM = 0.02

d = sys.argv[1]
r = os.path.join(d, "render")
out = os.path.join(d, "pairs")
os.makedirs(out, exist_ok=True)


def differs(a, b):
    """Share of pixel rows that differ between two equally sized images."""
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L").point(lambda v: 255 if v > 16 else 0)
    return sum(1 for y in range(diff.height) if diff.crop((0, y, diff.width, y + 1)).getbbox()) / max(diff.height, 1)


def changed(a, b):
    """Share of pixels that differ between two equally sized images. Both come from the
    same lossless render, so pixels left alone match exactly; a faint tint (a near-white
    panel on white) is just what shows as a seam, so the threshold is low."""
    diff = ImageChops.difference(a, b).point(lambda v: 255 if v > 2 else 0).convert("L").point(lambda v: 255 if v else 0)
    return diff.histogram()[255] / max(diff.width * diff.height, 1)


def band(img, top, bottom):
    return img.crop((0, max(top, 0), img.width, min(bottom, img.height)))


replay = json.load(open(os.path.join(d, "replay.json")))
orig = Image.open(os.path.join(r, "orig.png")).convert("RGB")
ob = json.load(open(os.path.join(r, "orig.json")))["boxes"]
report = {"pairs": {}}

font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
font = ImageFont.truetype(font_path, 22) if os.path.exists(font_path) else ImageFont.load_default()

for f in sorted(os.listdir(r)):
    if not (f.endswith(".json") and f[:-5].isdigit()):  # render/<i>.json, one per generated section
        continue
    sec = f[:-5]
    meta = json.load(open(os.path.join(r, f)))
    rendered = Image.open(os.path.join(r, f"{sec}.png")).convert("RGB")
    o = ob[sec]
    top, bottom = o["y"], o["y"] + o["h"]
    above = differs(band(orig, 0, top), band(rendered, 0, top))
    below = differs(band(orig, bottom, orig.height), band(rendered, bottom, orig.height)) if rendered.height == orig.height else 1.0
    gen = orig.copy()
    gen.paste(rendered.crop((0, top, rendered.width, bottom)), (0, top))
    left, right = o["x"], o["x"] + o["w"]
    # (line just outside the box, line just inside), for each side that has an outside
    sides = {side: lines for side, lines, there in [
        ("top", ((left, top - 1, right, top), (left, top, right, top + 1)), top > 0),
        ("bottom", ((left, bottom, right, bottom + 1), (left, bottom - 1, right, bottom)), bottom < orig.height),
        ("left", ((left - 1, top, left, bottom), (left, top, left + 1, bottom)), left > 0),
        ("right", ((right, top, right + 1, bottom), (right - 1, top, right, bottom)), right < orig.width),
    ] if there}
    breaks = lambda img, out, inn: changed(img.crop(out), img.crop(inn))
    seam = {side: round(max(breaks(gen, *lines) - breaks(orig, *lines), 0), 3) for side, lines in sides.items()}
    a = band(orig, top - MARGIN, bottom + MARGIN)
    b = band(gen, top - MARGIN, bottom + MARGIN)
    a.save(os.path.join(out, f"{sec}-orig.png"))
    b.save(os.path.join(out, f"{sec}-gen.png"))
    b.resize((b.width // 2, b.height // 2)).save(os.path.join(out, f"{sec}-gen.jpg"), quality=85)
    pad, head = 32, 56
    side = Image.new("RGB", (a.width + b.width + pad * 3, a.height + head + pad), "white")
    draw = ImageDraw.Draw(side)
    draw.text((pad, 16), f"section {sec}: original", fill="black", font=font)
    draw.text((a.width + pad * 2, 16), f"section {sec}: generated ({MARGIN}px of page above and below)", fill="black", font=font)
    side.paste(a, (pad, head))
    side.paste(b, (a.width + pad * 2, head))
    side.save(os.path.join(out, f"{sec}-side.png"))
    entry = {"box": o, "spill": meta["spill"], "seam": seam, "above_rows_differing": round(above, 3), "below_rows_differing": round(below, 3), **meta["checks"]}
    entry["replay"] = replay[sec]
    entry["failed"] = [name for name, bad in [
        ("replay", not replay[sec]["same"]),
        ("fit", not meta["fits"]),
        ("seam", max(seam.values(), default=0) > SEAM),
        ("text", bool(entry["missingText"])),
        ("images", bool(entry["missingImages"] or entry["brokenImages"])),
        ("overflow", entry["overflow"] > 0),
        ("fonts", bool(entry["fontsMissing"])),
    ] if bad]
    report["pairs"][sec] = entry
    print(f"section {sec}: {'ok' if not entry['failed'] else 'FAILED ' + ', '.join(entry['failed'])} (spill {meta['spill']}px, seam {' '.join(f'{k} {v:.1%}' for k, v in seam.items()) or 'none measured'}, page around changed: above {above:.1%}, below {below:.1%}; missing text {len(entry['missingText'])}, missing images {len(entry['missingImages'])}, overflow {entry['overflow']})")

json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=1)
