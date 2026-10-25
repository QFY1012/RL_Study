"""Rubric items 1.1-1.3, trust: does the page run, and are its findings true to the data?

    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_bench.trust <evidence_dir> <facts.json> [--model m]

The page's writer delivers facts.json (facts.py): every finding as a claim and
the pandas code that computes it. The items, in order, each a veto:

- 1.1 renders: the capture opened the page and it showed text; a generated page
  also ran without errors. Published Pudding pages throw errors of their own
  (titletowns: "reading 'latitude'") and still work, so for them only the first
  part applies.
- 1.2 facts run: facts.json loads and every fact's code runs on the data.
- 1.3 claims hold: one model call reads each claim next to its code and what the
  code printed, and says whether they agree.

An item is checked only if the ones before it hold.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from . import facts as F
from .llm import LLM

MODEL = "deepseek-v4.1-flash"
MAX_TOKENS = 32768  # the reasoning counts too

PROMPT = """下面是一份数据报告给出的发现。每条发现有结论(claim),一段在数据上运行的 pandas 代码(code),和这段代码的输出(output)。

逐条判断结论和输出是否一致:
- ok:结论里的数字、比较、多少、趋势都和输出相符。四舍五入造成的出入不算不符。
- wrong:结论和输出矛盾，或者结论说的东西输出里没有，或者结论里的数和名字不是代码从表里算出来的，而是直接写在代码里的(比如代码就是一个写好的字符串、写好数值的 Series)。筛选条件、阈值、改名写在代码里没关系。

每条先在 basis 里写出输出里对应的数，再给 verdict。只输出 JSON:{"facts": [{"id": "...", "basis": "...", "verdict": "ok 或 wrong"}]}

{facts}
"""
PROMPT_HASH = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]


def renders(ev: dict) -> list[str]:
    """1.1: why the page did not open, show text or run cleanly; empty if it did."""
    problems = []
    if ev["verdict"] != "ok":
        problems.append(f"verdict {ev['verdict']}")
    if ev.get("hang"):
        problems.append("hang")
    if not ev["target"].startswith(("http://", "https://")):
        problems += [f"page error: {e}" for e in ev["page_errors"]] + [f"syntax error: {e}" for e in ev["syntax_errors"]]
    return problems


def run_facts(facts_path: Path, data: list[Path]) -> tuple[list[str], list[dict], dict]:
    """1.2: problems, the facts and every fact's output."""
    try:
        facts = F.load(facts_path)
    except F.FactError as e:
        return [str(e)], [], {}
    results = F.run(facts, data)
    problems = [f"fact {i} does not run: {r['error']}" for i, r in results.items() if "error" in r]
    return problems, facts, results


def block(fact: dict, result: dict) -> str:
    tables = ", ".join(f"{name} = {path}" for name, path in fact["tables"].items())
    return f"[{fact['id']}]\nclaim: {fact['claim']}\ntables: {tables}\ncode: {fact['code']}\noutput:\n{result['output']}"


def claims_hold(facts: list[dict], results: dict, model: str) -> dict:
    """1.3: one model call over every claim, its code and its output."""
    prompt = PROMPT.replace("{facts}", "\n\n".join(block(f, results[f["id"]]) for f in facts))
    reply = LLM(model).chat([{"role": "user", "content": prompt}], max_tokens=MAX_TOKENS)
    m = re.search(r"\{.*\}", reply.text, re.S)
    try:
        verdicts = json.loads(m.group(0))["facts"]
        wrong = [v for v in verdicts if v["verdict"] != "ok"]
    except (AttributeError, json.JSONDecodeError, KeyError, TypeError):
        verdicts = wrong = None  # no usable answer is a failed check, not a pass
    return {"verdicts": verdicts, "wrong": wrong, "prompt": prompt, "reply": reply.text,
            "usage": {"prompt_tokens": reply.prompt_tokens, "completion_tokens": reply.completion_tokens, "seconds": reply.seconds}}


def trust(ev_dir: Path, facts_path: Path, model: str = MODEL) -> dict:
    """The three items for one captured page. `violated` is None for 1.3 when the model gave no usable answer."""
    ev = json.loads((ev_dir / "evidence.json").read_text(encoding="utf-8"))
    record = {"page": ev["target"], "facts": str(facts_path), "model": model, "prompt_hash": PROMPT_HASH, "items": {}}
    problems = renders(ev)
    record["items"]["1.1"] = {"violated": bool(problems), "problems": problems}
    if not problems:
        problems, facts, results = run_facts(facts_path, [Path(p) for p in ev["data"]])
        record["items"]["1.2"] = {"violated": bool(problems), "problems": problems}
        if not problems:
            check = claims_hold(facts, results, model)
            record["items"]["1.3"] = {"violated": None if check["wrong"] is None else bool(check["wrong"]), **check}
    record["vetoed"] = [k for k, v in record["items"].items() if v["violated"]]
    return record


def feedback(record: dict) -> list[str]:
    """One line per problem, in the rubric's words."""
    names = {"1.1": "页面可渲染", "1.2": "fact 能执行", "1.3": "结论和数据一致"}
    lines = [f"{k} {names[k]}:{p}" for k, v in record["items"].items() for p in v.get("problems", [])]
    check = record["items"].get("1.3")
    if check and check["wrong"] is None:
        lines.append("1.3 结论和数据一致:核对没有给出可用的结果")
    for v in (check or {}).get("wrong") or []:
        lines.append(f"1.3 结论和数据一致:[{v.get('id')}] {v.get('basis', '')}")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("evidence", type=Path)
    ap.add_argument("facts", type=Path)
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()
    r = trust(args.evidence, args.facts, args.model)
    print(f"vetoed={','.join(r['vetoed']) or '-'}")
    for line in feedback(r):
        print("  " + line)
    if "1.3" in r["items"]:
        print(f"  usage {r['items']['1.3']['usage']}")


if __name__ == "__main__":
    main()
