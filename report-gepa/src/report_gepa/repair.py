"""Fix pages whose scripts fail, in place, with a deepseek agent.

    PYTHONPATH=src .venv/bin/python -m report_gepa.repair runs/pudding-pages runs/pages [--workers 4]

A page needs repair when its render recorded page errors or script syntax errors.
The agent works in the page's own directory with the data copied back in; the
task message lists the errors and asks it to fix only what causes them, keeping
the design and the text. The broken page is kept as index.broken.html and
page.broken.png, and record.json gets a "repair" entry (agent run, errors before
and after) while "render" describes the repaired page. A page that still fails
after MAX_ATTEMPTS keeps the last attempt and its errors.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .generate import page_problem, run_agent
from .llm import OutOfCredit, credit_refused
from .render import render

ROOT = Path(__file__).resolve().parents[2]
REPAIR_MODEL = "deepseek-v4.1-flash"
MAX_ATTEMPTS = 2
SYSTEM = "你负责修网页里的脚本错误。只改导致错误的代码，不改页面的设计、排版和文字。\n"
TASK = """工作目录里的 index.html 是用 data/ 里的数据做的报告网页。在浏览器里打开时报了下面的错误:

{errors}

找出原因并修好，让页面里的脚本完整运行、所有图表都画出来。只改出错的地方，不要改页面的设计、文字和结构。
工作环境里没有浏览器;可以把脚本抽出来用 node --check 查语法，或者用 node 跑数据处理的那部分代码。改完就结束。
"""


def errors_of(render_json: dict) -> list[str]:
    return render_json.get("page_errors", []) + render_json.get("syntax_errors", [])


def repair_page(page_dir: Path) -> dict:
    record_path = page_dir / "record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    before = errors_of(record["render"])
    if not (page_dir / "index.broken.html").exists():
        shutil.copy2(page_dir / "index.html", page_dir / "index.broken.html")
        shutil.copy2(page_dir / "page.png", page_dir / "page.broken.png")
    repair = {"model": REPAIR_MODEL, "errors_before": before, "attempts": []}
    with tempfile.TemporaryDirectory() as tmp:
        system = Path(tmp) / "system.md"
        task = Path(tmp) / "task.txt"
        system.write_text(SYSTEM, encoding="utf-8")
        task.write_text(TASK.format(errors="\n".join(f"- {e}" for e in before)), encoding="utf-8")
        for _ in range(MAX_ATTEMPTS):
            shutil.copy2(page_dir / "index.broken.html", page_dir / "index.html")
            (page_dir / "data").mkdir(exist_ok=True)
            for p in map(Path, record["data"]):
                if p.is_dir():
                    shutil.copytree(p, page_dir / "data" / p.name)
                else:
                    shutil.copy2(p, page_dir / "data" / p.name)
            # the agent's transcript goes to repair-session.jsonl; keep the generation one
            session = page_dir / "session.jsonl"
            kept = session.read_bytes() if session.exists() else None
            run = run_agent(page_dir, system, REPAIR_MODEL, "high", f"  repair {page_dir.parent.name}/{page_dir.name}", task)
            if session.exists():
                session.rename(page_dir / "repair-session.jsonl")
            if kept is not None:
                session.write_bytes(kept)
            shutil.rmtree(page_dir / "data", ignore_errors=True)
            if credit_refused(run.get("error")):
                shutil.copy2(page_dir / "index.broken.html", page_dir / "index.html")
                raise OutOfCredit(run["error"])
            run["problem"] = page_problem(page_dir)
            rend = None if run["problem"] else render((page_dir / "index.html").read_text(encoding="utf-8"), page_dir / "page.png").to_json()
            run["errors_after"] = errors_of(rend) if rend else None
            repair["attempts"].append(run)
            if rend and rend["verdict"] == "ok" and not run["errors_after"]:
                break
    if rend is None:  # never produced a usable page: put the broken one back
        shutil.copy2(page_dir / "index.broken.html", page_dir / "index.html")
        shutil.copy2(page_dir / "page.broken.png", page_dir / "page.png")
    else:
        record["render"] = rend
    repair["errors_after"] = errors_of(record["render"])
    record["repair"] = repair
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", type=Path, nargs="+", help="page directories such as runs/pudding-pages")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    todo = []
    for runs in args.runs:
        for record_path in sorted(runs.glob("*/*/record.json")):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record["delivered"] and errors_of(record["render"]) and "repair" not in record:
                todo.append(record_path.parent)
    print(f"{len(todo)} pages to repair", flush=True)

    def one(page_dir: Path):
        try:
            rec = repair_page(page_dir)
            rep = rec["repair"]
            print(f"{page_dir.parent.name}/{page_dir.name}: tries={len(rep['attempts'])} "
                  f"before={rep['errors_before'][0][:60]!r} after={rep['errors_after'][:1]}", flush=True)
        except OutOfCredit as e:
            print(f"{page_dir.parent.name}/{page_dir.name}: OUT OF CREDIT {str(e)[:120]}", flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(one, todo))


if __name__ == "__main__":
    main()
