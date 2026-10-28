"""Write down a Pudding story's findings, as facts, with a pi agent that reads the story on the web.

    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.originals <out_dir> [id ...] [--workers 8] [--model m]

These are the answers for rubric 2.1 (finding coverage): the findings the
original's authors drew from the task's data, written the way a page's
facts.json is (report-bench/TASK.md), so a page's facts can be matched against
them. Without ids, every task with an original.json in report-bench/out/answers.

The agent (agent/gen.mjs with WEB_TOOLS=1) gets the task's data under data/ and
the story's address. It reads the story with web_fetch and web_view (agent/web.mjs,
run outside the sandbox), lists every finding the authors state or label, and
writes the ones the data reproduces as facts, each quoting the story's words in
`source`; the rest go to skipped.json with the reason. Then every fact is run
again and its claim read against its printout, as trust.py does for a page (1.2,
1.3), and its source looked up in the text the agent's web tools returned. The
facts that pass are the answer, answer.json; the others are listed in
record.json under `dropped`. Each task lives in <out_dir>/<id>/: facts.json (the
agent's), answer.json, skipped.json, record.json and session.jsonl; the copied
data is removed afterwards. A task whose answer.json exists is skipped, so a
stopped run picks up where it was. With --answers, answer.json is also copied to
report-bench/out/answers/<id>/facts.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from report_bench.llm import OutOfCredit, credit_refused
from report_bench.trust import claims_hold, run_facts

from .generate import GEN_MODEL, ROOT, run_agent

BENCH = ROOT.parent / "report-bench" / "out"

SYSTEM = """You are a careful data analyst. You read a published data story and write down, as checkable facts, the findings its authors drew from their data. You quote the story exactly, you compute every number from the files you are given, and you never type a number into code. You work in English."""

TASK = """The folder `data/` holds the data behind a published data story, "{title}": {url}
The files: {files}

Write down the story's findings that this data reproduces.

1. Read the story on the web. web_fetch returns the page as the server sends it. web_view opens it in a browser and scrolls it like a reader, so it also gets text drawn by scripts, chart labels and the text of scrolling steps: use it when web_fetch returns little of the story, and to read what the charts label. Follow links to the story's methods or data notes when they say how a number was computed.
2. List every finding the authors draw from data: each number, comparison, ranking, share, trend or pattern the text states or a chart labels. A description of the data itself is not a finding: how many records, people, items, categories or sources it has, and how it was collected. When a chart states the same thing for each of its items (the top three for each phrase, the share for each year), that is one finding, written as one fact whose code computes it for every item at once.
3. Write each finding the files in data/ can reproduce as a fact in `facts.json`:

```json
[{{"id": "women-front-shorter",
  "source": "On average, the pockets in women's jeans are 48% shorter and 6.5% narrower than men's pockets.",
  "claim": "Women's front pockets average 14.3 cm of maximum height against 23.1 cm for men.",
  "tables": {{"m": "data/measurements.csv"}},
  "code": "m.groupby('menWomen').maxHeightFront.mean()"}}]
```

- `id`: unique in the file, a few meaningful words.
- `source`: the story's own words for this finding, quoted exactly, from its text or a chart label.
- `claim`: the finding in one sentence, with the numbers the code prints, and nothing the printout does not show: the story's own wording and numbers belong in `source`, not in the claim.
- `tables`: the files the code reads, each a variable name and the file's path from this folder, such as `data/orders.csv`; every file is read with `pd.read_csv(path)`.
- `code`: one Python expression over those variables, with `pd` (pandas) and `np` (numpy) available: the plain pandas computation whose printout shows the finding, such as a filter, a group-by, a count, a share or a sort. Do not assemble the result into a hand-made Series or dict.

Evaluate every fact from this folder the way it will be checked: read its `tables` with `pd.read_csv`, evaluate its `code`, print the value the way pandas prints it, and read the printout against the claim and the source. Every number, name and comparison in the claim must be in the printout, computed from the tables: code that writes a number itself, such as a string or a Series of typed-in values, does not count. The printout must agree with the story's numbers, up to rounding. Use the story's own definitions and filters, from its text or methods: a term means the same in every fact (if making it past the rookie contract is more than two seasons in one fact, it is more than two seasons in all of them), and a range, threshold or subset is one the story uses, never one chosen to make a number come out right. If the story's number only comes out under a definition or filter the story does not use, the finding is not reproduced. If after a fair try the data does not give the story's number (it needs other data, a different period, or the numbers differ beyond rounding), leave the finding out of facts.json.

4. Write `skipped.json`: every finding you left out, as [{{"source": "the story's words", "why": "..."}}].

Deliver both files, even when the data reproduces none of the story's findings: then `facts.json` is `[]`.
"""


def task_text(task_id: str) -> str:
    original = json.loads((BENCH / "answers" / task_id / "original.json").read_text(encoding="utf-8"))
    task = json.loads((BENCH / "tasks" / task_id / "task.json").read_text(encoding="utf-8"))
    return TASK.format(title=original["title"], url=original["url"], files=", ".join(task["files"]))


def _norm(s: str) -> str:
    return re.sub(r"[\W_]+", " ", s.replace("\u2019", "'")).lower().strip()


def quoted(source: str, read: str) -> bool:
    """Whether every part of a quote is in what was read; parts joined by an ellipsis may sit apart, as chart labels do."""
    parts = [_norm(x) for x in re.split(r"\.\.\.|\u2026", source)]
    return bool(any(parts)) and all(x in read for x in parts if x)


def read_on_web(session: Path) -> str:
    """Everything the agent's web tools returned, normalised for looking quotes up."""
    text = []
    for line in session.read_text(encoding="utf-8").splitlines():
        try:
            m = json.loads(line).get("message", {})
        except json.JSONDecodeError:  # a line cut off while the file was written
            continue
        if m.get("role") == "toolResult" and m.get("toolName") in ("web_fetch", "web_view"):
            text += [c.get("text", "") for c in m.get("content", []) if c.get("type") == "text"]
    return _norm(" ".join(text))


def extract(task_id: str, out_dir: Path, model: str, effort: str = "high") -> dict:
    ws = out_dir / task_id
    shutil.rmtree(ws, ignore_errors=True)
    shutil.copytree(BENCH / "tasks" / task_id / "data", ws / "data")
    task_path = out_dir / f"{task_id}.task.md"
    task_path.write_text(task_text(task_id), encoding="utf-8")
    system_path = out_dir / "system.md"
    run = run_agent(ws, system_path, model, effort, f"  {task_id}", task_path, output="facts.json")
    if credit_refused(run.get("error")):
        shutil.rmtree(ws, ignore_errors=True)
        raise OutOfCredit(run["error"])
    record = {"id": task_id, "model": model, "effort": effort, "run": run}
    data = sorted((ws / "data").iterdir())
    problems, facts, results = run_facts(ws / "facts.json", data)
    record["facts"] = len(facts)
    record["problems"] = problems
    if not facts and not problems:  # the story states nothing this data reproduces
        record["dropped"], record["answer"] = [], 0
        (ws / "answer.json").write_text("[]", encoding="utf-8")
    if facts and not problems:
        check = claims_hold(facts, results, model)
        record["wrong"] = check["wrong"]
        record["verdicts"] = check["verdicts"]
        if check["wrong"] is not None:
            read = read_on_web(ws / "session.jsonl") if (ws / "session.jsonl").exists() else ""
            wrong = {v["id"] for v in check["wrong"]}
            dropped = [{"id": f["id"], "why": "claim does not agree with its printout"} for f in facts if f["id"] in wrong]
            dropped += [{"id": f["id"], "why": "source not in the story as read"} for f in facts
                        if f["id"] not in wrong and not quoted(str(f.get("source", "")), read)]
            gone = {d["id"] for d in dropped}
            answer = [f for f in facts if f["id"] not in gone]
            record["dropped"] = dropped
            record["answer"] = len(answer)
            (ws / "answer.json").write_text(json.dumps(answer, ensure_ascii=False, indent=1), encoding="utf-8")
    skipped = ws / "skipped.json"
    try:
        record["skipped"] = len(json.loads(skipped.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError):
        record["skipped"] = None
    shutil.rmtree(ws / "data")
    (ws / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--model", default=GEN_MODEL)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--answers", action="store_true", help="copy each answer.json to report-bench/out/answers/<id>/facts.json")
    args = ap.parse_args()
    ids = args.ids or sorted(p.parent.name for p in (BENCH / "answers").glob("*/original.json"))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "system.md").write_text(SYSTEM, encoding="utf-8")
    os.environ["WEB_TOOLS"] = "1"  # run_agent passes the environment on to gen.mjs

    def one(task_id):
        if (args.out / task_id / "answer.json").exists():  # done in an earlier run
            return
        try:
            r = extract(task_id, args.out, args.model)
        except OutOfCredit:
            raise
        except Exception as e:  # noqa: BLE001 - one task's failure is reported, not the end of the run
            print(f"{task_id}: crashed {type(e).__name__}: {str(e)[:200]}", flush=True)
            return
        answer = args.out / task_id / "answer.json"
        if args.answers and answer.exists():
            shutil.copy2(answer, BENCH / "answers" / task_id / "facts.json")
        print(f"{task_id}: facts={r['facts']} answer={r.get('answer')} dropped={len(r.get('dropped', []))} "
              f"skipped={r['skipped']} problems={len(r['problems'])} {r['run'].get('seconds')}s steps={r['run'].get('steps')}",
              flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(one, ids))


if __name__ == "__main__":
    main()
