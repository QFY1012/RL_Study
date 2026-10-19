"""Generate pages for every report as soon as the report exists, alongside datagen.

    PYTHONPATH=src .venv/bin/python -m report_gepa.pagegen data/reports runs/pages | tee runs/pagegen.log

Every report gets pages from three sources, so the pages people label differ in
quality for reasons other than sampling noise:

    seed-ds    seed guide, deepseek-v4.1-flash, 2 pages (also GEPA's reference pages)
    seed-glm   seed guide, glm-5.3-flash, 1 page
    detail-ds  guides/detailed.md, deepseek-v4.1-flash, 1 page

The loop rereads datagen's manifest every 30 s and queues what is missing; a
page whose record exists is skipped, so a restart resumes. It exits once
datagen has written split.json and every queued page is done.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .generate import SEED_GUIDE, generate_page
from .llm import LLM

GUIDES_DIR = Path(__file__).resolve().parents[2] / "guides"

SOURCES = {
    "seed-ds": ("deepseek-v4.1-flash", "seed", 2),
    "seed-glm": ("glm-5.3-flash", "seed", 1),
    "detail-ds": ("deepseek-v4.1-flash", "detailed.md", 1),
}


def load_guide(name: str) -> str:
    return SEED_GUIDE if name == "seed" else (GUIDES_DIR / name).read_text(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reports", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--renders", type=int, default=3, help="browsers open at the same time")
    args = ap.parse_args()

    llms = {model: LLM(model=model) for model, _, _ in SOURCES.values()}
    guides = {src: load_guide(g) for src, (_, g, _) in SOURCES.items()}
    render_slots = threading.Semaphore(args.renders)
    queued: set[tuple[str, str]] = set()
    counts = {"done": 0, "delivered": 0, "failed": 0}
    lock = threading.Lock()
    pool = ThreadPoolExecutor(args.workers)
    futures = []

    def run(report_path: Path, rid: str, source: str, name: str):
        model, _, _ = SOURCES[source]
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            rec = generate_page(llms[model], guides[source], report, args.out / rid, name, render_slots)
            rend = rec.get("render", {})
            tries = "/".join(a["problem"] or "ok" for a in rec["attempts"])
            line = (f"{rid}/{name}: delivered={rec['delivered']} tries={tries} {rec['seconds']}s tokens={rec['completion_tokens']} "
                    f"verdict={rend.get('verdict')} height={rend.get('page_height')} "
                    f"errors={len(rend.get('page_errors', [])) + len(rend.get('syntax_errors', []))} hang={rend.get('hang')}")
            ok = rec["delivered"]
        except Exception as e:  # noqa: BLE001 - one page must not stop the pipeline
            line, ok = f"{rid}/{name}: FAILED {str(e)[:200]}", False
        with lock:
            counts["done"] += 1
            counts["delivered" if ok else "failed"] += 1
            print(f"[{counts['done']}/{len(queued)}] {line}", flush=True)

    manifest = args.reports / "manifest.jsonl"
    while True:
        # a report is listed in the manifest only after its file is fully written
        rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()] \
            if manifest.exists() else []
        for row in sorted((r for r in rows if r["ok"]), key=lambda r: r["id"]):
            rid = row["id"]
            report_path = args.reports / row["kind"] / f"{rid}.json"
            for source, (_, _, n) in SOURCES.items():
                for k in range(1, n + 1):
                    name = f"{source}-{k}"
                    if (rid, name) in queued or (args.out / rid / f"{name}.json").exists():
                        continue
                    queued.add((rid, name))
                    futures.append(pool.submit(run, report_path, rid, source, name))
        data_finished = (args.reports / "split.json").exists()
        if data_finished and all(f.done() for f in futures):
            break
        time.sleep(30)
    pool.shutdown()
    print(f"pages done {counts['done']}: delivered {counts['delivered']}, failed {counts['failed']}", flush=True)


if __name__ == "__main__":
    main()
