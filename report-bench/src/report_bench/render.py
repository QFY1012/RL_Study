"""Render a generated HTML page and capture a full-page screenshot.

The page is served over a loopback http server rather than file://, because
browsers block module scripts and fetch on file://, which leaves runtime-rendered
pages blank. Before the shot we scroll to the bottom so lazy and reveal-on-scroll
content appears, freeze animations, and return to the top. Every in-page wait has
a deadline.

The result separates two things the scorer must not confuse: whether we saw the
page at all (``verdict``), and what the page did wrong (``page_errors``,
``syntax_errors``, ``hang``).
"""

from __future__ import annotations

import functools
import http.server
import json
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

RENDER_VERSION = "render-1"

VIEW_W, VIEW_H = 1440, 900
MAX_PAGE_H = 12000
LOAD_TIMEOUT_MS = 20000
SETTLE_MS = 800
CHROMIUM = "/opt/pw-browsers/chromium"

FREEZE_CSS = """
*, *::before, *::after {
  animation-play-state: paused !important;
  animation-delay: -1s !important;
  transition: none !important;
  scroll-behavior: auto !important;
}
* { background-attachment: scroll !important; }
"""

SCROLL_THROUGH = """
async (maxHeight) => {
  const step = window.innerHeight * 0.8;
  const limit = Math.min(document.documentElement.scrollHeight, maxHeight);
  for (let y = 0; y < limit; y += step) {
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 120));
  }
  window.scrollTo(0, 0);
}
"""

PAGE_TEXT = "() => (document.body ? document.body.innerText.trim().length : 0)"


@dataclass
class RenderResult:
    verdict: str  # "ok" | "blank" | "render_failed"
    screenshot: Path | None = None
    page_height: int = 0
    page_errors: list[str] = field(default_factory=list)
    syntax_errors: list[str] = field(default_factory=list)
    hang: bool = False
    detail: str = ""

    def to_json(self) -> dict:
        d = self.__dict__.copy()
        d["screenshot"] = str(self.screenshot) if self.screenshot else None
        d["render_version"] = RENDER_VERSION
        return d


def inline_script_syntax_errors(html: str) -> list[str]:
    """Run `node --check` on every inline classic script; a syntax error drops the whole block."""
    import re

    errors = []
    pattern = re.compile(r"<script(?![^>]*\bsrc=)(?![^>]*type=[\"'](?:module|application/json|application/ld\+json|text/template)[\"'])[^>]*>(.*?)</script>", re.S | re.I)
    for i, body in enumerate(pattern.findall(html)):
        if not body.strip():
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(body)
            path = f.name
        proc = subprocess.run(["node", "--check", path], capture_output=True, text=True, timeout=30)
        Path(path).unlink(missing_ok=True)
        if proc.returncode != 0:
            lines = proc.stderr.strip().splitlines()
            message = next((line for line in lines if "Error" in line), "syntax error")
            errors.append(f"script {i}: {message.strip()}")
    return errors


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - signature fixed by the base class
        pass


def _serve(root: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    handler = functools.partial(_QuietHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/page.html"


def _shoot(url: str, out_png: Path, proxy: str | None, syntax_errors: list[str], max_height: int,
           wait_until: str = "load", timeout_ms: int = LOAD_TIMEOUT_MS, settle_ms: int = SETTLE_MS) -> RenderResult:
    try:
        with sync_playwright() as p:
            launch = {"executable_path": CHROMIUM}
            if proxy:
                launch["proxy"] = {"server": proxy, "bypass": "127.0.0.1,localhost"}
            browser = p.chromium.launch(**launch)
            try:
                page = browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H})
                page_errors: list[str] = []
                page.on("pageerror", lambda e: page_errors.append(str(e)[:300]))
                try:
                    page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                except PlaywrightError as e:
                    return RenderResult("ok", hang=True, page_errors=page_errors, syntax_errors=syntax_errors,
                                        detail=f"load did not finish: {str(e)[:200]}")
                page.wait_for_timeout(settle_ms)
                try:
                    page.evaluate(SCROLL_THROUGH, max_height)
                except PlaywrightError as e:
                    return RenderResult("ok", hang=True, page_errors=page_errors, syntax_errors=syntax_errors,
                                        detail=f"page stopped answering: {str(e)[:200]}")
                page.add_style_tag(content=FREEZE_CSS)
                page.wait_for_timeout(200)
                height = min(page.evaluate("document.documentElement.scrollHeight"), max_height)
                text_len = page.evaluate(PAGE_TEXT)
                out_png.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(out_png), full_page=True, clip={"x": 0, "y": 0, "width": VIEW_W, "height": height})
                verdict = "ok" if text_len > 0 else "blank"
                return RenderResult(verdict, out_png, height, page_errors, syntax_errors)
            finally:
                browser.close()
    except PlaywrightError as e:
        return RenderResult("render_failed", detail=str(e)[:300])


def render(html: str, out_png: Path, proxy: str | None = None) -> RenderResult:
    """Render `html` and write a full-page PNG to `out_png`."""
    syntax_errors = inline_script_syntax_errors(html)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "page.html").write_text(html, encoding="utf-8")
        server, url = _serve(root)
        try:
            return _shoot(url, out_png, proxy, syntax_errors, MAX_PAGE_H)
        finally:
            server.shutdown()


def render_url(url: str, out_png: Path, proxy: str | None, max_height: int = MAX_PAGE_H) -> RenderResult:
    """Screenshot a published page the same way as a generated one, except that it
    waits only for the DOM: some published pages never fire load (vogue waited on a
    request that never finished). It then gives the page 5 s to build itself;
    mars-weather was 2,266px tall after 0.8 s and 8,036px after 3 s."""
    return _shoot(url, out_png, proxy, [], max_height, "domcontentloaded", 60000, 5000)


if __name__ == "__main__":
    import sys

    html_path, png_path = Path(sys.argv[1]), Path(sys.argv[2])
    result = render(html_path.read_text(encoding="utf-8"), png_path)
    print(json.dumps(result.to_json(), ensure_ascii=False, indent=1))
