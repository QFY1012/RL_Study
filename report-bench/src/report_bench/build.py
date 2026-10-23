"""Build the benchmark's task folders from report-gepa's data.

    python3 -m report_bench.build <out>

For every task in tasks.json its tables go to <out>/tasks/<id>/data/ under
their own file names (a tsv becomes a csv, a url-escaped name is unescaped) and
<out>/tasks/<id>/task.json gets the task statement: the fixed instruction
(TASK.md), the task's one-line title and the file names. <out>/tasks.jsonl lists
every task with its source and each table's shape. A mock task's planted findings
go to <out>/answers/<id>/findings.json, which participants do not get.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / "report-gepa" / "data"
SOURCES = {"pudding": DATA / "pudding", "pudding-web": DATA / "pudding-web", "mock": DATA / "mock"}
TASKS = ROOT / "tasks.json"
INSTRUCTION = ROOT / "TASK.md"

csv.field_size_limit(sys.maxsize)


def published_name(table: str) -> str:
    name = unquote(Path(table).name)
    return name[:-4] + ".csv" if name.lower().endswith(".tsv") else name


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
        (folder / "data").mkdir(parents=True)
        names = [published_name(x) for x in t["tables"]]
        if len(set(names)) != len(names):
            raise SystemExit(f"{t['id']}: two tables would get the same file name: {names}")
        shapes = []
        for table, name in zip(t["tables"], names):
            rows, header = copy_table(SOURCES[t["source"]] / t["id"] / table, folder / "data" / name)
            shapes.append({"file": name, "rows": rows, "columns": len(header), "bytes": (folder / "data" / name).stat().st_size})
        (folder / "task.json").write_text(json.dumps({"id": t["id"], "title": t["title"], "files": [f"data/{n}" for n in names],
                                                      "instruction": instruction}, ensure_ascii=False, indent=1), encoding="utf-8")
        if t["source"] == "mock":
            answers = args.out / "answers" / t["id"]
            answers.mkdir(parents=True)
            shutil.copy2(SOURCES["mock"] / t["id"] / "findings.json", answers / "findings.json")
        size = sum(x["bytes"] for x in shapes)
        lines.append({"id": t["id"], "source": t["source"], "title": t["title"], "tables": shapes})
        print(f"{t['id']:24} {t['source']:11} {len(shapes):>2} tables {sum(x['rows'] for x in shapes):>9} rows {size / 1e6:7.2f} MB", flush=True)
    (args.out / "tasks.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in lines), encoding="utf-8")
    print(f"{len(lines)} tasks in {args.out}", flush=True)


if __name__ == "__main__":
    main()
