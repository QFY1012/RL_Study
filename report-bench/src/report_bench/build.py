"""Build the benchmark's task folders from report-gepa's data.

    python3 -m report_bench.build <out>

For every task in tasks.json the one table goes to <out>/tasks/<id>/data.csv
(a tsv becomes a csv) and <out>/tasks/<id>/task.json gets the task statement:
the fixed instruction (TASK.md) and the task's one-line title. <out>/tasks.jsonl
lists every task with its source and table shape. A mock task's planted findings
go to <out>/answers/<id>/findings.json, which participants do not get.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / "report-gepa" / "data"
SOURCES = {"pudding": DATA / "pudding", "pudding-web": DATA / "pudding-web", "mock": DATA / "mock"}
TASKS = ROOT / "tasks.json"
INSTRUCTION = ROOT / "TASK.md"

csv.field_size_limit(sys.maxsize)


def table(task: dict) -> Path:
    base = SOURCES[task["source"]] / task["id"]
    return base / ("data.csv" if task["source"] == "mock" else task["table"])


def copy_table(src: Path, dst: Path) -> tuple[int, list[str]]:
    """Copy as utf-8 csv; return the row count and header."""
    delimiter = "\t" if src.suffix.lower() == ".tsv" else ","
    with src.open(encoding="utf-8-sig", errors="replace", newline="") as f, dst.open("w", encoding="utf-8", newline="") as g:
        reader, writer = csv.reader(f, delimiter=delimiter), csv.writer(g)
        header = next(reader)
        writer.writerow(header)
        rows = 0
        for row in reader:
            writer.writerow(row)
            rows += 1
    return rows, header


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    args = ap.parse_args()

    instruction = INSTRUCTION.read_text(encoding="utf-8")
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    shutil.rmtree(args.out / "tasks", ignore_errors=True)
    shutil.rmtree(args.out / "answers", ignore_errors=True)
    lines = []
    for t in tasks:
        folder = args.out / "tasks" / t["id"]
        folder.mkdir(parents=True)
        rows, header = copy_table(table(t), folder / "data.csv")
        (folder / "task.json").write_text(json.dumps({"id": t["id"], "title": t["title"], "instruction": instruction},
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
        if t["source"] == "mock":
            answers = args.out / "answers" / t["id"]
            answers.mkdir(parents=True)
            shutil.copy2(SOURCES["mock"] / t["id"] / "findings.json", answers / "findings.json")
        size = (folder / "data.csv").stat().st_size
        lines.append({"id": t["id"], "source": t["source"], "title": t["title"], "rows": rows, "columns": len(header), "bytes": size})
        print(f"{t['id']:24} {t['source']:11} {rows:>8} rows {len(header):>3} cols {size / 1e6:7.2f} MB", flush=True)
    (args.out / "tasks.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in lines), encoding="utf-8")
    print(f"{len(lines)} tasks in {args.out}", flush=True)


if __name__ == "__main__":
    main()
