"""Collect every Pudding original next to every page generated from its data.

    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.pairs runs/pairs [--capture-missing] | tee runs/pairs.log

For each story of data/pudding (the ones whose original is a Pudding page) the
original and all generated pages go to <out>/<story>/:

- original/: url.txt, the full-page screenshot (fullpage.png, from
  runs/pudding-originals/) and the scroll capture (evidence.json, thumb.jpg,
  frames/, from runs/evidence/<story>/original/). --capture-missing first captures
  the originals that have none, into runs/evidence/<story>/original/.
- pages/<page id>/: index.html, the scroll capture when the page has one, and
  what judged it: result.json (GEPA-style runs) or reward.json (TF-GRPO), and
  judge/<run>/ (runs/judge records of the pudding-pages versions).

Generated pages come from runs/pudding-pages (one page per version), every
GEPA-style run (report-gepa runs/*/rollouts and runs/gepa/*/rollouts,
report-tfgrpo runs/*/val/rollouts; one page per guide) and the TF-GRPO steps
(report-tfgrpo runs/<run>/step-NN/<story>/page-K). The prompt each was written
with goes to <out>/guides/. <out>/pairs.jsonl has one line per generated page
(story, page id, where it came from, its guide, its score) and the human
original-vs-generated labels of labels/round1 where there are any;
<out>/stories.jsonl has one line per story.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

from report_bench.capture import capture

from .optimize import DATA

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"
TFGRPO = ROOT.parent / "report-tfgrpo" / "runs"
EVIDENCE = RUNS / "evidence"
LABELS = ROOT / "labels" / "round1"
LABELLED_VERSION = "pudding-ds-1"  # the generated page the annotators compared with the original


def copy_capture(src: Path, dst: Path) -> bool:
    if not (src / "evidence.json").exists():
        return False
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("evidence.json", "thumb.jpg"):
        if (src / name).exists():
            shutil.copy2(src / name, dst / name)
    if (src / "frames").is_dir():
        shutil.copytree(src / "frames", dst / "frames", dirs_exist_ok=True)
    return True


def human_labels() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for path in sorted(LABELS.glob("annotator-*.csv")):
        if path.stem.endswith("-boxes"):
            continue
        boxes = LABELS / f"{path.stem}-boxes.csv"
        notes = list(csv.DictReader(boxes.open(encoding="utf-8-sig"))) if boxes.exists() else []
        for row in csv.DictReader(path.open(encoding="utf-8-sig")):
            out.setdefault(row["dataset"], []).append(
                {"annotator": path.stem.removeprefix("annotator-"), "generated": LABELLED_VERSION, "winner": row["winner"],
                 "choice": row["choice"], "reason": row.get("reason", ""),
                 "boxes": [{k: b[k] for k in ("pane", "version", "tag", "note", "x", "y", "w", "h")}
                           for b in notes if b["dataset"] == row["dataset"]]})
    return out


def pudding_pages(story: str) -> list[dict]:
    pages = []
    for d in sorted((RUNS / "pudding-pages" / story).glob("*/index.html")):
        version = d.parent.name
        judge = {run.name: run / "page" / story / version for run in sorted((RUNS / "judge").glob("*"))
                 if (run / "page" / story / version).is_dir()}
        pages.append({"id": version, "source": "pudding-pages", "html": d, "capture": EVIDENCE / story / version,
                      "judge": judge, "guide": None, "score": None})
    return pages


def gepa_pages(story: str) -> list[dict]:
    roots = sorted(RUNS.glob("*/rollouts")) + sorted(RUNS.glob("gepa/*/rollouts")) + sorted(TFGRPO.glob("*/val/rollouts"))
    pages = []
    for rollouts in roots:
        run = rollouts.parent
        project, home = ("report-tfgrpo", TFGRPO) if TFGRPO in run.parents else ("report-gepa", RUNS)
        name = str(run.relative_to(home))
        for base in sorted(rollouts.glob(f"*/{story}")):
            if not (base / "page" / "index.html").exists():
                continue
            h = base.parent.name
            result = base / "result.json"
            pages.append({"id": f"{project}-{name.replace('/', '-')}-{h}", "source": f"{project}:{name}", "html": base / "page" / "index.html",
                          "capture": base / "evidence", "judgements": base / "judgements.json", "result": result,
                          "guide": (run / "guides" / f"{h}.md", f"{project}-{name.replace('/', '-')}-{h}.md"),
                          "score": json.loads(result.read_text(encoding="utf-8"))["score"] if result.exists() else None})
    return pages


def tfgrpo_pages(story: str) -> list[dict]:
    pages = []
    for step in sorted(TFGRPO.glob("*/step-*")):
        folder = step / story
        if not folder.is_dir():
            continue
        run = step.parent.name
        rewards = {}
        if (step / "rollouts.json").exists():
            for group in json.loads((step / "rollouts.json").read_text(encoding="utf-8")):
                if group["story"] == story:
                    rewards = {r["page"]: r for r in group["rollouts"]}
        judged = json.loads((folder / "judgements.json").read_text(encoding="utf-8")) if (folder / "judgements.json").exists() else {}
        for html in sorted(folder.glob("page-*/index.html")):
            k = html.parent.name.removeprefix("page-")
            ev = f"ev-{k}"
            r = rewards.get(ev, {})
            pages.append({"id": f"report-tfgrpo-{run}-{step.name}-{k}", "source": f"report-tfgrpo:{run}", "html": html,
                          "capture": folder / ev, "reward": {"reward": r.get("reward"), "summary": r.get("summary"), "judgements": judged.get(ev)},
                          "guide": (step / "system.md", f"report-tfgrpo-{run}-{step.name}.md"), "score": r.get("reward")})
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--capture-missing", action="store_true", help="capture the originals that have no scroll capture yet")
    args = ap.parse_args()

    stories = [json.loads(line) for line in (DATA / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    labels = human_labels()
    shutil.rmtree(args.out, ignore_errors=True)
    (args.out / "guides").mkdir(parents=True)
    pair_lines, story_lines = [], []
    for s in stories:
        story = s["id"]
        orig_ev = EVIDENCE / story / "original"
        if args.capture_missing and not (orig_ev / "evidence.json").exists():
            print(f"{story:22} capturing the original {s['url']}", flush=True)
            capture(s["url"], orig_ev)
        o = args.out / story / "original"
        o.mkdir(parents=True)
        (o / "url.txt").write_text(s["url"] + "\n", encoding="utf-8")
        shot = RUNS / "pudding-originals" / f"{story}.png"
        if shot.exists():
            shutil.copy2(shot, o / "fullpage.png")
        captured = copy_capture(orig_ev, o)
        pages = pudding_pages(story) + gepa_pages(story) + tfgrpo_pages(story)
        for p in pages:
            d = args.out / story / "pages" / p["id"]
            d.mkdir(parents=True)
            shutil.copy2(p["html"], d / "index.html")
            p["captured"] = copy_capture(p["capture"], d)
            for key in ("judgements", "result"):
                if p.get(key) and p[key].exists():
                    shutil.copy2(p[key], d / p[key].name)
            if p.get("reward"):
                (d / "reward.json").write_text(json.dumps(p["reward"], ensure_ascii=False, indent=1), encoding="utf-8")
            for run, src in p.get("judge", {}).items():
                shutil.copytree(src, d / "judge" / run)
            guide = None
            if p["guide"] and p["guide"][0].exists():
                guide = p["guide"][1]
                if not (args.out / "guides" / guide).exists():
                    shutil.copy2(p["guide"][0], args.out / "guides" / guide)
            human = [h for h in labels.get(story, []) if p["source"] == "pudding-pages" and p["id"] == h["generated"]]
            pair_lines.append({"story": story, "page": p["id"], "source": p["source"], "guide": guide, "score": p["score"],
                               "captured": p["captured"], "judge_runs": sorted(p.get("judge", {})), "human": human})
        story_lines.append({"story": story, "title": s["title"], "url": s["url"], "published": s.get("published"),
                            "original_static": s.get("original_static"), "original_fullpage": shot.exists(),
                            "original_captured": captured, "pages": len(pages), "human_labels": len(labels.get(story, []))})
        print(f"{story:22} {len(pages):4d} pages  original {'captured' if captured else 'NOT captured'}"
              f"{', full-page shot' if shot.exists() else ''}{f', {len(labels[story])} human labels' if story in labels else ''}", flush=True)
    (args.out / "pairs.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in pair_lines), encoding="utf-8")
    (args.out / "stories.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in story_lines), encoding="utf-8")
    print(f"{len(story_lines)} stories, {len(pair_lines)} generated pages, "
          f"{sum(1 for r in story_lines if r['original_captured'])} originals captured, "
          f"{sum(len(r['human']) for r in pair_lines)} human labels -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
