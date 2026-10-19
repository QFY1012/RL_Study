"""Turn one report's JSON into an HTML page with a given guide, then render it.

    PYTHONPATH=src .venv/bin/python -m report_gepa.generate <report.json> <out_dir> [--guide guide.md] [--n 2]

The guide is the system prompt and is the thing GEPA optimizes; the user message
is the report JSON verbatim. Each version is written to <out_dir>/<n>.html with
its screenshot <n>.png and a <n>.json record of the call and the render.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .llm import LLM
from .render import render

GEN_MODEL = "deepseek-v4.1-flash"
MAX_ATTEMPTS = 3
# glm-5.3-flash stops at 8192 output tokens unless told otherwise; a Pudding-style
# deepseek page took 47k, so ask for more than any page needs.
MAX_TOKENS = 65536
SPACED_TAG = re.compile(r"<\s+/?(?:div|span|p|section|h[1-6]|table|tr|td|th|li|ul|svg|text|a|img|header|footer|main|article)\b", re.I)

SEED_GUIDE = "把用户给的 JSON 数据做成一个网页报告。只回复一个完整的 HTML 文件,放在一个 ```html 代码块里。"


def guide_hash(guide: str) -> str:
    return hashlib.sha256(guide.encode()).hexdigest()[:12]


def extract_html(text: str) -> str | None:
    m = re.search(r"```html\s*\n(.*?)```", text, re.S | re.I)
    if m:
        return m.group(1).strip()
    start = text.lower().find("<!doctype html")
    if start < 0:
        start = text.lower().find("<html")
    return text[start:].strip() if start >= 0 else None


def generate_page(llm: LLM, guide: str, report: dict, out_dir: Path, name: str,
                  render_slots: threading.Semaphore | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {"model": llm.model, "guide_hash": guide_hash(guide), "name": name, "attempts": []}
    messages = [
        {"role": "system", "content": guide},
        {"role": "user", "content": json.dumps(report, ensure_ascii=False, indent=1)},
    ]
    html = None
    for _ in range(MAX_ATTEMPTS):
        reply = llm.chat(messages, max_tokens=MAX_TOKENS)
        html = extract_html(reply.text) if reply.complete else None
        # The relay has returned finish_reason=stop with the text cut mid-stylesheet,
        # so a page counts as delivered only when the document is closed.
        # A deepseek reply once wrote every tag in the body as "< div", which the
        # browser shows as text; it renders "ok" with text on it, so check here.
        problem = ("reply incomplete" if not reply.complete else
                   "no html in reply" if html is None else
                   "html not closed" if "</html>" not in html.lower() else
                   "tags written as text" if len(SPACED_TAG.findall(html)) >= 5 else None)
        record["attempts"].append({"finish_reason": reply.finish_reason, "seconds": reply.seconds,
                                   "completion_tokens": reply.completion_tokens,
                                   "text_chars": len(reply.text), "problem": problem})
        if problem is None:
            break
        html = None
    last = record["attempts"][-1]
    record.update(finish_reason=last["finish_reason"], seconds=sum(a["seconds"] for a in record["attempts"]),
                  prompt_tokens=reply.prompt_tokens, completion_tokens=last["completion_tokens"])
    if html is None:
        record["delivered"] = False
        record["detail"] = last["problem"]
    else:
        record["delivered"] = True
        (out_dir / f"{name}.html").write_text(html, encoding="utf-8")
        if render_slots is None:
            record["render"] = render(html, out_dir / f"{name}.png").to_json()
        else:
            with render_slots:
                record["render"] = render(html, out_dir / f"{name}.png").to_json()
    (out_dir / f"{name}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--guide", type=Path, help="guide file; default is the seed guide")
    ap.add_argument("--n", type=int, default=1)
    args = ap.parse_args()

    guide = args.guide.read_text(encoding="utf-8") if args.guide else SEED_GUIDE
    report = json.loads(args.report.read_text(encoding="utf-8"))
    llm = LLM(model=GEN_MODEL)
    with ThreadPoolExecutor(args.n) as pool:
        records = list(pool.map(lambda i: generate_page(llm, guide, report, args.out, str(i + 1)), range(args.n)))
    for r in records:
        rend = r.get("render", {})
        print(f"{r['name']}: delivered={r['delivered']} finish={r['finish_reason']} {r['seconds']}s "
              f"tokens={r['completion_tokens']} verdict={rend.get('verdict')} height={rend.get('page_height')} "
              f"page_errors={len(rend.get('page_errors', []))} syntax_errors={len(rend.get('syntax_errors', []))} "
              f"hang={rend.get('hang')} {r.get('detail', '')}", flush=True)


if __name__ == "__main__":
    main()
