"""Take The Pudding's published data, with each published story as the bar.

    PYTHONPATH=src .venv/bin/python -m report_gepa.pudding <cache_dir> data/pudding runs/pudding-originals

STORIES is every data story The Pudding publishes data for: the table in the
README of github.com/the-pudding/data, plus folders of that repo the table
leaves out but whose README names a story (gayborhoods, mow). Each story says
where its data is:

    data:<folder>                  a folder of the-pudding/data
    git:<owner>/<repo>[:<path>]    another repo, or one directory or file in it
    http:<url>                     a file published on its own

Repos are cloned into <cache_dir> (shallow, data files only) and reused. The
data files (csv, tsv, json) go to data/pudding/<slug>/, which is what the page
agent gets, with the folder's README when it describes the data. README lines
that link to the published story are dropped, so the task stays "make a report
from this data" rather than "recall this article". The story is screenshotted to
<originals>/<slug>.png the same way generated pages are; "original_static" in
the manifest is false where the page opens on a start button, is a video, or is
an app that fits one screen (falsetto, book-covers, birthday-paradox: a 900px
page with no scrolling story), so neither the screenshot nor the scroll capture
is a usable bar.

Left out: the newsletter dump (winning-the-internet), folders with no story
(clutch) or no data (queues), the Whole Foods story (data only on Notion) and
Human Terrain (a how-to, no data), and stories whose data is thousands of
small files rather than a dataset to report on (wiki-billboard, one file per
person; two-minute-report, one per game; country-radio, one per station plus
the analysis' intermediates). The data repo is MIT licensed; other repos
carry their own licenses.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .render import render_url

DATA_REPO = "the-pudding/data"
DATA_SUFFIXES = (".csv", ".tsv", ".json")
# json files in app repos that are build config, not data
NOT_DATA = {"package.json", "package-lock.json", "tsconfig.json", "jsconfig.json", "manifest.json",
            ".eslintrc.json", "vercel.json", "netlify.json", "now.json", "composer.json", "bower.json"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".svelte-kit"}
STORY_LINK = re.compile(r"pudding\.cool|polygraph\.cool", re.I)
ORIGINAL_MAX_HEIGHT = 30000


@dataclass(frozen=True)
class Story:
    slug: str
    title: str
    url: str
    published: str
    data: str
    static: bool = True  # False: a start button, a video, or an app that fits one screen instead of a scrolling story


STORIES = [
    Story("bears-boys", "Bears Will Be Boys", "https://pudding.cool/2025/07/kids-books/", "July 2025", "git:the-pudding/kids-book-animals:static/assets/data"),
    Story("birthday-effect", "Are you more likely to die on your birthday", "https://pudding.cool/2025/04/birthday-effect/", "April 2025", "data:birthday-effect"),
    Story("mow", "Why some people mow a lawn better than others", "https://pudding.cool/2026/06/mow", "June 2026", "data:mow", static=False),
    Story("romance-covers", "What Does a Happily Ever After Look Like?", "https://pudding.cool/2023/10/romance-covers/", "October 2023", "git:the-pudding/romance-covers-new:src/data/listings.csv"),
    Story("nba-unexpected", "The Greatest Unexpected NBA Performances", "https://www.youtube.com/watch?v=jV49bDzkQhY", "February 2023", "data:nba-unexpected", static=False),
    Story("random", "We think this cool study we found is flawed. Help us reproduce it.", "https://pudding.cool/2022/04/random/", "April 2022", "data:random", static=False),
    Story("banknotes", "Who's in Your Wallet?", "https://pudding.cool/2022/04/banknotes/", "April 2022", "git:the-pudding/banknotes:src/data"),
    Story("women-in-headlines", "When Women Make Headlines", "https://pudding.cool/2022/02/women-in-headlines", "February 2022", "data:women-in-headlines"),
    Story("same-gender-lyrics", "\"I Kissed a Girl\" to \"Call Me By Your Name\"", "https://pudding.cool/2021/06/same-gender-lyrics/", "June 2021", "git:the-pudding/same-gender-lyrics-viz:src/data/data.csv"),
    Story("foundation-names", "The Naked Truth", "https://pudding.cool/2021/03/foundation-names", "March 2021", "data:foundation-names"),
    Story("police-misconduct", "Police Misconduct", "https://pudding.cool/2020/10/police-misconduct/", "October 2020", "git:the-pudding/police_misconduct_pudding:src/assets/data"),
    Story("campaign-colors", "How candidate diversity impacts color diversity", "https://pudding.cool/2020/08/campaign-colors/", "August 2020", "data:campaign-colors"),
    Story("song-decay", "90s Song Memory", "https://pudding.cool/2020/07/song-decay/", "July 2020", "git:the-pudding/song-decay-clean:src/assets/data"),
    Story("infinite", "The Infinite Monkey Theorem Experiment", "https://pudding.cool/2020/04/infinite/", "Apr 2020", "http:https://pudding.cool/2020/04/infinite-data/data.json"),
    Story("kidz-bop", "Just how does Kidz Bop censor songs?", "https://pudding.cool/2020/04/kidz-bop/", "Apr 2020", "data:kidz-bop", static=False),
    Story("census-history", "The Evolution of the American Census", "https://pudding.cool/2020/03/census-history", "Mar 2020", "data:census-history"),
    Story("rain", "Where will you need your umbrella?", "https://pudding.cool/2020/02/rain", "Feb 2020", "data:rain"),
    Story("laugh", "Laughing OnLine", "https://pudding.cool/2019/10/laugh", "Oct 2019", "data:laugh"),
    Story("dog-shelters", "Finding Forever Homes", "https://pudding.cool/2019/10/shelters", "Oct 2019", "data:dog-shelters"),
    Story("falsetto", "Vocal Register and Singing Voices", "https://pudding.cool/2019/08/register/", "Aug 2019", "git:the-pudding/falsetto-story", static=False),
    Story("book-covers", "Book Covers", "https://pudding.cool/2019/07/book-covers/", "July 2019", "git:the-pudding/book-covers", static=False),
    Story("summer-reading", "Hipster Summer Reading List", "https://pudding.cool/2019/06/summer-reading/", "June 2019", "data:summer-reading"),
    Story("music-history", "Best Year in Music", "https://pudding.cool/projects/music-history/", "June 2019", "git:the-pudding/music-taste-2019", static=False),
    Story("people-map-uk", "A People Map of the UK", "https://pudding.cool/2019/06/people-map-uk", "June 2019", "data:people-map-uk", static=False),
    Story("people-map", "A People Map of the US", "https://pudding.cool/2019/05/people-map", "May 2019", "data:people-map", static=False),
    Story("names-in-songs", "Sing My Name", "https://pudding.cool/2019/05/names-in-songs", "May 2019", "data:names-in-songs"),
    Story("hyphens", "The Rise of Hyphenated Last Names in Pro Sports", "https://pudding.cool/2019/05/hyphens/", "May 2019", "git:the-pudding/hyphenated-names"),
    Story("three-seconds", "The NBA Has A Defensive Three Seconds Problem", "https://pudding.cool/2019/05/three-seconds", "May 2019", "data:three-seconds", static=False),
    Story("vogue", "Colorism in High Fashion", "https://pudding.cool/2019/04/vogue", "April 2019", "data:vogue"),
    Story("eu-regions", "EU Regions", "https://pudding.cool/2019/04/eu-regions/", "April 2019", "git:the-pudding/eu-regions:src/assets/data"),
    Story("nba-spelling", "NBA Spell Jam", "https://pudding.cool/2019/03/nba-spelling/", "March 2019", "http:https://pudding.cool/2019/03/sankey-nba-data/data-all.json"),
    Story("pop-music", "Who is the Biggest Pop Star?", "https://pudding.cool/2019/03/pop-music/", "March 2019", "git:the-pudding/telephone:src/assets/data"),
    Story("hype", "How Many High School Stars Make It to the NBA?", "https://pudding.cool/2019/03/hype/", "March 2019", "data:hype"),
    Story("gyllenhaal", "The Gyllenhaal Experiment", "https://pudding.cool/2019/02/gyllenhaal/", "February 2019", "http:https://pudding.cool/2019/02/sankey-data/data-all.json"),
    Story("dress-codes", "The Sexualized Messages Dress Codes are Sending to Students", "https://pudding.cool/2019/02/dress-code-sexualization/", "February 2019", "data:dress-codes"),
    Story("vocabulary", "The Largest Vocabulary in Hip Hop", "https://pudding.cool/projects/vocabulary/index.html", "January 2019", "http:https://docs.google.com/spreadsheets/d/1HIIfgDpNMM-j0hoQHN-yP5P1lNOfJuvym0u0sdWwD9g/export?format=csv&gid=737896402"),
    Story("boybands", "Internet Boy Band Database", "https://pudding.cool/2018/11/boy-bands/", "November 2018", "data:boybands", static=False),
    Story("dearabby", "Thirty Years of American Anxieties", "https://pudding.cool/2018/11/dearabby/", "November 2018", "data:dearabby"),
    Story("titletowns", "The Winningest Cities in North American Sports", "https://pudding.cool/2018/11/titletowns/", "November 2018", "data:titletowns"),
    Story("filmordigital", "Film vs. Digital", "https://pudding.cool/2018/08/filmordigital/", "August 2018", "data:filmordigital"),
    Story("pockets", "Women's Pockets are Inferior", "https://pudding.cool/2018/08/pockets", "August 2018", "data:pockets"),
    Story("wiki-death", "Life After Death on Wikipedia", "https://pudding.cool/2018/08/wiki-death", "August 2018", "git:the-pudding/wiki-death-data"),
    Story("airports", "What Airport Traffic Tells Us About the World's Megacities", "https://pudding.cool/2018/07/airports", "July 2018", "git:the-pudding/airports"),
    Story("birth-control", "Let's Talk About Birth Control", "https://pudding.cool/2018/07/birth_control", "July 2018", "data:birth-control"),
    Story("gayborhoods", "Men are from Chelsea, Women are from Park Slope", "https://pudding.cool/2018/06/gayborhoods/", "June 2018", "data:gayborhoods"),
    Story("makeup-shades", "The Diversity of Makeup Shades", "https://pudding.cool/2018/06/makeup-shades", "June 2018", "data:makeup-shades"),
    Story("skate-music", "The Good, the Rad, and the Gnarly", "https://pudding.cool/2018/06/skate-music/", "June 2018", "data:skate-music"),
    Story("cookies", "Baking the Most Average Chocolate Chip Cookie", "https://pudding.cool/2018/05/cookies", "May 2018", "data:cookies"),
    Story("one-hit-wonders", "One-Hit Wonders in Sports", "https://pudding.cool/2018/04/one-hit-wonders", "April 2018", "data:one-hit-wonders"),
    Story("birthday-paradox", "The Birthday Paradox Experiment", "https://pudding.cool/2018/04/birthday-paradox", "April 2018", "http:https://pudding.cool/2018/04/birthday-data/data.json", static=False),
    Story("neighborhoods", "A Tale of Two Cities", "https://pudding.cool/2018/03/neighborhoods", "March 2018", "data:neighborhoods"),
    Story("stand-up", "The Structure of Stand-Up Comedy", "https://pudding.cool/2018/02/stand-up", "February 2018", "data:stand-up", static=False),
    Story("mars-weather", "Greetings from Mars", "https://pudding.cool/2018/01/mars-weather/", "February 2018", "data:mars-weather"),
    Story("clinics", "How far is too far? An analysis of driving times to abortion clinics in the US.", "https://pudding.cool/2017/09/clinics/", "September 2017", "data:clinics"),
    Story("cetaceans", "Free Willy & Flipper by the Numbers", "https://pudding.cool/2017/07/cetaceans/", "July 2017", "data:cetaceans"),
    Story("births", "The Timing of Baby Making", "https://pudding.cool/2017/05/births/", "May 2017", "data:births"),
]


def sh(*cmd: str, cwd: Path | None = None):
    subprocess.run(cmd, cwd=cwd, check=True, env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"})


def clone(repo: str, cache: Path) -> Path:
    """Shallow clone holding only data files; reused if present."""
    dst = cache / repo.replace("/", "__")
    if not (dst / ".git").exists():
        shutil.rmtree(dst, ignore_errors=True)
        sh("git", "clone", "--depth", "1", "--filter=blob:none", "--no-checkout", "--quiet", f"https://github.com/{repo}", str(dst))
        sh("git", "sparse-checkout", "set", "--no-cone", *(f"*{s}" for s in DATA_SUFFIXES), "README.md", cwd=dst)
        sh("git", "checkout", "--quiet", cwd=dst)
    return dst


def is_data(path: Path, rel: Path) -> bool:
    return (path.is_file() and path.suffix.lower() in DATA_SUFFIXES and path.name not in NOT_DATA
            and not SKIP_DIRS.intersection(rel.parts))


def fetch(story: Story, cache: Path, dst: Path) -> list[str]:
    """Copy the story's data files to dst; return their paths relative to dst."""
    shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True)
    kind, _, where = story.data.partition(":")
    if kind == "http":
        name = Path(urllib.request.urlparse(where).path).name
        name = name if name.endswith(DATA_SUFFIXES) else f"{story.slug}.csv"  # the Google Sheets export
        with urllib.request.urlopen(where, timeout=120) as r:
            (dst / name).write_bytes(r.read())
        return [name]
    repo, _, sub = (DATA_REPO, ":", where) if kind == "data" else where.partition(":")
    src = clone(repo, cache) / sub
    if src.is_file():
        shutil.copy2(src, dst / src.name)
        return [src.name]
    files = []
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if is_data(path, rel):
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst / rel)
            files.append(str(rel))
    # the data repo's READMEs describe the data; an app repo's README describes the app
    readme = src / "README.md"
    if kind == "data" and readme.exists():
        lines = [line for line in readme.read_text(encoding="utf-8").splitlines() if not STORY_LINK.search(line)]
        (dst / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cache", type=Path, help="where repos are cloned")
    ap.add_argument("out", type=Path)
    ap.add_argument("originals", type=Path)
    args = ap.parse_args()

    args.cache.mkdir(parents=True, exist_ok=True)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    rows = []
    for story in STORIES:
        try:
            files = fetch(story, args.cache, args.out / story.slug)
        except Exception as e:  # noqa: BLE001 - one missing source must not stop the rest
            print(f"{story.slug}: DATA FAILED {str(e)[:200]}", flush=True)
            continue
        size = sum((args.out / story.slug / f).stat().st_size for f in files)
        if not files:
            print(f"{story.slug}: NO DATA FILES in {story.data}", flush=True)
            continue
        shot = render_url(story.url, args.originals / f"{story.slug}.png", proxy, ORIGINAL_MAX_HEIGHT).to_json()
        rows.append({"id": story.slug, "kind": "pudding", "ok": True, "data": story.slug, "files": files, "bytes": size,
                     "title": story.title, "url": story.url, "published": story.published, "source": story.data,
                     "original_static": story.static, "original": shot})
        print(f"{story.slug}: {len(files)} files {size / 1e6:.2f} MB | {story.published} | {story.title[:50]} | "
              f"original {shot['verdict']} height={shot['page_height']} hang={shot['hang']} {shot['detail'][:80]}", flush=True)
    (args.out / "manifest.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (args.out / "split.json").write_text(json.dumps({"pudding": [r["id"] for r in rows]}, indent=1), encoding="utf-8")
    print(f"{len(rows)} datasets in {args.out}", flush=True)


if __name__ == "__main__":
    main()
