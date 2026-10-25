"""Data the pudding.cool stories bundle into their JS: the tables a build inlined from its data files.

    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingjs harvest <cache_dir>/js
    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingjs extract <cache_dir>/js
    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingjs pack <cache_dir>/js data/pudding-js

Most stories import their data at build time, so the page loads no data file
(report_gepa.puddingweb finds nothing) and the table sits in a JS chunk instead.
harvest opens every story on the site's list that neither report_gepa.pudding nor
the benchmark (report-bench/tasks.json) has data for, scrolls through it (a chunk
can load late) and keeps every JS file the page loads from pudding.cool and every
inline script of the page (a json script as `export default <json>`) under
<cache_dir>/js/<slug>/js/, one line per story in summary.jsonl. A story already in
summary.jsonl is not opened again.

extract runs jsdata/extract.mjs on every harvested story: the tables go to
<slug>/tables/ and one line per table to <slug>/tables.jsonl (where it sits in the
JS, its kind, rows, columns and header). The extractor only takes literals: an
array of records, an array of equal rows (the build dropped the header: columns
c0, c1...), an object of equal columns, a csv or tsv string, a numbered codebook,
each also inside a JSON.parse; see jsdata/extract.mjs.

pack takes the tables TABLES names, looked up by where they sit in the JS, and
writes them to <out>/<id>/<name> with the header TABLES gives (read from the code
that uses a headerless table), <out>/manifest.jsonl getting {id, title, url,
published, files, bytes}. The other tables were looked at and left out: the
story's copy and scroll steps, colour keys, sprite and layout boxes, map shapes,
tables computed for one chart (counts per year or per bin), and rows whose cells
are encoded arrays nobody can read without the story's code.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from .pudding import STORIES
from .puddingweb import CHROMIUM, SCROLL, STORY_LIST, manifest

EXTRACT = Path(__file__).resolve().parents[2] / "jsdata" / "extract.mjs"
BENCH = Path(__file__).resolve().parents[3] / "report-bench" / "tasks.json"
INLINE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S | re.I)

# story id (the url's last part) -> {file name: (where the table sits in the JS, header or None to keep its own)}
TABLES = {
    "kevin-bacon": {"actors.csv": ("Ke.nodes", ["pid", "name", "hop", "films", "avgDistance", "rank", "conc", "top50",
                                                 "predFilm", "predFilmConc", "predFilmDeg", "predAll", "careerAge"])},
    "menu-collection": {"menus.csv": ("or", None)},
    "street-view": {"terms.csv": ("Ot", None)},
    "aapi-casting": {"roles.csv": ("zt", None)},
    "music-dna": {"songs.csv": ("Aht", None), "samples.csv": ("fme", None)},
    "middle-school": {"survey.csv": ("Yg.json", None)},
    "love-songs": {"top10-songs.csv": ("sm", ["performers_list_str", "song", "date_as_decimal", "love_song_sub_type",
                                              "total_weeks_in_top_10"])},
    "abortion-mazes": {"states.csv": ("V1", None), "policies.csv": ("ef", None)},
    "scifi": {"films.csv": ("wt", None)},
    "climate-zones": {"cities.csv": ("un", None)},
    "greatest-music": {"albums.csv": ("yt", None), "voters.csv": ("Yn", None)},
    "upward-mobility": {"cities.csv": ("Kl.points.geometries", None)},
    "tiktok-story": {"artists.csv": ("B", None), "charting-artists.csv": ("v1", None)},
    "spades": {"answers.csv": ("app.ln", None), "questions.csv": ("app.i", ["question", "text"])},
    "cool": {"cools.csv": ("app.Je", None)},
}

csv.field_size_limit(sys.maxsize)


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
            row = {"url": s["url"], "slug": slug, "title": s.get("hed", ""), "js": len(files),
                   "js_bytes": sum(f.stat().st_size for f in files), "error": err}
            with (out / "summary.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{s['url']:40s} {len(files):3d} js {row['js_bytes'] / 1e6:6.2f} MB" + (f"  ERROR {err}" if err else ""), flush=True)
        browser.close()


def extract(src: Path):
    for row in manifest(src / "summary.jsonl"):
        folder = src / row["slug"]
        shutil.rmtree(folder / "tables", ignore_errors=True)
        run = subprocess.run(["node", str(EXTRACT), str(folder / "tables"), *map(str, sorted((folder / "js").iterdir()))],
                             capture_output=True, text=True, timeout=900)
        if run.returncode:
            raise SystemExit(f"{row['url']}: extract.mjs failed\n{run.stderr[-2000:]}")
        found = [json.loads(line) for line in run.stdout.splitlines() if line.strip()]
        tables = [t for t in found if "file" in t]
        (folder / "tables.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in tables), encoding="utf-8")
        biggest = max(tables, key=lambda t: t["rows"], default=None)
        errors = [t for t in found if "error" in t]
        print(f"{row['url']:40s} {len(tables):3d} tables"
              + (f"  biggest {biggest['rows']}x{biggest['columns']} {biggest['kind']} {biggest['where'][:30]}" if biggest else "")
              + (f"  {len(errors)} files did not parse" if errors else ""), flush=True)


def pack(src: Path, out: Path):
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    stories = {row["url"].rstrip("/").split("/")[-1]: row for row in manifest(src / "summary.jsonl")}
    ids = bench_ids()
    rows = []
    for sid, wanted in TABLES.items():
        row = stories[sid]
        if benched(row["url"], ids):
            raise SystemExit(f"{sid}: the benchmark already has this story as a pudding-web or pudding-repo task")
        tables = manifest(src / row["slug"] / "tables.jsonl")
        (out / sid).mkdir()
        for name, (where, header) in wanted.items():
            hits = [t for t in tables if t["where"] == where]
            if len(hits) != 1:
                raise SystemExit(f"{sid}: {len(hits)} tables sit at {where!r}, want 1")
            t = hits[0]
            if header and len(header) != t["columns"]:
                raise SystemExit(f"{sid}: {where} has {t['columns']} columns, the header {len(header)}")
            with (src / row["slug"] / "tables" / t["file"]).open(encoding="utf-8", newline="") as f, \
                 (out / sid / name).open("w", encoding="utf-8", newline="") as g:
                reader, writer = csv.reader(f, delimiter="\t" if t["file"].endswith(".tsv") else ","), csv.writer(g)
                writer.writerow(header or next(reader))
                if header:
                    next(reader)
                writer.writerows(reader)
        parts = row["url"].strip("/").split("/")
        size = sum(p.stat().st_size for p in (out / sid).iterdir())
        rows.append({"id": sid, "title": row["title"], "url": f"https://pudding.cool/{row['url'].strip('/')}/",
                     "published": f"{parts[1]}/{parts[0]}" if parts[0].isdigit() else "", "files": list(wanted), "bytes": size})
        print(f"{row['url']:40s} -> {sid}: {', '.join(wanted)} {size / 1e6:.2f} MB  {row['title'][:50]}", flush=True)
    (out / "manifest.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(rows)} stories in {out}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("harvest", "extract"):
        sub.add_parser(cmd).add_argument("src", type=Path)
    k = sub.add_parser("pack")
    k.add_argument("src", type=Path)
    k.add_argument("out", type=Path)
    args = ap.parse_args()
    {"harvest": lambda: harvest(args.src), "extract": lambda: extract(args.src), "pack": lambda: pack(args.src, args.out)}[args.cmd]()


if __name__ == "__main__":
    main()
