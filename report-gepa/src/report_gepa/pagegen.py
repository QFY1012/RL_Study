"""Generate pages for every report as soon as the report exists, alongside datagen.

    PYTHONPATH=src .venv/bin/python -m report_gepa.pagegen data/reports runs/pages | tee runs/pagegen.log

Every report gets pages from four sources, so the pages people label differ in
quality for reasons other than sampling noise. Each page is made by a pi agent
that reads the report file itself (see generate.py):

    seed-ds     guides/seed.md, deepseek-v4.1-flash, 2 pages (also GEPA's reference pages)
    seed-glm    guides/seed.md, glm-5.3-flash, 1 page
    detail-ds   guides/detailed.md, deepseek-v4.1-flash, 1 page
    pudding-ds  guides/pudding.md, deepseek-v4.1-flash, 1 page

The loop rereads datagen's manifest every 30 s and queues what is missing; a
page whose record.json exists is skipped, so a restart resumes. --pages limits
the run to some of the names (seed-ds-1, pudding-ds-1, ...). It exits once
datagen has written split.json and every queued page is done, or as soon as the
endpoint says the balance is too low; that page leaves no record, so the next
run makes it.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .generate import GUIDES, generate_page
from .llm import OutOfCredit

SOURCES = {
    "seed-ds": ("deepseek-v4.1-flash", "seed.md", 2),
    "seed-glm": ("glm-5.3-flash", "seed.md", 1),
    "detail-ds": ("deepseek-v4.1-flash", "detailed.md", 1),
    "pudding-ds": ("deepseek-v4.1-flash", "pudding.md", 1),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reports", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--renders", type=int, default=3, help="browsers open at the same time")
    ap.add_argument("--pages", help="only these page names, comma-separated (e.g. seed-ds-1,pudding-ds-1)")
    args = ap.parse_args()
    only = set(args.pages.split(",")) if args.pages else None

    render_slots = threading.Semaphore(args.renders)
    queued: set[tuple[str, str]] = set()
    counts = {"done": 0, "delivered": 0, "failed": 0}
    lock = threading.Lock()
    pool = ThreadPoolExecutor(args.workers)
    futures = []
    out_of_credit = threading.Event()

    def run(report_path: Path, rid: str, source: str, name: str):
        if out_of_credit.is_set():
            return
        model, guide, _ = SOURCES[source]
        try:
            rec = generate_page(GUIDES / guide, [report_path], args.out / rid, name, model, render_slots=render_slots)
            rend = rec.get("render", {})
            tries = "/".join(a["problem"] or "ok" for a in rec["attempts"])
            line = (f"{rid}/{name}: delivered={rec['delivered']} tries={tries} {rec['seconds']}s tokens={rec['output_tokens']} "
                    f"verdict={rend.get('verdict')} height={rend.get('page_height')} "
                    f"errors={len(rend.get('page_errors', [])) + len(rend.get('syntax_errors', []))} hang={rend.get('hang')}")
            ok = rec["delivered"]
        except OutOfCredit as e:
            out_of_credit.set()
            print(f"{rid}/{name}: OUT OF CREDIT, stopping: {str(e)[:200]}", flush=True)
            return
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
            report_path = args.reports / row["data"]
            for source, (_, _, n) in SOURCES.items():
                for k in range(1, n + 1):
                    name = f"{source}-{k}"
                    if only is not None and name not in only:
                        continue
                    if (rid, name) in queued or (args.out / rid / name / "record.json").exists():
                        continue
                    queued.add((rid, name))
                    futures.append(pool.submit(run, report_path, rid, source, name))
        data_finished = (args.reports / "split.json").exists()
        if out_of_credit.is_set() or (data_finished and all(f.done() for f in futures)):
            break
        time.sleep(30)
    # out of credit: queued pages are dropped and running ones end at their next request
    pool.shutdown(cancel_futures=out_of_credit.is_set())
    print(f"pages done {counts['done']}: delivered {counts['delivered']}, failed {counts['failed']}"
          + (" (stopped: out of credit)" if out_of_credit.is_set() else ""), flush=True)


if __name__ == "__main__":
    main()
