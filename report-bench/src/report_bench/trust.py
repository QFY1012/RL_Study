"""Rubric items 1.1-1.3, trust: does the page run, and are its findings true to the data?

    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_bench.trust <evidence_dir> <facts.json> [--model m]

The page's writer delivers facts.json (facts.py): every finding as a claim and
the computation that produces it. The items, in order, each a veto:

- 1.1 renders: the capture opened the page and it showed text; a generated page
  also ran without errors. Published Pudding pages throw errors of their own
  (titletowns: "reading 'latitude'") and still work, so for them only the first
  part applies.
- 1.2 facts run: facts.json loads and every fact's computation runs on the data.
- 1.3 claims hold: code runs every fact; one model call reads each claim next to
  its result tables and says whether they agree.

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

PROMPT = """下面是一份数据报告给出的发现。每条发现有结论(claim),以及程序按它的计算方法从数据算出的结果表。

逐条判断结论和结果表是否一致:
- ok:结论里的数字、比较、多少、趋势都和结果表相符。四舍五入造成的出入不算不符。
- wrong:结论和结果表矛盾，或者结论说的东西结果表里没有。

每条先在 basis 里写出结果表里对应的数，再给 verdict。只输出 JSON:{"facts": [{"id": "...", "basis": "...", "verdict": "ok 或 wrong"}]}

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
    """1.2: problems, the facts and every fact's result tables."""
    try:
        facts = F.load(facts_path)
    except F.FactError as e:
        return [str(e)], [], {}
    files = F.tables(data)
    problems, results = [], {}
    for f in facts:
        try:
            results[f["id"]] = F.run(files, f)
        except F.FactError as e:
            problems.append(f"fact {f['id']} does not run: {e}")
    return problems, facts, results


def block(fact: dict, result: list) -> str:
    parts = [f"[{fact['id']}]", f"claim: {fact['claim']}"]
    for s, table in zip(fact["series"], result):
        how = "; ".join(f"{k}: {s[k]}" for k in ("table", "filter", "group", "measure") if s.get(k))
        parts.append(f"computed: {how}\n{table.to_csv(index=False).strip()}")
    return "\n".join(parts)


def claims_hold(facts: list[dict], results: dict, model: str) -> dict:
    """1.3: one model call over every claim and its result tables."""
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
