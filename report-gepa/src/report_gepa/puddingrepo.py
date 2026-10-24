"""Data of the pudding.cool stories that published none, from each story's own GitHub repo.

    PYTHONPATH=src .venv/bin/python -m report_gepa.puddingrepo clone <cache_dir>/web <cache_dir>/repos
    PYTHONPATH=src .venv/bin/python -m report_gepa.puddingrepo pack <cache_dir>/repos data/pudding-repo

Most Pudding stories import their data at build time, so the page loads no data
file and report_gepa.puddingweb finds nothing: the table is inlined in a JS chunk.
The source data usually sits in the story's repo under the-pudding (src/data/,
static/assets/...). clone takes every story of puddingweb's summary.jsonl that
data/pudding-web has nothing for, looks for a public repo named after its slug
(also with _ for -), and shallow-clones it without LFS objects; <repos>/repos.jsonl
gets one line per story with the repo found, or null.

pack keeps the csv and tsv files outside node_modules and .git, minus the
starter template's placeholders (test.csv, sample.csv, demo folders). A file
whose contents data/pudding, data/pudding-web or an earlier file already has is
dropped (the copy a build puts in docs/ or public/), and a story is kept under
the same rule as puddingweb's pack: one of its files is a table of at least
MIN_ROWS rows and MIN_COLUMNS columns. The files go to <out>/<id>/ under their own
names (with their folders when two share a name) and <out>/manifest.jsonl gets
{id, title, url, repo, published, files, bytes}. These stories are for learning
and the benchmark only: report_gepa.optimize.split does not see them.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from .optimize import DATA
from .puddingweb import KEEP, MIN_COLUMNS, MIN_ROWS, digest, manifest, table_shape

WEB = DATA.parent / "pudding-web"
OWNER = "https://github.com/the-pudding/"
SKIP_DIRS = {".git", "node_modules", ".svelte-kit"}
TEMPLATE = {"test.csv", "sample.csv", "demo-layercake.csv"}


def git(*args: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"})


def clone(web: Path, repos: Path):
    repos.mkdir(parents=True, exist_ok=True)
    packed = {row["url"].rstrip("/").split("pudding.cool/")[-1] for row in manifest(WEB / "manifest.jsonl")}
    done = {row["url"] for row in manifest(repos / "repos.jsonl")}
    todo = [s for s in manifest(web / "summary.jsonl") if s["url"].rstrip("/") not in packed and s["url"] not in done]
    print(f"{len(todo)} stories to look up", flush=True)
    for s in todo:
        slug = s["url"].rstrip("/").split("/")[-1]
        repo = next((name for name in dict.fromkeys([slug, slug.replace("-", "_")])
                     if git("ls-remote", "--heads", OWNER + name, timeout=60).returncode == 0), None)
        if repo and not (repos / slug / ".git").is_dir():
            r = git("clone", "--depth", "1", "--single-branch", OWNER + repo, str(repos / slug))
            if r.returncode != 0:
                print(f"{s['url']:40s} clone failed: {r.stderr.strip()[-200:]}", flush=True)
                continue
        with (repos / "repos.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"url": s["url"], "slug": slug, "title": s["title"], "repo": repo}, ensure_ascii=False) + "\n")
        print(f"{s['url']:40s} {repo or '-'}", flush=True)


def tables(folder: Path) -> list[Path]:
    found = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and "demo" not in d.lower())
        found += [Path(root) / f for f in sorted(files) if Path(f).suffix.lower() in KEEP and f.lower() not in TEMPLATE]
    return found


def pack(repos: Path, out: Path):
    seen = {digest(p) for d in (DATA, WEB) for p in d.rglob("*") if p.is_file() and p.suffix.lower() in KEEP}
    taken = {row["id"] for d in (DATA, WEB) for row in manifest(d / "manifest.jsonl")}
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    rows = []
    for row in manifest(repos / "repos.jsonl"):
        if not row["repo"]:
            continue
        fresh = []
        for p in tables(repos / row["slug"]):
            h = digest(p)
            if h not in seen:
                seen.add(h)
                fresh.append(p)
        shapes = [table_shape(p) for p in fresh]
        if not any(r >= MIN_ROWS and c >= MIN_COLUMNS for r, c in shapes):
            print(f"{row['url']:40s} skipped: {len(fresh)} new csv/tsv files, rows x columns {shapes[:8]}", flush=True)
            continue
        sid = row["slug"] if row["slug"] not in taken else row["url"].strip("/").replace("/", "_")
        taken.add(sid)
        names = [p.name for p in fresh]
        if len(set(names)) != len(names):  # two folders hold a file of the same name
            names = [str(p.relative_to(repos / row["slug"])).replace("/", "__") for p in fresh]
        (out / sid).mkdir()
        for p, name in zip(fresh, names):
            shutil.copy2(p, out / sid / name)
        parts = row["url"].strip("/").split("/")
        size = sum(p.stat().st_size for p in fresh)
        rows.append({"id": sid, "title": row["title"], "url": f"https://pudding.cool/{row['url'].strip('/')}/",
                     "repo": OWNER + row["repo"], "published": f"{parts[1]}/{parts[0]}" if parts[0].isdigit() else "",
                     "files": names, "bytes": size})
        print(f"{row['url']:40s} -> {sid}: {len(names)} files {size / 1e6:.2f} MB  {row['title'][:50]}", flush=True)
    (out / "manifest.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(rows)} stories in {out}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("clone")
    c.add_argument("web", type=Path)
    c.add_argument("repos", type=Path)
    k = sub.add_parser("pack")
    k.add_argument("repos", type=Path)
    k.add_argument("out", type=Path)
    args = ap.parse_args()
    clone(args.web, args.repos) if args.cmd == "clone" else pack(args.repos, args.out)


if __name__ == "__main__":
    main()
