"""Take datasets from The Pudding's public data repo, with their published stories as the bar.

    git clone --depth 1 https://github.com/the-pudding/data <pudding_repo>
    PYTHONPATH=src .venv/bin/python -m report_gepa.pudding <pudding_repo> data/pudding runs/pudding-originals

For each story in STORIES, the data files (csv, tsv, json) and the README are
copied to data/pudding/<slug>/, which is what the page agent gets. Lines of the
README that link to the published story are dropped, so the task stays "make a
report from this data" rather than "recall this article". The published story
is screenshotted to <originals>/<slug>.png the same way generated pages are.
data/pudding/manifest.jsonl lists every dataset in the same shape as datagen's,
and split.json puts them all under "pudding".

Stories were picked from the repo's 40 folders: the published page is built
mainly from this data (not a video, a game, a map of names or a newsletter), it
reads as a static page (kidz-bop, boybands and stand-up open on a start button,
so a screenshot shows only the cover; three-seconds is a video), and the data is
at most 70 MB. The repo is MIT licensed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

from .render import render_url

STORIES = [
    "birthday-effect", "foundation-names", "mars-weather", "census-history", "rain", "laugh", "clinics",
    "vogue", "hype", "dress-codes", "titletowns", "pockets", "makeup-shades", "cetaceans", "births",
    "filmordigital", "one-hit-wonders", "campaign-colors", "names-in-songs", "skate-music",
]
DATA_SUFFIXES = (".csv", ".tsv", ".json")
STORY_LINK = re.compile(r"pudding\.cool|polygraph\.cool", re.I)
ORIGINAL_MAX_HEIGHT = 30000


def story_index(repo: Path) -> dict[str, dict]:
    """Folder name -> title, url and date, from the table in the repo's README."""
    row = re.compile(r"\|\s*\[(.*?)\]\((.*?)\)\s*\|\s*(.*?)\s*\|.*\]\(https://github.com/(?:the-pudding|polygraph-cool)/data/tree/master/([\w-]+)\)")
    index = {}
    for line in (repo / "README.md").read_text(encoding="utf-8").splitlines():
        m = row.match(line)
        if m:
            index[m.group(4)] = {"title": m.group(1), "url": m.group(2), "published": m.group(3)}
    return index


def copy_dataset(src: Path, dst: Path) -> list[str]:
    shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True)
    files = []
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if path.is_file() and path.suffix.lower() in DATA_SUFFIXES:
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst / rel)
            files.append(str(rel))
    readme = src / "README.md"
    if readme.exists():
        lines = [line for line in readme.read_text(encoding="utf-8").splitlines() if not STORY_LINK.search(line)]
        (dst / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("originals", type=Path)
    args = ap.parse_args()

    index = story_index(args.repo)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    rows = []
    for slug in STORIES:
        story = index[slug]
        files = copy_dataset(args.repo / slug, args.out / slug)
        size = sum((args.out / slug / f).stat().st_size for f in files)
        shot = render_url(story["url"], args.originals / f"{slug}.png", proxy, ORIGINAL_MAX_HEIGHT).to_json()
        rows.append({"id": slug, "kind": "pudding", "ok": True, "data": slug, "files": files, "bytes": size,
                     **story, "original": shot})
        print(f"{slug}: {len(files)} files {size / 1e6:.2f} MB | {story['published']} | {story['title'][:50]} | "
              f"original {shot['verdict']} height={shot['page_height']} hang={shot['hang']} {shot['detail'][:80]}", flush=True)
    (args.out / "manifest.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (args.out / "split.json").write_text(json.dumps({"pudding": STORIES}, indent=1), encoding="utf-8")
    print(f"{len(rows)} datasets in {args.out}", flush=True)


if __name__ == "__main__":
    main()
