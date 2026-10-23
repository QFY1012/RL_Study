"""Data from the pudding.cool stories that publish none: the files each story page loads.

    PYTHONPATH=src .venv/bin/python -m report_gepa.puddingweb harvest <cache_dir>/web
    PYTHONPATH=src .venv/bin/python -m report_gepa.puddingweb pack <cache_dir>/web data/pudding-web

harvest opens every story on the site's list (pudding.cool/assets/data/stories.json)
that report_gepa.pudding has no data for, scrolls through it (scroll-triggered
charts load their data late) and keeps every csv/tsv/json response from
pudding.cool under <cache_dir>/web/<slug>/, with one line per story in
summary.jsonl. A story already in summary.jsonl is not opened again.

pack keeps only the csv and tsv files: the json a page loads is mostly map
outlines, sprite sheets and the story's own copy, which is not data to report on
and would hand the agent the article. A file whose contents data/pudding or an
earlier story already has is dropped (a story told twice, or one data/pudding
has under another url); a story is kept when what is left comes to at least
MIN_BYTES. The files go to <out>/<id>/ under their own names, and <out>/manifest.jsonl
gets {id, title, url, published, files, bytes}. These stories are for learning only:
report_gepa.optimize.split does not see them, so GEPA's val and test stories stay as they were.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .optimize import DATA

STORY_LIST = "https://pudding.cool/assets/data/stories.json"
SKIP = re.compile(r"/assets/data/stories\.json$|manifest\.json$|/_app/|version\.json$|\.webmanifest$", re.I)
SCROLL = """async () => { for (let y = 0; y < document.documentElement.scrollHeight; y += 700) { scrollTo(0, y); await new Promise(r => setTimeout(r, 150)); } }"""
KEEP = (".csv", ".tsv")
MIN_BYTES = 20_000
CHROMIUM = "/opt/pw-browsers/chromium"


def manifest(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def harvest(out: Path):
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(STORY_LIST, timeout=60) as r:
        listed = json.loads(r.read())
    have = {row["url"].rstrip("/").split("pudding.cool/")[-1] for row in manifest(DATA / "manifest.jsonl")}
    done = {row["url"] for row in manifest(out / "summary.jsonl")}
    todo = [s for s in listed if not s["url"].startswith("http") and s["url"].rstrip("/") not in have and s["url"] not in done]
    print(f"{len(todo)} stories to open ({len(listed)} listed, {len(have)} already in {DATA})", flush=True)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM, **({"proxy": {"server": proxy}} if proxy else {}))
        for s in todo:
            slug = s["url"].strip("/").replace("/", "_")
            files = []
            page = browser.new_page(viewport={"width": 1440, "height": 900})

            def keep(response, slug=slug, files=files):
                u = urlparse(response.url)
                if not u.netloc.endswith("pudding.cool") or SKIP.search(u.path):
                    return
                if not re.search(r"\.(csv|tsv|json)$", u.path, re.I) and "text/csv" not in response.headers.get("content-type", ""):
                    return
                try:
                    body = response.body()
                except Exception:  # noqa: BLE001 - a response without a body (a redirect) is not data
                    return
                name = u.path.strip("/").split("/", 2)[-1].replace("/", "__") or "data"
                (out / slug).mkdir(exist_ok=True)
                (out / slug / name).write_bytes(body)
                files.append((name, len(body)))

            page.on("response", keep)
            err = None
            try:
                page.goto(f"https://pudding.cool/{s['url'].strip('/')}/", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(4000)
                page.evaluate(SCROLL)
                page.wait_for_timeout(2500)
            except Exception as e:  # noqa: BLE001 - what loaded before the error is kept
                err = str(e)[:120]
            page.close()
            row = {"url": s["url"], "slug": slug, "title": s.get("hed", ""), "files": len(files),
                   "bytes": sum(n for _, n in files), "names": [n for n, _ in files][:30], "error": err}
            with (out / "summary.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{s['url']:40s} {len(files):3d} files {row['bytes'] / 1e6:7.2f} MB  {row['title'][:50]}"
                  + (f"  ERROR {err}" if err else ""), flush=True)
        browser.close()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pack(src: Path, out: Path):
    seen = {digest(p) for p in DATA.rglob("*") if p.is_file() and p.suffix.lower() in KEEP}
    taken = {row["id"] for row in manifest(DATA / "manifest.jsonl")}
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    rows = []
    for row in manifest(src / "summary.jsonl"):
        folder = src / row["slug"]
        files = sorted(p for p in folder.glob("*") if p.suffix.lower() in KEEP) if folder.is_dir() else []
        fresh = []
        for p in files:
            h = digest(p)
            if h not in seen:
                seen.add(h)
                fresh.append(p)
        size = sum(p.stat().st_size for p in fresh)
        if size < MIN_BYTES:
            print(f"{row['url']:40s} skipped: {len(fresh)} new csv/tsv files, {size} bytes", flush=True)
            continue
        sid = row["url"].rstrip("/").split("/")[-1]
        sid = sid if sid not in taken else row["slug"]
        taken.add(sid)
        names = [p.name.split("__")[-1] for p in fresh]
        names = names if len(set(names)) == len(names) else [p.name for p in fresh]  # the short names collide
        (out / sid).mkdir()
        for p, name in zip(fresh, names):
            shutil.copy2(p, out / sid / name)
        parts = row["url"].strip("/").split("/")
        published = f"{parts[1]}/{parts[0]}" if parts[0].isdigit() else ""
        rows.append({"id": sid, "title": row["title"], "url": f"https://pudding.cool/{row['url'].strip('/')}/",
                     "published": published, "files": names, "bytes": size})
        print(f"{row['url']:40s} -> {sid}: {len(names)} files {size / 1e6:.2f} MB  {row['title'][:50]}", flush=True)
    (out / "manifest.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(rows)} stories in {out}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("harvest")
    h.add_argument("out", type=Path)
    k = sub.add_parser("pack")
    k.add_argument("src", type=Path)
    k.add_argument("out", type=Path)
    args = ap.parse_args()
    harvest(args.out) if args.cmd == "harvest" else pack(args.src, args.out)


if __name__ == "__main__":
    main()
