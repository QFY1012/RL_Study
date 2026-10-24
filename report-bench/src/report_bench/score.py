"""Score one system's submissions with the judge, the way GEPA scores a page.

    PYTHONPATH=../report-gepa/src:src ../report-gepa/.venv/bin/python -m report_bench.score submissions/<system> [--tasks a,b] [--out runs/<system>] [--workers 4] [--browsers 2] | tee runs/<system>.log

For every task in out/tasks/ the page is submissions/<system>/<id>/index.html.
It is captured (capture.py) with the task's data, then judged: 1.1 from the
capture (it did not open, render or run cleanly: the page scores 0), expression
(2.x) and aesthetics (3.x) in one judge call each. A call whose reply leaves an
item without a score is asked again, up to JUDGE_TRIES times; an item still
without a score is left out of the mean and the result says so. The page's score
is the mean of the scored items, the same formula as report_gepa.optimize.

Output: <out>/<id>/{evidence/, judgements.json, result.json} (reused on a rerun:
a page is not captured or judged twice) and <out>/scores.jsonl, one line per
task; the means by source are printed at the end. A task with no page scores 0.
"""

from __future__ import annotations

import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean

from . import judge as J
from .capture import capture
from .llm import OutOfCredit
from .rubric import load

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "out" / "tasks"
MODEL = "deepseek-v4.1-flash"  # GEPA's judge model, so the scores compare with runs/gepa
JUDGE_TRIES = 3


def score_task(task: str, system: Path, out: Path, browsers: threading.Semaphore, model: str) -> dict:
    base = out / task
    if (base / "result.json").exists():
        return json.loads((base / "result.json").read_text(encoding="utf-8"))
    page = system / task / "index.html"
    if not page.exists():
        return {"task": task, "score": 0.0, "summary": "no page"}
    ev = base / "evidence"
    if not (ev / "evidence.json").exists():
        with browsers:
            capture(str(page.resolve()), ev, None, [TASKS / task / "data"])
    rubric = load()
    scored = [it for it in rubric.values() if it.scored]
    judged = base / "judgements.json"
    items: dict[str, dict] = json.loads(judged.read_text(encoding="utf-8")) if judged.exists() else {}
    gate = J.gate(ev)
    items["1.1"] = {"violated": gate["violated"], "reason": "; ".join(gate["problems"])}
    if not gate["violated"]:
        for dim in ([it for it in scored if it.id.startswith(d)] for d in ("2.", "3.")):
            for _ in range(JUDGE_TRIES):
                if all(items.get(it.id, {}).get("score") is not None for it in dim):
                    break
                try:
                    items.update(J.page_group(dim, ev, model)[1])
                except OutOfCredit:
                    raise
                except Exception as e:  # noqa: BLE001 - a failed call is asked again
                    print(f"[judge] {task} {dim[0].id[0]}.x: FAILED {str(e)[:200]}", flush=True)
    judged.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    parts = {it.id: items[it.id]["score"] for it in scored if items.get(it.id, {}).get("score") is not None}
    missing = [it.id for it in scored if it.id not in parts]
    if gate["violated"]:
        result = {"task": task, "score": 0.0, "vetoed": ["1.1"], "summary": "vetoed by 1.1: " + items["1.1"]["reason"]}
    else:
        result = {"task": task, "score": mean(parts.values()) if parts else 0.0, "parts": parts, "unjudged": missing,
                  "summary": " ".join(f"{k}={v:.2f}" for k, v in parts.items()) + (f"  unjudged {','.join(missing)}" if missing else "")}
    if not missing or gate["violated"]:  # a page with unjudged items is judged again on the next run
        (base / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("system", type=Path, help="submissions/<system>: one <id>/index.html per task")
    ap.add_argument("--tasks", help="comma-separated task ids (default: all)")
    ap.add_argument("--out", type=Path, help="default runs/<system>")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--browsers", type=int, default=2)
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    listed = {json.loads(l)["id"]: json.loads(l)["source"] for l in (ROOT / "out" / "tasks.jsonl").read_text(encoding="utf-8").splitlines()}
    tasks = args.tasks.split(",") if args.tasks else list(listed)
    out = args.out or ROOT / "runs" / args.system.name
    out.mkdir(parents=True, exist_ok=True)
    browsers = threading.Semaphore(args.browsers)
    print(f"== {args.system.name}: {len(tasks)} tasks, judge {args.model}, out {out}", flush=True)
    results = {}
    with ThreadPoolExecutor(args.workers) as pool:
        jobs = {pool.submit(score_task, t, args.system, out, browsers, args.model): t for t in tasks}
        for f in as_completed(jobs):
            r = f.result()
            results[jobs[f]] = r
            print(f"{jobs[f]:24} {r['score']:.3f}  {r['summary'][:160]}", flush=True)
    (out / "scores.jsonl").write_text("".join(json.dumps({**results[t], "source": listed[t]}, ensure_ascii=False) + "\n" for t in tasks),
                                      encoding="utf-8")
    for source in dict.fromkeys(listed[t] for t in tasks):
        s = [results[t]["score"] for t in tasks if listed[t] == source]
        print(f"{source:13} {len(s):4d} tasks  mean {mean(s):.3f}", flush=True)
    print(f"{'all':13} {len(tasks):4d} tasks  mean {mean(results[t]['score'] for t in tasks):.3f}", flush=True)


if __name__ == "__main__":
    main()
