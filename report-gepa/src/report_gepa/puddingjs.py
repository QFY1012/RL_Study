"""Data the pudding.cool stories bundle into their JS: the tables a build inlined from its data files.

    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingjs harvest <cache_dir>/js
    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingjs pack <cache_dir>/js data/pudding-js

Most stories import their data at build time, so the page loads no data file
(report_gepa.puddingweb finds nothing) and the table sits in a JS chunk instead.
harvest opens every story on the site's list that neither report_gepa.pudding nor
the benchmark (report-bench/tasks.json) has data for, scrolls through it (a chunk can load late), keeps every JS file the page loads
from pudding.cool and every inline script of the page (a json script as
`export default <json>`) under <cache_dir>/js/<slug>/js/, and runs
jsdata/extract.mjs on them: the tables go to <slug>/tables/, one line per story
to summary.jsonl. A story already in summary.jsonl is not opened again.

The extractor only takes literals: an array of records, an array of equal rows
(the build dropped the header: columns c0, c1...), an object of equal columns, a
csv or tsv string, each also inside a JSON.parse; see jsdata/extract.mjs.

pack leaves out the stories the benchmark has (it may have got them since harvest
ran) and keeps a story when one of its tables has at least MIN_ROWS rows and
MIN_COLUMNS columns, drops a table whose contents an earlier one of the story
has (the same data in two chunks), and copies the tables to <out>/<id>/ with
<out>/manifest.jsonl getting {id, title, url, published, files, bytes, tables}
(tables: where each one sits in the JS, its kind, rows and columns, so a
headerless one can be named from the story).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from .pudding import STORIES
from .puddingweb import CHROMIUM, MIN_COLUMNS, MIN_ROWS, SCROLL, STORY_LIST, digest, manifest, table_shape

EXTRACT = Path(__file__).resolve().parents[2] / "jsdata" / "extract.mjs"
BENCH = Path(__file__).resolve().parents[3] / "report-bench" / "tasks.json"
INLINE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S | re.I)


def story_path(url: str) -> str:
    return url.split("pudding.cool/")[-1].removesuffix("index.html").strip("/")


def bench_ids() -> set[str]:
    return {t["id"] for t in json.loads(BENCH.read_text(encoding="utf-8")) if t["source"] in ("pudding-web", "pudding-repo")}


def benched(url: str, ids: set[str]) -> bool:
    """pudding-web and pudding-repo tasks are named after the url's last part, or the slug when two share it."""
    return story_path(url).split("/")[-1] in ids or story_path(url).replace("/", "_") in ids


def inline_scripts(html: str) -> list[str]:
    out = []
    for attrs, body in INLINE.findall(html):
        if re.search(r"\bsrc\s*=", attrs) or not body.strip():
            continue
        out.append(f"export default {body}" if re.search(r"json", attrs, re.I) else body)
    return out


def harvest(out: Path):
    import urllib.request

    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(STORY_LIST, timeout=60) as r:
        listed = json.loads(r.read())
    have = {story_path(s.url) for s in STORIES}
    ids = bench_ids()
    done = {row["url"] for row in manifest(out / "summary.jsonl")}
    todo = [s for s in listed if not s["url"].startswith("http") and story_path(s["url"]) not in have
            and not benched(s["url"], ids) and s["url"] not in done]
    print(f"{len(todo)} stories to open ({len(listed)} listed, {len(have)} in report_gepa.pudding, "
          f"{len(ids)} pudding-web and pudding-repo tasks in the benchmark, {len(done)} done)", flush=True)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM, **({"proxy": {"server": proxy}} if proxy else {}))
        for s in todo:
            slug = s["url"].strip("/").replace("/", "_")
            js = out / slug / "js"
            shutil.rmtree(out / slug, ignore_errors=True)
            js.mkdir(parents=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})

            def keep(response, js=js):
                u = urlparse(response.url)
                if not u.netloc.endswith("pudding.cool") or not u.path.endswith((".js", ".mjs")):
                    return
                try:
                    body = response.body()
                except Exception:  # noqa: BLE001 - a response without a body (a redirect) is not code
                    return
                (js / (u.path.strip("/").replace("/", "__") or "script.js")).write_bytes(body)

            page.on("response", keep)
            err = None
            try:
                page.goto(f"https://pudding.cool/{s['url'].strip('/')}/", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(4000)
                page.evaluate(SCROLL)
                page.wait_for_timeout(2500)
                for i, body in enumerate(inline_scripts(page.content())):
                    (js / f"inline-{i}.js").write_text(body, encoding="utf-8")
            except Exception as e:  # noqa: BLE001 - what loaded before the error is kept
                err = str(e)[:120]
            page.close()
            files = sorted(js.iterdir())
            run = subprocess.run(["node", str(EXTRACT), str(out / slug / "tables"), *map(str, files)],
                                 capture_output=True, text=True, timeout=900)
            found = [json.loads(line) for line in run.stdout.splitlines() if line.strip()]
            tables = [t for t in found if "file" in t]
            row = {"url": s["url"], "slug": slug, "title": s.get("hed", ""), "js": len(files),
                   "js_bytes": sum(f.stat().st_size for f in files), "tables": tables,
                   "parse_errors": [t for t in found if "error" in t], "error": err or (run.stderr.strip()[-200:] or None if run.returncode else None)}
            with (out / "summary.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            biggest = max(tables, key=lambda t: t["rows"], default=None)
            print(f"{s['url']:40s} {len(files):3d} js {row['js_bytes'] / 1e6:6.2f} MB {len(tables):3d} tables"
                  + (f"  biggest {biggest['rows']}x{biggest['columns']} {biggest['kind']} {biggest['where'][:30]}" if biggest else "")
                  + (f"  ERROR {row['error']}" if row["error"] else ""), flush=True)
        browser.close()


def pack(src: Path, out: Path):
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    rows = []
    ids = bench_ids()
    for row in manifest(src / "summary.jsonl"):
        if benched(row["url"], ids):
            print(f"{row['url']:40s} skipped: in the benchmark", flush=True)
            continue
        seen, kept = set(), []
        for t in row["tables"]:
            p = src / row["slug"] / "tables" / t["file"]
            r, c = table_shape(p)
            h = digest(p)
            if r >= MIN_ROWS and c >= MIN_COLUMNS and h not in seen:
                seen.add(h)
                kept.append((p, t))
        if not kept:
            print(f"{row['url']:40s} skipped: {len(row['tables'])} tables, none of {MIN_ROWS} rows x {MIN_COLUMNS} columns", flush=True)
            continue
        sid = row["url"].rstrip("/").split("/")[-1]
        sid = sid if sid not in {r["id"] for r in rows} else row["slug"]
        (out / sid).mkdir()
        for p, _ in kept:
            shutil.copy2(p, out / sid / p.name)
        parts = row["url"].strip("/").split("/")
        published = f"{parts[1]}/{parts[0]}" if parts[0].isdigit() else ""
        size = sum(p.stat().st_size for p, _ in kept)
        rows.append({"id": sid, "title": row["title"], "url": f"https://pudding.cool/{row['url'].strip('/')}/",
                     "published": published, "files": [p.name for p, _ in kept], "bytes": size,
                     "tables": [{k: t[k] for k in ("file", "where", "kind", "rows", "columns", "header")} for _, t in kept]})
        print(f"{row['url']:40s} -> {sid}: {len(kept)} tables {size / 1e6:.2f} MB  {row['title'][:50]}", flush=True)
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
