"""Write benchmark submissions with the pi agent: one model, some tasks, a page each.

    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.bench <system> --model m --tasks a,b [--guide guides/seed.md] [--workers 3]

Each task gets what a participant gets (report-bench/out/tasks/<id>/: the
instruction, which is TASK.md, the title and the data files) plus how to look at
the page with pageshot, as in generate.py. The agent writes index.html and
facts.json into report-bench/submissions/<system>/<id>/, beside record.json (the
agent's runs) and session.jsonl; the copied data is removed afterwards. A task
whose record.json exists is skipped. Score the submissions with report_bench.score.
"""

from __future__ import annotations

import argparse
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from report_bench.llm import OutOfCredit, credit_refused

from .generate import GUIDES, MAX_ATTEMPTS, ROOT, TOOLS, page_problem, run_agent

BENCH = ROOT.parent / "report-bench"
TASKS = BENCH / "out" / "tasks"
SUBMISSIONS = BENCH / "submissions"


def task_text(task_id: str) -> str:
    task = json.loads((TASKS / task_id / "task.json").read_text(encoding="utf-8"))
    return f"Title: {task['title']}\n\n{task['instruction']}{TOOLS}"


def submit(system: str, task_id: str, model: str, guide: Path) -> dict:
    out = SUBMISSIONS / system
    ws = out / task_id
    task_path = out / f"{task_id}.task.md"
    out.mkdir(parents=True, exist_ok=True)
    task_path.write_text(task_text(task_id), encoding="utf-8")
    record = {"task": task_id, "model": model, "guide": str(guide.relative_to(ROOT)), "attempts": []}
    for _ in range(MAX_ATTEMPTS):
        shutil.rmtree(ws, ignore_errors=True)
        shutil.copytree(TASKS / task_id / "data", ws / "data")
        run = run_agent(ws, guide, model, "high", f"  {system}/{task_id}", task_path)
        if credit_refused(run.get("error")):
            shutil.rmtree(ws, ignore_errors=True)
            raise OutOfCredit(run["error"])
        run["problem"] = page_problem(ws)
        record["attempts"].append(run)
        shutil.rmtree(ws / "data")
        if run["problem"] is None:
            break
    record["delivered"] = record["attempts"][-1]["problem"] is None
    record["seconds"] = sum(a.get("seconds", 0) for a in record["attempts"])
    (ws / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("system", help="the submission's folder name under report-bench/submissions/")
    ap.add_argument("--model", required=True)
    ap.add_argument("--tasks", required=True, help="comma-separated task ids")
    ap.add_argument("--guide", type=Path, default=GUIDES / "seed.md")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    guide = args.guide.resolve()

    def one(task_id):
        if (SUBMISSIONS / args.system / task_id / "record.json").exists():
            return
        r = submit(args.system, task_id, args.model, guide)
        print(f"{args.system}/{task_id}: delivered={r['delivered']} attempts={len(r['attempts'])} {r['seconds']}s "
              f"{r['attempts'][-1].get('problem') or ''}", flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(one, args.tasks.split(",")))


if __name__ == "__main__":
    main()
