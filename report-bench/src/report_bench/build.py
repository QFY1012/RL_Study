"""Build the benchmark's task folders from report-gepa's data.

    python3 -m report_bench.build <out> [--tasks a,b]

For every task in tasks.json its tables go to <out>/tasks/<id>/data/ under
their own file names (a tsv becomes a csv, a url-escaped name is unescaped) and
<out>/tasks/<id>/task.json gets the task statement: the fixed instruction
(TASK.md), the task's one-line title and the file names. <out>/tasks.jsonl lists
every task with its source, each table's shape and, for a Pudding task, the
story page the data comes from. Participants do not get <out>/answers/: a mock
task's planted findings (findings.json), and for a Pudding task the original
story (original.json: url, title, published), the reference for scoring.

--tasks rebuilds only the tasks listed and keeps the rest of <out> as it is (their
lines in tasks.jsonl too), so only those tasks' sources need to be in report-gepa/data.
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
SOURCES = {"pudding": DATA / "pudding", "pudding-web": DATA / "pudding-web", "pudding-repo": DATA / "pudding-repo",
           "pudding-js": DATA / "pudding-js", "pudding-merge": DATA / "pudding-merge", "mock": DATA / "mock"}
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
    ap.add_argument("--tasks", help="comma-separated task ids to rebuild; the others stay as they are")
    args = ap.parse_args()

    instruction = INSTRUCTION.read_text(encoding="utf-8")
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    wanted = set(args.tasks.split(",")) if args.tasks else {t["id"] for t in tasks}
    if unknown := wanted - {t["id"] for t in tasks}:
        raise SystemExit(f"not in tasks.json: {sorted(unknown)}")
    kept = {}
    if args.tasks:
        kept = {r["id"]: r for r in map(json.loads, (args.out / "tasks.jsonl").read_text(encoding="utf-8").splitlines())}
        for i in wanted:
            shutil.rmtree(args.out / "tasks" / i, ignore_errors=True)
            shutil.rmtree(args.out / "answers" / i, ignore_errors=True)
    else:
        shutil.rmtree(args.out / "tasks", ignore_errors=True)
        shutil.rmtree(args.out / "answers", ignore_errors=True)
    used = {t["source"] for t in tasks if t["id"] in wanted} - {"mock"}
    stories = {s: {r["id"]: r for r in map(json.loads, (SOURCES[s] / "manifest.jsonl").read_text(encoding="utf-8").splitlines())}
               for s in used}
    lines = []
    for t in tasks:
        if t["id"] not in wanted:
            lines.append(kept[t["id"]])
            continue
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
        line = {"id": t["id"], "source": t["source"], "title": t["title"], "tables": shapes}
        if t["source"] != "mock":
            story = stories[t["source"]][t["id"]]
            answers = args.out / "answers" / t["id"]
            answers.mkdir(parents=True)
            (answers / "original.json").write_text(json.dumps({k: story[k] for k in ("url", "title", "published")}, ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
            line["original"] = story["url"]
        size = sum(x["bytes"] for x in shapes)
        lines.append(line)
        print(f"{t['id']:24} {t['source']:11} {len(shapes):>2} tables {sum(x['rows'] for x in shapes):>9} rows {size / 1e6:7.2f} MB", flush=True)
    (args.out / "tasks.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in lines), encoding="utf-8")
    print(f"{len(lines)} tasks in {args.out}", flush=True)


if __name__ == "__main__":
    main()
