"""The score of a page: the one definition the benchmark, GEPA and TF-GRPO share.

    PYTHONPATH=../report-gepa/src:src ../report-gepa/.venv/bin/python -m report_bench.score submissions/<system> [--tasks a,b] [--out runs/<system>] [--workers 4] [--browsers 2] | tee runs/<system>.log

score_page scores one delivered page (a folder with index.html and facts.json,
see TASK.md) made from `data`, the files and folders its writer found in data/:

1. capture: the page is captured with the data (capture.py) into <out>/evidence.
2. trust (1.x, trust.py): renders, refs hold, data accurate. Any violated item
   makes the score 0 and the page is not judged further: a page that misstates
   its data is not a better page for being clear or pretty.
3. expression (2.x) and aesthetics (3.x): one judge call each (judge.py).
4. the score: the mean of the scored items, equal weights until weights are
   fitted on whole-page labels.

A check that gives no usable answer (1.3 without parseable JSON, a judge call
that leaves an item without a score) is asked again, up to TRIES times in all;
the tries are kept, so a restart does not ask a hopeless page again. A page whose
checks are still missing an answer is `complete: false`: its score covers only
what was answered, and callers that compare pages (TF-GRPO) leave it out.

Everything is kept in <out>: evidence/, trust.json, judgements.json and
result.json, and reused when present, so a restart or a repeated request costs
nothing. The result's feedback lines (every trust problem, every item's score and
reason, the page's scroll facts) are what GEPA reflects on.

The benchmark command scores submissions/<system>/<id>/ for every task in
out/tasks/ with the task's data, writes <out>/scores.jsonl and prints the means by
source. A task with no page scores 0.
"""

from __future__ import annotations

import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from pathlib import Path
from statistics import mean

from . import judge as J
from . import trust as T
from .capture import capture
from .llm import OutOfCredit
from .rubric import load

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "out" / "tasks"
MODEL = "deepseek-v4.1-flash"  # GEPA's and TF-GRPO's judge, so benchmark scores compare with their runs
TRIES = 3


def _read(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")


def _trust(page: Path, ev: Path, out: Path, model: str) -> dict:
    path = out / "trust.json"
    record = _read(path, None)
    tries = record["tries"] if record else 0
    while tries < TRIES and (record is None or record["items"].get("1.3", {}).get("violated", False) is None):
        tries += 1
        record = {**T.trust(ev, page / "facts.json", model), "tries": tries}
        if "1.3" in record["items"]:
            (out / "trust-prompt.txt").write_text(record["items"]["1.3"].pop("prompt"), encoding="utf-8")
        _write(path, record)
    return record


def _judge(ev: Path, out: Path, model: str) -> dict:
    path = out / "judgements.json"
    items = _read(path, {})
    tries = items.setdefault("tries", {})
    scored = [it for it in load().values() if it.scored]
    for dim in ([it for it in scored if it.id.startswith(d)] for d in ("2.", "3.")):
        name = dim[0].id[0] + ".x"
        while tries.get(name, 0) < TRIES and not all(items.get(it.id, {}).get("score") is not None for it in dim):
            tries[name] = tries.get(name, 0) + 1
            try:
                items.update(J.page_group(dim, ev, model)[1])
            except OutOfCredit:
                raise
            except Exception as e:  # noqa: BLE001 - asked again; still missing, the page is incomplete
                print(f"[judge] {out.name} {name}: FAILED {str(e)[:200]}", flush=True)
            _write(path, items)
    return items


def score_page(page: Path, data: list[Path], out: Path, model: str = MODEL, browsers: threading.Semaphore | None = None) -> dict:
    """Score the page in `page` (index.html, facts.json) made from `data`; see the module text."""
    path = out / "result.json"
    if path.exists():
        return _read(path, None)
    out.mkdir(parents=True, exist_ok=True)
    ev = out / "evidence"
    if not (ev / "evidence.json").exists():
        with browsers or nullcontext():
            capture(str((page / "index.html").resolve()), ev, None, data)
    trust = _trust(page, ev, out, model)
    feedback = T.feedback(trust)
    rubric = {it.id: it for it in load().values() if it.scored}
    if trust["vetoed"]:
        result = {"score": 0.0, "vetoed": trust["vetoed"], "parts": {}, "complete": True,
                  "summary": "vetoed by " + ",".join(trust["vetoed"])}
    else:
        items = _judge(ev, out, model)
        parts = {k: items[k]["score"] for k in rubric if items.get(k, {}).get("score") is not None}
        for k, it in rubric.items():
            if k in parts:
                r = items[k]
                feedback.append(f"{k} {it.name}:{parts[k]:.2f}。{r.get('where') or ''} {r.get('reason') or ''}".strip())
        missing = [k for k in rubric if k not in parts]
        unchecked = trust["items"].get("1.3", {}).get("violated") is None
        result = {"score": mean(parts.values()) if parts else 0.0, "vetoed": [], "parts": parts,
                  "complete": not missing and not unchecked,
                  "summary": " ".join(f"{k}={v:.2f}" for k, v in parts.items())
                             + (f"  unjudged {','.join(missing)}" if missing else "") + ("  1.3 unchecked" if unchecked else "")}
    e = _read(ev / "evidence.json", {})
    feedback.append(f"页面高 {e.get('page_height')}px,滚动截了 {len(e.get('frames', []))} 帧,"
                    f"滚动时固定在屏幕上的图 {sum(1 for c in e.get('scroll_story', []) if c['pinned'])} 张。")
    result["feedback"] = feedback
    _write(path, result)
    return result


def task_data(task: str) -> list[Path]:
    """A benchmark task's files, as a submission's writer finds them in data/."""
    return sorted((TASKS / task / "data").iterdir())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("system", type=Path, help="submissions/<system>: one <id>/ with index.html and facts.json per task")
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

    def one(task: str) -> dict:
        if not (args.system / task / "index.html").exists():
            return {"score": 0.0, "summary": "no page"}
        return score_page(args.system / task, task_data(task), out / task, args.model, browsers)

    results = {}
    with ThreadPoolExecutor(args.workers) as pool:
        jobs = {pool.submit(one, t): t for t in tasks}
        for f in as_completed(jobs):
            r = f.result()
            results[jobs[f]] = r
            print(f"{jobs[f]:24} {r['score']:.3f}  {r['summary'][:160]}", flush=True)
    (out / "scores.jsonl").write_text("".join(json.dumps({"task": t, "source": listed[t], **{k: v for k, v in results[t].items() if k != "feedback"}},
                                                         ensure_ascii=False) + "\n" for t in tasks), encoding="utf-8")
    for source in dict.fromkeys(listed[t] for t in tasks):
        s = [results[t]["score"] for t in tasks if listed[t] == source]
        print(f"{source:13} {len(s):4d} tasks  mean {mean(s):.3f}", flush=True)
    print(f"{'all':13} {len(tasks):4d} tasks  mean {mean(results[t]['score'] for t in tasks):.3f}", flush=True)


if __name__ == "__main__":
    main()
