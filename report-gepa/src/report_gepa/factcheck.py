"""Rubric item 1.2: check every number and claim on a page against the data, with a pi agent.

    PYTHONPATH=src .venv/bin/python -m report_gepa.factcheck <evidence_dir> <out_dir>

A model reading screenshots cannot tell that "twice as many" is really 30% more;
that needs the data and arithmetic. The agent works like the page writer: the
data is copied into data/, the page text (from the capture, in page order, chart
labels included) is in page.txt, and bash runs python in the sandbox. It lists
the numbers and the quantitative claims the page makes (most, twice, rose,
share...), recomputes each from the data, and writes verdict.json.

Only a claim the data contradicts is a violation. A claim the data cannot
settle (published Pudding stories often cite figures that are not in the files
they released) is recorded as unverifiable and does not count.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from .generate import CREDIT_REFUSED, OutOfCredit, run_agent

FACT_MODEL = "glm-5.3-flash"
SYSTEM = "你负责核对数据报告网页上写的内容是否和数据一致。你只核对，不评价设计和写法。\n"
TASK = """工作目录里:
- data/ 是做这个网页用的数据(有 README 的话是数据说明)。
- page.txt 是网页上的全部文字，按页面从上到下的顺序，包括图里的标签和数字。

任务:
1. 从 page.txt 里找出页面写的每个数字(总数、平均、比例、排名、年份对应的值……)和每个带量的说法(最高、最多、几倍、增长、下降、超过一半……)。图里的坐标轴刻度不用核对。
2. 用 python 读 data/ 里的数据，逐条复算或查证。
3. 每条的结论只能是三种之一:
   - ok:和数据一致(四舍五入、单位换算后的出入算一致);
   - wrong:和数据矛盾，或者算出来明显不同;
   - unverifiable:数据里没有能核对它的信息。
4. 把结果写到工作目录的 verdict.json,格式:
{"claims": [{"text": "页面原文", "result": "ok|wrong|unverifiable", "detail": "你怎么算的、算出来是多少"}], "summary": "一两句话"}

工作环境里没有浏览器，也没有网络。写完 verdict.json 就结束。
"""


def page_text(ev: dict) -> str:
    return "\n".join(t["text"] for t in ev["text"])


def factcheck(ev_dir: Path, data: list[Path], out_dir: Path, model: str = FACT_MODEL) -> dict:
    ev = json.loads((ev_dir / "evidence.json").read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out_dir.parent) as tmp:
        ws = Path(tmp) / "ws"
        (ws / "data").mkdir(parents=True)
        for p in data:
            if p.is_dir():
                shutil.copytree(p, ws / "data" / p.name)
            else:
                shutil.copy2(p, ws / "data" / p.name)
        (ws / "page.txt").write_text(page_text(ev), encoding="utf-8")
        system, task = Path(tmp) / "system.md", Path(tmp) / "task.txt"
        system.write_text(SYSTEM, encoding="utf-8")
        task.write_text(TASK, encoding="utf-8")
        run = run_agent(ws, system, model, "high", f"  factcheck {ev_dir.parent.name}/{ev_dir.name}", task, "verdict.json")
        if CREDIT_REFUSED in (run.get("error") or ""):
            raise OutOfCredit(run["error"])
        verdict = None
        if (ws / "verdict.json").exists():
            try:
                verdict = json.loads((ws / "verdict.json").read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                verdict = None
        if (ws / "session.jsonl").exists():
            shutil.copy2(ws / "session.jsonl", out_dir / "factcheck-session.jsonl")
    claims = (verdict or {}).get("claims", [])
    wrong = [c for c in claims if c.get("result") == "wrong"]
    return {"item": "1.2", "page": str(ev_dir), "model": model, "data": [str(p) for p in data],
            "capture_version": ev["capture_version"], "delivered": verdict is not None,
            "violated": bool(wrong) if verdict is not None else None,
            "counts": {r: sum(c.get("result") == r for c in claims) for r in ("ok", "wrong", "unverifiable")},
            "wrong": wrong, "summary": (verdict or {}).get("summary"), "claims": claims, "agent": run}


if __name__ == "__main__":
    ev_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    ev = json.loads((ev_dir / "evidence.json").read_text(encoding="utf-8"))
    rec = factcheck(ev_dir, [Path(p) for p in ev["data"]], out_dir)
    print(json.dumps({k: rec[k] for k in ("violated", "counts", "wrong", "summary")}, ensure_ascii=False, indent=1))
