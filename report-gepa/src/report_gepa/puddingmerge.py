"""Pudding stories whose data is there but not as a table: one recipe each makes it one.

    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.puddingmerge <cache_dir> data/pudding-merge [--stories a,b]

The other sources left these out because the data is spread over many small
files (one per game, station, contest, person or name), is json that is not a
list of records, or sits on a host other than pudding.cool. Each recipe in
RECIPES fetches the files (repos shallow-cloned into <cache_dir>, only the paths
it reads) and writes tables to <out>/<id>/:

    concat  many files of one shape -> one table; the column a file stood for
            (station, contest, ...) comes from its name
    json    nested json -> long rows (name, spelling, count), map properties ->
            a row per region, records -> a row per record
    copy    a file the page loads from another host

<out>/manifest.jsonl gets {id, title, url, published, files, bytes}. A story the
benchmark already has (report-bench/tasks.json) is refused.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError

from .optimize import DATA
from .puddingweb import STORY_LIST, manifest

BENCH = Path(__file__).resolve().parents[3] / "report-bench" / "tasks.json"

csv.field_size_limit(sys.maxsize)


def checkout(repo: str, paths: list[str], cache: Path) -> Path:
    """Shallow clone with only `paths` (gitignore-style patterns) checked out; reused if present."""
    dst = cache / repo.replace("/", "__")
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
    if not (dst / ".git").exists():
        subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--no-checkout", "--quiet",
                        f"https://github.com/{repo}", str(dst)], check=True, env=env)
    subprocess.run(["git", "sparse-checkout", "set", "--no-cone", *paths], cwd=dst, check=True, env=env)
    subprocess.run(["git", "checkout", "--quiet"], cwd=dst, check=True, env=env)
    return dst


def get(url: str) -> bytes | None:
    """The file at url, None when there is none (404); a dropped connection is tried again, up to 4 times."""
    for wait in (2, 4, 8, 16, None):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except HTTPError as e:
            if e.code == 404:
                return None
            raise
        except (ConnectionError, TimeoutError, URLError):
            if wait is None:
                raise
            time.sleep(wait)


def concat(parts: list[tuple[dict, Path]], dst: Path) -> int:
    """Write the rows of every file to dst, each with its own extra columns in front; return the row count."""
    header = list(dict.fromkeys(k for extra, _ in parts for k in extra))
    for _, p in parts:
        with p.open(encoding="utf-8-sig", newline="") as f:
            header += [k for k in next(csv.reader(f)) if k not in header]
    n = 0
    with dst.open("w", encoding="utf-8", newline="") as g:
        w = csv.DictWriter(g, header)
        w.writeheader()
        for extra, p in parts:
            with p.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    w.writerow({**row, **extra})
                    n += 1
    return n


def write(dst: Path, header: list[str], rows) -> int:
    n = 0
    with dst.open("w", encoding="utf-8", newline="") as g:
        w = csv.writer(g)
        w.writerow(header)
        for r in rows:
            w.writerow(r)
            n += 1
    return n


def two_minute_report(cache: Path, out: Path):
    # the repo also has one file per game under output/games/; all_games.csv is all of them
    src = checkout("polygraph-cool/last-two-minute-report", ["/output/all_games.csv"], cache)
    (out / "calls.csv").write_bytes((src / "output" / "all_games.csv").read_bytes())


def country_radio(cache: Path, out: Path):
    # input/: a year of plays per station; output/ and analysis/ are the story's counts
    src = checkout("the-pudding/country-radio-data", ["/input/*-Workbook-Full2022.csv"], cache)
    files = sorted((src / "input").glob("*-Workbook-Full2022.csv"))
    concat([({"city": re.sub(r"(?<=[a-z])(?=[A-Z])", " ", p.name.split("_")[0])}, p) for p in files], out / "plays.csv")


def caption_contest(cache: Path, out: Path):
    # summaries/<contest>[_<sampler>].csv: each caption's votes; a few contests were run with two or three samplers
    src = checkout("nextml/caption-contest-data", ["/summaries/*.csv"], cache)
    parts = []
    for p in sorted((src / "summaries").glob("*.csv"), key=lambda p: (int(p.stem.split("_")[0]), p.stem)):
        contest, _, sampler = p.stem.partition("_")
        parts.append(({"contest": contest, "sampler": sampler}, p))
    concat(parts, out / "captions.csv")


def wiki_billboard(cache: Path, out: Path):
    # one file per person of weekly page views (Wikipedia, July 2015 to September 2018); category.csv describes 246 of them
    src = checkout("the-pudding/wiki-billboard-data", ["/input/pageviews-binned--week/*.csv", "/input/category.csv"], cache)
    concat([({}, p) for p in sorted((src / "input" / "pageviews-binned--week").glob("*.csv"))], out / "weekly-pageviews.csv")
    (out / "people.csv").write_bytes((src / "input" / "category.csv").read_bytes())


def same_name(cache: Path, out: Path):
    # the page loads assets/places/<group>.csv for the places whose names sound alike: 0000 to 5553, a few missing
    url = "https://pudding.cool/2023/03/same-name/assets/places/{:04d}.csv"
    folder = cache / "same-name-places"
    folder.mkdir(parents=True, exist_ok=True)

    def one(i: int) -> Path | None:
        p = folder / f"{i:04d}.csv"
        if not p.exists():
            body = get(url.format(i))
            if body is None:
                return None
            p.write_bytes(body)
        return p

    with ThreadPoolExecutor(4) as pool:
        files = [(i, p) for i, p in enumerate(pool.map(one, range(5554))) if p]
    concat([({"sound_group": f"{i:04d}"}, p) for i, p in files], out / "places.csv")


def book_covers(cache: Path, out: Path):
    books = json.loads((DATA / "book-covers" / "data" / "json_output.json").read_text(encoding="utf-8"))
    # grid_point is where the story laid each cover out, not data about the book
    cols = ["title", "author", "isbn13", "genre", "is_fiction", "gender", "labels"]
    write(out / "books.csv", cols, ([b.get(c) if c != "labels" else "|".join(b.get(c) or []) for c in cols] for b in books))


def eu_regions(cache: Path, out: Path):
    folder = DATA / "eu-regions"
    cols = ["NUTS_ID", "CNTR_CODE", "NUTS_NAME", "gdppps17"]
    for name, level in (("regions.csv", "nuts2"), ("countries.csv", "nuts0")):
        topo = json.loads((folder / f"{level}_gdppps17_topo.json").read_text(encoding="utf-8"))
        geoms = [g["properties"] for o in topo["objects"].values() for g in o["geometries"]]
        write(out / name, cols, ([str(p.get(c, "")).strip() for c in cols] for p in geoms))
    # the file also labels capitals outside the EU on the map; only the 28 EU ones have a region and a GDP
    caps = [f["properties"] for f in json.loads((folder / "capitals-gdppps17.json").read_text(encoding="utf-8"))["features"]]
    write(out / "capitals.csv", ["capital", "NUTS_ID", "CNTR_CODE", "gdppps17"],
          ([p["name"], p["NUTS_ID"], p["CNTR_CODE"], p["gdppps17"]] for p in caps if p.get("NUTS_ID")))


def spellings(story: str):
    def make(cache: Path, out: Path):
        names = json.loads((DATA / story / "data-all.json").read_text(encoding="utf-8"))["data"]["names"]
        write(out / "spellings.csv", ["name", "spelling", "count"],
              ([name, s["name"], s["count"]] for name, rows in names.items() for s in rows))
    return make


def copy(**files: str):
    """name_csv=url: the file at url as name.csv (dashes for underscores)."""
    def make(cache: Path, out: Path):
        for name, u in files.items():
            (out / (name.removesuffix("_csv").replace("_", "-") + ".csv")).write_bytes(get(u))
    return make


# story id -> (story url, recipe)
RECIPES = {
    "two-minute-report": ("https://pudding.cool/2017/02/two-minute-report/", two_minute_report),
    "country-radio": ("https://pudding.cool/2023/05/country-radio/", country_radio),
    "caption-contest": ("https://pudding.cool/projects/caption-contest/", caption_contest),
    "wiki-billboard": ("https://pudding.cool/2018/09/wiki-billboard/", wiki_billboard),
    "same-name": ("https://pudding.cool/2023/03/same-name/", same_name),
    "book-covers": ("https://pudding.cool/2019/07/book-covers/", book_covers),
    "eu-regions": ("https://pudding.cool/2019/04/eu-regions/", eu_regions),
    "nba-spelling": ("https://pudding.cool/2019/03/nba-spelling/", spellings("nba-spelling")),
    "gyllenhaal": ("https://pudding.cool/2019/02/gyllenhaal/", spellings("gyllenhaal")),
    "restaurants": ("https://pudding.cool/2018/02/restaurants/",
                    copy(county_searches_csv="https://googletrends.github.io/restaurants_vs/assets/gremel_county_foods_3.csv")),
    # summary_3.csv next to it is the story's correlations per year; only the weekly interest per state is data
    "new-slang": ("https://pudding.cool/2017/02/new-slang/",
                  copy(state_weekly_searches_csv="https://googletrends.github.io/year-in-language/state_data_10.csv")),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cache", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--stories", help="comma-separated ids to (re)make; the others stay as they are")
    args = ap.parse_args()

    wanted = args.stories.split(",") if args.stories else list(RECIPES)
    if unknown := set(wanted) - set(RECIPES):
        raise SystemExit(f"no recipe for {sorted(unknown)}")
    if taken := set(wanted) & {t["id"] for t in json.loads(BENCH.read_text(encoding="utf-8")) if t["source"] != "pudding-merge"}:
        raise SystemExit(f"the benchmark already has {sorted(taken)} from another source")
    with urllib.request.urlopen(STORY_LIST, timeout=60) as r:
        titles = {s["url"].strip("/"): s["hed"] for s in json.loads(r.read())}
    args.cache.mkdir(parents=True, exist_ok=True)
    rows = {r["id"]: r for r in manifest(args.out / "manifest.jsonl")}
    for sid in wanted:
        url, recipe = RECIPES[sid]
        folder = args.out / sid
        for p in folder.glob("*"):
            p.unlink()
        folder.mkdir(parents=True, exist_ok=True)
        recipe(args.cache, folder)
        files = sorted(p.name for p in folder.iterdir())
        size = sum((folder / f).stat().st_size for f in files)
        path = url.split("pudding.cool/")[-1].strip("/")
        parts = path.split("/")
        rows[sid] = {"id": sid, "title": titles.get(path, ""), "url": url,
                     "published": f"{parts[1]}/{parts[0]}" if parts[0].isdigit() else "", "files": files, "bytes": size}
        shapes = []
        for f in files:
            with (folder / f).open(encoding="utf-8-sig", newline="") as h:
                r = csv.reader(h)
                cols = len(next(r))
                shapes.append(f"{f} {sum(1 for _ in r)}x{cols}")
        print(f"{sid:18s} {size / 1e6:8.2f} MB  {', '.join(shapes)}", flush=True)
    order = [s for s in RECIPES if s in rows]
    (args.out / "manifest.jsonl").write_text("".join(json.dumps(rows[s], ensure_ascii=False) + "\n" for s in order), encoding="utf-8")
    print(f"{len(order)} stories in {args.out}", flush=True)


if __name__ == "__main__":
    main()
