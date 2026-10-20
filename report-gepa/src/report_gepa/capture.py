"""Capture what the judge sees of a page: scroll frames, a thumbnail, the text and the charts.

    PYTHONPATH=src .venv/bin/python -m report_gepa.capture one <page.html | url> <out_dir> [--data <file or dir>...]
    PYTHONPATH=src .venv/bin/python -m report_gepa.capture pudding runs/pudding-pages data/pudding runs/evidence [--versions original,seed-ds-1,pudding-ds-1] [--stories a,b] [--workers 4]

A single full-page shot keeps one state of a page whose chart changes as you
scroll, so the page is scrolled the way a reader scrolls it: small mouse-wheel
steps, so scroll-triggered steps (scrollama, IntersectionObserver) fire one by
one instead of being jumped over. A viewport frame is taken every FRAME_EVERY
pixels after transitions settle, without freezing animations; a frame that looks
the same as the one before it is dropped.

At every frame the charts on screen are recorded with their screen position and
a fingerprint of their content. From these the capture works out the scroll
story: a chart that stays at the same place on screen while the page moves is
pinned (sticky or fixed), and a fingerprint that changes means the chart was
redrawn, so "one chart, pinned over frames 5-12, four different states" reaches
the judge as text and does not have to be guessed from the pictures.

Afterwards a full-page shot is taken the way render.py takes it (scroll
through, freeze animations, back to the top) and shrunk into a thumbnail for
whole-page judgements such as visual consistency.

The text is read from the DOM in page order, with its position, so the judge
does not have to read small type off the screenshots and the fact checker can
see every number the page states. Charts are listed with their size and how
many marks and labels they hold.

<out_dir>/frames/NN.jpg, thumb.jpg and evidence.json are written; evidence.json
also names the data the page was made from, for the fact check. Generated pages
are served over loopback like in render.py; published pages are opened through
the proxy and get the same waits as render_url.

The pudding command captures, for every story, the published original
(<out>/<story>/original) and the generated versions (<out>/<story>/<version>),
skipping captures that already exist. Originals that are interactive apps
rather than scrolling stories (original_static false in the manifest) are not
captured.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from .render import CHROMIUM, FREEZE_CSS, SCROLL_THROUGH, VIEW_H, VIEW_W, _serve, inline_script_syntax_errors

CAPTURE_VERSION = "capture-2"
MAX_PAGE_H = 30000
MAX_FRAMES = 60
FRAME_EVERY = 450  # px between frames, unless the page is too long for MAX_FRAMES
WHEEL_PX = 80  # one wheel tick
WHEEL_PAUSE_MS = 40
FRAME_SETTLE_MS = 800
SAME_FRAME = 1.0  # mean absolute pixel difference (0-255) below which a frame repeats the last one
PINNED_PX = 4  # a chart whose screen position moves less than this while the page scrolls is pinned
THUMB_W = 480
JPEG_QUALITY = 80

# Text in page order. Each piece of text belongs to its nearest block-level
# element (a heading, paragraph, list item, table cell, svg <text>...), so a
# paragraph with a <b> inside comes out as one item.
PAGE_TEXT = r"""
() => {
  const BLOCK = 'h1,h2,h3,h4,h5,h6,p,li,figcaption,blockquote,td,th,dt,dd,label,button,option,caption,summary,text,title,pre';
  const out = new Map();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const t = n.textContent.replace(/\s+/g, ' ').trim();
    if (!t) continue;
    const parent = n.parentElement;
    if (!parent || parent.closest('script,style,noscript,template')) continue;
    const el = parent.closest(BLOCK) || parent;
    if (!out.has(el)) out.set(el, []);
    out.get(el).push(t);
  }
  const items = [];
  for (const [el, parts] of out) {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    items.push({
      tag: el.tagName.toLowerCase(),
      y: Math.round(r.top + scrollY), x: Math.round(r.left), w: Math.round(r.width),
      in_svg: !!el.closest('svg'),
      hidden: s.display === 'none' || s.visibility === 'hidden' || r.width === 0,
      text: parts.join(' ').slice(0, 2000),
    });
  }
  items.sort((a, b) => a.y - b.y || a.x - b.x);
  return items;
}
"""

# Charts: svg and canvas big enough not to be an icon, and images (assets the
# data did not provide).
CHARTS = r"""
() => {
  const items = [];
  for (const el of document.querySelectorAll('svg, canvas, img')) {
    if (el.tagName.toLowerCase() === 'svg' && el.parentElement && el.parentElement.closest('svg')) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 150 || r.height < 80) continue;
    const kind = el.tagName.toLowerCase();
    const item = {kind, y: Math.round(r.top + scrollY), x: Math.round(r.left), w: Math.round(r.width), h: Math.round(r.height)};
    if (kind === 'svg') {
      item.marks = el.querySelectorAll('rect,circle,ellipse,path,line,polyline,polygon').length;
      item.labels = el.querySelectorAll('text').length;
    }
    items.push(item);
  }
  items.sort((a, b) => a.y - b.y);
  return items;
}
"""


# The charts on screen now, in viewport coordinates, each with a fingerprint of
# its content. Elements get a stable id the first time they are seen, so the
# same chart can be followed from frame to frame.
CHART_STATE = r"""
() => {
  window.__capId = window.__capId || 0;
  const hash = (s) => { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return (h >>> 0).toString(16); };
  const out = [];
  for (const el of document.querySelectorAll('svg, canvas')) {
    if (el.tagName.toLowerCase() === 'svg' && el.parentElement && el.parentElement.closest('svg')) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 150 || r.height < 80) continue;
    if (r.bottom <= 0 || r.top >= innerHeight) continue;
    if (!el.dataset.capId) el.dataset.capId = String(++window.__capId);
    let sig = '';
    if (el.tagName.toLowerCase() === 'svg') {
      const parts = [];
      for (const m of el.querySelectorAll('rect,circle,ellipse,path,line,polyline,polygon,text,g')) {
        const st = getComputedStyle(m);
        parts.push(m.tagName, m.getAttribute('x'), m.getAttribute('y'), m.getAttribute('width'), m.getAttribute('height'),
                   m.getAttribute('cx'), m.getAttribute('cy'), m.getAttribute('r'), (m.getAttribute('d') || '').length,
                   m.getAttribute('transform'), st.opacity, st.fill, st.visibility, m.tagName === 'text' ? m.textContent : '');
        if (parts.length > 40000) break;
      }
      sig = hash(parts.join('|'));
    } else {
      try { sig = hash(el.toDataURL('image/png', 0.1)); } catch (e) { sig = 'tainted'; }
    }
    out.push({id: +el.dataset.capId, kind: el.tagName.toLowerCase(), top: Math.round(r.top), left: Math.round(r.left),
              w: Math.round(r.width), h: Math.round(r.height), sig});
  }
  return out;
}
"""


def _jpeg(png: bytes, path: Path, width: int | None = None) -> None:
    from io import BytesIO

    img = Image.open(BytesIO(png)).convert("RGB")
    if width and img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    img.save(path, "JPEG", quality=JPEG_QUALITY)


def _same(a: Image.Image, b: Image.Image) -> bool:
    from PIL import ImageChops, ImageStat

    small = (a.width // 4, a.height // 4)
    diff = ImageChops.difference(a.convert("L").resize(small), b.convert("L").resize(small))
    return ImageStat.Stat(diff).mean[0] < SAME_FRAME


def _wheel_to(page, target: int) -> int:
    """Scroll down to `target` in wheel ticks, like a reader; returns where the page ended up."""
    at = page.evaluate("Math.round(scrollY)")
    while at < target:
        page.mouse.wheel(0, min(WHEEL_PX, target - at))
        page.wait_for_timeout(WHEEL_PAUSE_MS)
        now = page.evaluate("Math.round(scrollY)")
        if now <= at:  # the wheel did nothing: bottom of the page, or wheel scrolling is blocked
            page.evaluate("y => window.scrollTo(0, y)", target)
            now = page.evaluate("Math.round(scrollY)")
            if now <= at:
                break
        at = now
    return at


def _walk(page, out: Path) -> list[dict]:
    """Viewport frames from top to bottom, with the charts on screen at each one."""
    from io import BytesIO

    frames_dir = out / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    page.mouse.move(VIEW_W / 2, VIEW_H / 2)
    frames, last, target = [], None, 0
    while len(frames) < MAX_FRAMES:
        height = min(page.evaluate("document.documentElement.scrollHeight"), MAX_PAGE_H)
        every = max(FRAME_EVERY, -(-height // MAX_FRAMES))
        at = _wheel_to(page, target)
        page.wait_for_timeout(FRAME_SETTLE_MS)
        img = Image.open(BytesIO(page.screenshot())).convert("RGB")
        charts = page.evaluate(CHART_STATE)
        if last is None or not _same(img, last):
            name = f"frames/{len(frames):02d}.jpg"
            img.save(out / name, "JPEG", quality=JPEG_QUALITY)
            frames.append({"file": name, "scroll_y": at, "charts": charts})
            last = img
        if at + VIEW_H >= height or at < target:
            break  # reached the bottom, or the page would not scroll further
        target = at + every
    return frames


def scroll_story(frames: list[dict]) -> list[dict]:
    """Per chart: the frames it is on screen, the runs where it stays pinned while
    the page scrolls, and how many different states it shows."""
    seen: dict[int, list[tuple[int, dict]]] = {}
    for i, f in enumerate(frames):
        for c in f["charts"]:
            seen.setdefault(c["id"], []).append((i, c))
    story = []
    for cid, hits in seen.items():
        pinned, run = [], [hits[0][0]]
        for (i0, c0), (i1, c1) in zip(hits, hits[1:]):
            moved_page = frames[i1]["scroll_y"] != frames[i0]["scroll_y"]
            if i1 == i0 + 1 and moved_page and abs(c1["top"] - c0["top"]) < PINNED_PX:
                run.append(i1)
            else:
                if len(run) > 1:
                    pinned.append([run[0], run[-1]])
                run = [i1]
        if len(run) > 1:
            pinned.append([run[0], run[-1]])
        first = hits[0][1]
        story.append({"chart": cid, "kind": first["kind"], "size": [first["w"], first["h"]],
                      "frames": [hits[0][0], hits[-1][0]], "pinned": pinned,
                      "states": len({c["sig"] for _, c in hits})})
    return story


def _merge_letters(items: list[dict]) -> list[dict]:
    """A title animated letter by letter is one element per letter; join runs of
    one- and two-character items on the same line back into words."""
    out: list[dict] = []
    for t in items:
        prev = out[-1] if out else None
        if (prev and len(t["text"]) <= 2 and prev.get("letters") and prev["y"] == t["y"] and prev["tag"] == t["tag"]):
            prev["text"] += t["text"]
            continue
        t = dict(t)
        if len(t["text"]) <= 2:
            t["letters"] = True
        out.append(t)
    for t in out:
        t.pop("letters", None)
    return out


def capture(target: str, out: Path, proxy: str | None = None, data: list[Path] = ()) -> dict:
    """Capture `target` (a local html file or an http(s) url) into `out`."""
    out.mkdir(parents=True, exist_ok=True)
    is_url = target.startswith(("http://", "https://"))
    evidence = {"capture_version": CAPTURE_VERSION, "target": target, "data": [str(p) for p in data],
                "viewport": [VIEW_W, VIEW_H],
                "verdict": "render_failed", "page_errors": [], "syntax_errors": [], "hang": False}
    server = tmp = None
    try:
        if is_url:
            url, wait_until, timeout_ms, settle_ms = target, "domcontentloaded", 60000, 5000
        else:
            html = Path(target).read_text(encoding="utf-8", errors="replace")
            evidence["syntax_errors"] = inline_script_syntax_errors(html)
            tmp = tempfile.TemporaryDirectory()
            (Path(tmp.name) / "page.html").write_text(html, encoding="utf-8")
            server, url = _serve(Path(tmp.name))
            wait_until, timeout_ms, settle_ms = "load", 20000, 800
        with sync_playwright() as p:
            launch = {"executable_path": CHROMIUM}
            if is_url and proxy:
                launch["proxy"] = {"server": proxy, "bypass": "127.0.0.1,localhost"}
            browser = p.chromium.launch(**launch)
            try:
                page = browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H})
                page.on("pageerror", lambda e: evidence["page_errors"].append(str(e)[:300]))
                try:
                    page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                    page.wait_for_timeout(settle_ms)
                    evidence["frames"] = _walk(page, out)
                    evidence["scroll_story"] = scroll_story(evidence["frames"])
                    evidence["text"] = _merge_letters(page.evaluate(PAGE_TEXT))
                    evidence["charts"] = page.evaluate(CHARTS)
                    page.evaluate("window.scrollTo(0, 0)")
                    page.evaluate(SCROLL_THROUGH, MAX_PAGE_H)
                    page.add_style_tag(content=FREEZE_CSS)
                    page.wait_for_timeout(200)
                    height = min(page.evaluate("document.documentElement.scrollHeight"), MAX_PAGE_H)
                    full = page.screenshot(full_page=True, clip={"x": 0, "y": 0, "width": VIEW_W, "height": height})
                except PlaywrightError as e:
                    evidence["hang"] = True
                    evidence["detail"] = f"page stopped answering: {str(e)[:200]}"
                    return evidence
                _jpeg(full, out / "thumb.jpg", THUMB_W)
                evidence["thumb"] = "thumb.jpg"
                evidence["page_height"] = height
                visible = sum(len(t["text"]) for t in evidence["text"] if not t["hidden"])
                evidence["verdict"] = "ok" if visible > 0 else "blank"
            finally:
                browser.close()
    except PlaywrightError as e:
        evidence["detail"] = str(e)[:300]
    finally:
        if server:
            server.shutdown()
        if tmp:
            tmp.cleanup()
        (out / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    return evidence


def _summary(ev: dict) -> str:
    pinned = [c for c in ev.get("scroll_story", []) if c["pinned"]]
    return (f"verdict={ev['verdict']} height={ev.get('page_height')} frames={len(ev.get('frames', []))} "
            f"pinned_charts={len(pinned)} max_states={max([c['states'] for c in pinned], default=0)} "
            f"page_errors={len(ev['page_errors'])} syntax_errors={len(ev['syntax_errors'])} hang={ev['hang']}")


def pudding(pages: Path, data_root: Path, out: Path, versions: list[str], workers: int, proxy: str | None,
            stories: set[str] | None = None) -> None:
    from concurrent.futures import ThreadPoolExecutor

    jobs = []
    for line in (data_root / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        story = json.loads(line)
        if not story.get("ok") or (stories and story["id"] not in stories):
            continue
        data = [data_root / story["data"]]
        for v in versions:
            dest = out / story["id"] / v
            if (dest / "evidence.json").exists():
                continue
            if v == "original":
                if story.get("original_static") is False:
                    continue  # an interactive app, not a scrolling story: one screen of it says nothing
                jobs.append((story["url"], dest, data))
            elif (pages / story["id"] / v / "index.html").exists():
                jobs.append((str(pages / story["id"] / v / "index.html"), dest, data))

    def run(job):
        target, dest, data = job
        ev = capture(target, dest, proxy, data)
        print(f"{dest.parent.name}/{dest.name}: {_summary(ev)}", flush=True)

    print(f"{len(jobs)} captures", flush=True)
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(run, jobs))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("one")
    one.add_argument("target")
    one.add_argument("out", type=Path)
    one.add_argument("--data", type=Path, nargs="*", default=[])
    pud = sub.add_parser("pudding")
    pud.add_argument("pages", type=Path)
    pud.add_argument("data_root", type=Path)
    pud.add_argument("out", type=Path)
    pud.add_argument("--versions", default="original,seed-ds-1,pudding-ds-1")
    pud.add_argument("--workers", type=int, default=4)
    pud.add_argument("--stories", help="comma-separated story ids; all stories when omitted")
    args = ap.parse_args()
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if args.cmd == "one":
        ev = capture(args.target, args.out, proxy, args.data)
        print(_summary(ev))
        for c in ev.get("scroll_story", []):
            if c["pinned"] or c["states"] > 1:
                print(f"chart {c['chart']} {c['kind']} {c['size']}: frames {c['frames']} pinned {c['pinned']} states {c['states']}")
    else:
        pudding(args.pages, args.data_root, args.out, args.versions.split(","), args.workers, proxy,
                set(args.stories.split(",")) if args.stories else None)
