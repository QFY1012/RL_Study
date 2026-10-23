"""Make one report page with a pi agent (agent/gen.mjs), then render it.

    PYTHONPATH=src .venv/bin/python -m report_gepa.generate <out_dir> <data file or dir>... [--guide guides/seed.md] [--model m] [--n 2]

The guide is the agent's system prompt and is the thing GEPA optimizes. The data
files are copied into the agent's workspace and never put in a prompt: the agent
reads them with its tools. Each version lives in <out_dir>/<name>/: index.html,
page.png, record.json (the agent runs and the render) and session.jsonl (the
agent's transcript). The copied data is removed afterwards.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .llm import OutOfCredit, credit_refused, load_env
from .render import render

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "agent" / "gen.mjs"
GUIDES = ROOT / "guides"
GEN_MODEL = "deepseek-v4.1-flash"
MAX_ATTEMPTS = 2
SPACED_TAG = re.compile(r"<\s+/?(?:div|span|p|section|h[1-6]|table|tr|td|th|li|ul|svg|text|a|img|header|footer|main|article)\b", re.I)


def guide_hash(guide: str) -> str:
    return hashlib.sha256(guide.encode()).hexdigest()[:12]


def page_problem(ws: Path) -> str | None:
    page = ws / "index.html"
    if not page.exists():
        return "no index.html"
    html = page.read_text(encoding="utf-8", errors="replace")
    if "</html>" not in html.lower():
        return "html not closed"
    # A deepseek reply once wrote every tag in the body as "< div", which the
    # browser shows as text; it renders "ok" with text on it, so check here.
    if len(SPACED_TAG.findall(html)) >= 5:
        return "tags written as text"
    return None


def run_agent(ws: Path, guide_path: Path, model: str, effort: str, log_prefix: str, task_path: Path | None = None,
              output: str = "index.html") -> dict:
    env = load_env()
    proc = subprocess.Popen(
        ["node", str(AGENT), str(ws), str(guide_path), model, effort, str(task_path) if task_path else "", output],
        env={**os.environ, "LLM_API_KEY": env["LLM_API_KEY"], "LLM_BASE_URL": env["LLM_BASE_URL"]},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    result, tail = None, []
    for line in proc.stdout:
        line = line.rstrip("\n")
        if line.startswith("RESULT "):
            result = json.loads(line[len("RESULT "):])
        else:
            tail = (tail + [line])[-20:]
            print(f"{log_prefix} {line}", flush=True)
    proc.wait()
    if result is None:
        result = {"model": model, "effort": effort, "crashed": proc.returncode, "output_tail": tail}
    return result


def generate_page(guide_path: Path, data: list[Path], out_dir: Path, name: str, model: str = GEN_MODEL,
                  effort: str = "high", render_slots: threading.Semaphore | None = None,
                  task_path: Path | None = None) -> dict:
    """task_path replaces the agent's fixed task message (agent/gen.mjs TASK) when given."""
    ws = out_dir / name
    guide = guide_path.read_text(encoding="utf-8")
    record = {"model": model, "effort": effort, "guide": guide_path.name, "guide_hash": guide_hash(guide),
              "data": [str(p) for p in data], "attempts": []}
    for _ in range(MAX_ATTEMPTS):
        shutil.rmtree(ws, ignore_errors=True)
        (ws / "data").mkdir(parents=True)
        for p in data:
            if p.is_dir():
                shutil.copytree(p, ws / "data" / p.name)
            else:
                shutil.copy2(p, ws / "data" / p.name)
        run = run_agent(ws, guide_path, model, effort, f"  {out_dir.name}/{name}", task_path)
        if credit_refused(run.get("error")):
            # not the page's fault: leave no record, so a later run makes this page again
            shutil.rmtree(ws, ignore_errors=True)
            raise OutOfCredit(run["error"])
        run["problem"] = page_problem(ws)
        record["attempts"].append(run)
        shutil.rmtree(ws / "data")
        if run["problem"] is None:
            break
    last = record["attempts"][-1]
    record["delivered"] = last["problem"] is None
    record["seconds"] = sum(a.get("seconds", 0) for a in record["attempts"])
    record["output_tokens"] = sum(a.get("usage", {}).get("output", 0) for a in record["attempts"])
    if record["delivered"]:
        html = (ws / "index.html").read_text(encoding="utf-8")
        if render_slots is None:
            record["render"] = render(html, ws / "page.png").to_json()
        else:
            with render_slots:
                record["render"] = render(html, ws / "page.png").to_json()
    else:
        record["detail"] = last["problem"]
    (ws / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("data", type=Path, nargs="+", help="files or directories the agent gets under data/")
    ap.add_argument("--guide", type=Path, default=GUIDES / "seed.md")
    ap.add_argument("--model", default=GEN_MODEL)
    ap.add_argument("--n", type=int, default=1)
    args = ap.parse_args()

    with ThreadPoolExecutor(args.n) as pool:
        records = list(pool.map(lambda i: generate_page(args.guide, args.data, args.out, str(i + 1), args.model),
                                range(args.n)))
    for i, r in enumerate(records, 1):
        rend = r.get("render", {})
        tries = "/".join(a["problem"] or "ok" for a in r["attempts"])
        print(f"{i}: delivered={r['delivered']} tries={tries} {r['seconds']}s tokens={r['output_tokens']} "
              f"verdict={rend.get('verdict')} height={rend.get('page_height')} "
              f"page_errors={len(rend.get('page_errors', []))} syntax_errors={len(rend.get('syntax_errors', []))} "
              f"hang={rend.get('hang')}", flush=True)


if __name__ == "__main__":
    main()
