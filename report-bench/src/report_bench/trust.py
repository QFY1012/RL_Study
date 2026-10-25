"""Rubric items 1.1-1.3, trust: does the page run, and is what it says about the data true?

    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_bench.trust <evidence_dir> <facts.json> [--model m]

The page's writer delivers facts.json (facts.py): the findings and how each was
computed. The page marks the sentences that state a fact with data-ref, and
the capture (capture.py) records the marks with the page text. The
items, in order, each a veto:

- 1.1 renders: the capture opened the page and it showed text; a generated page
  also ran without errors. Published Pudding pages throw errors of their own
  (titletowns: "reading 'latitude'") and still work, so for them only the first
  part applies.
- 1.2 refs hold: facts.json loads, every id the page names is a fact in it,
  and every fact the page names runs on the data. Code decides this: it is what
  1.3 checks against, and a fact that does not run cannot back anything.
- 1.3 data accurate: one model call. Code runs the facts and does the
  arithmetic (facts.context); the model reads the page text with its marks and
  the results, and lists every statement about the data that contradicts them or
  that nothing in them supports.

An item is checked only if the ones before it hold. The record keeps every
problem and violation with its reason, which is the feedback for the page writer.
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
MAX_TOKENS = 32768  # the reasoning counts too; the endpoint's default 8192 cut every long page off
# The arithmetic is done in code, so the call only reads and compares, and it writes the numbers each
# verdict rests on before the verdict. With reasoning on, deepseek spent 16k tokens (80 s) a page thinking
# for an answer of a few hundred. The relay passes one of the two switches to some backends and the other to others.
NO_REASONING = {"reasoning_effort": "none", "extra_body": {"thinking": {"type": "disabled"}}}

PROMPT = """你核对一个数据报告网页上关于数据的说法是否和数据一致。数据已经由程序算好(见「结果」),你只拿这些结果核对，不要自己估算。

「网页文字」是页面正文，按从上到下的顺序。⟦id⟧……⟦/⟧ 包着的句子，页面声明它依据结果里编号为 id 的那一条。

逐句检查页面上关于这份数据的说法:数字、比较、最多最少、「只有」「每个」、几倍、占比、趋势。没有标记的句子也要查。背景、历史、引语、方法说明、教读者操作的话不是关于这份数据的说法，不查。

犯规有两种:
- contradicts:和结果矛盾。方向反了;「只有」「每个」「最高」这类说法在结果里不成立;写出的精确数字和结果的差，超过它显示的最后一位的一个单位(写 62% 而结果是 0.625 算对上，结果是 0.64 就对不上;结果里算好的占比、差值、倍数、百分比差都可以拿来对);带 about、nearly、roughly、almost、around 的数和结果差超过 10%;more than、less than 这类不等式不成立。
- unsupported:说的是这份数据，但结果里没有能核对它的东西。标了 id 的句子只用那个 id 的结果核对;没标的句子用全部结果核对。

不算犯规:四舍五入造成的出入;单位写法不同;只举了几个例子、没说只有这些。

页面上每一条关于这份数据的说法输出一条核对，按页面顺序：先在 basis 里写出结果里用来核对它的数，再给 verdict:ok、contradicts、unsupported;表头、标签、名称这类不是关于这份数据的说法写 n/a。只输出 JSON:{"checks": [{"text": "页面原句", "ref": "依据的 id,没有就写 null", "basis": "结果里对应的数，和它们说明了什么", "verdict": "ok"}]}。

结果
{results}

网页文字
{text}
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


def refs(ev: dict, facts_path: Path) -> tuple[list[str], dict, dict]:
    """1.2: problems, the facts by id and the results of the facts the page names."""
    try:
        facts = {f["id"]: f for f in F.load(facts_path)}
    except F.FactError as e:
        return [str(e)], {}, {}
    files = F.tables([Path(p) for p in ev["data"]])
    named = list(dict.fromkeys(i for r in ev.get("refs", []) for i in r["ids"]))
    problems = [f"data-ref names {i}, which facts.json does not have" for i in named if i not in facts]
    results = {}
    for i in named:
        if i in facts:
            try:
                results[i] = F.run(files, facts[i])
            except F.FactError as e:
                problems.append(f"fact {i} does not run: {e}")
    return problems, facts, results


def page_text(ev: dict) -> str:
    """The visible prose in page order, with the fact marks; text drawn inside svg is not prose."""
    return "\n".join(t.get("marked", t["text"]) for t in ev.get("text", []) if not t["hidden"] and not t["in_svg"])


def said(text: str, fact_id: str) -> str:
    """What the page's marked sentences say about one fact."""
    return " ".join(m.group(2) for m in re.finditer(r"⟦([^⟧]*)⟧(.*?)⟦/⟧", text) if fact_id in m.group(1).split())


def accuracy(ev: dict, facts: dict, results: dict, model: str) -> dict:
    """1.3: one model call over the page text and the results of the facts it names."""
    text = page_text(ev)
    blocks = "\n\n".join(F.context(facts[i], r, said(text, i)) for i, r in results.items()) or "(页面没有标出任何 fact)"
    prompt = PROMPT.replace("{results}", blocks).replace("{text}", text)
    reply = LLM(model).chat([{"role": "user", "content": prompt}], max_tokens=MAX_TOKENS, temperature=0, **NO_REASONING)
    m = re.search(r"\{.*\}", reply.text, re.S)
    try:
        checks = json.loads(m.group(0))["checks"] if m else None
        violations = [c for c in checks if c["verdict"] in ("contradicts", "unsupported")] if checks is not None else None
    except (json.JSONDecodeError, KeyError, TypeError):
        checks = violations = None  # no usable answer is a failed check, not a pass
    return {"violations": violations, "checks": checks, "prompt": prompt, "reply": reply.text,
            "usage": {"prompt_tokens": reply.prompt_tokens, "completion_tokens": reply.completion_tokens, "seconds": reply.seconds}}


def trust(ev_dir: Path, facts_path: Path, model: str = MODEL) -> dict:
    """The three items on one captured page. `violated` is True or False per item
    checked, None for 1.3 when the model gave no usable answer."""
    ev = json.loads((ev_dir / "evidence.json").read_text(encoding="utf-8"))
    record = {"page": ev["target"], "facts": str(facts_path), "model": model, "prompt_hash": PROMPT_HASH,
              "capture_version": ev["capture_version"], "items": {}}
    problems = renders(ev)
    record["items"]["1.1"] = {"violated": bool(problems), "problems": problems}
    if not problems:
        problems, facts, results = refs(ev, facts_path)
        record["items"]["1.2"] = {"violated": bool(problems), "problems": problems, "named": list(results)}
        if not problems:
            acc = accuracy(ev, facts, results, model)
            record["items"]["1.3"] = {"violated": None if acc["violations"] is None else bool(acc["violations"]), **acc}
    record["vetoed"] = [k for k, v in record["items"].items() if v["violated"]]
    return record


def feedback(record: dict) -> list[str]:
    """One line per problem or violation, in the rubric's words."""
    names = {"1.1": "页面可渲染", "1.2": "引用完整", "1.3": "数据准确"}
    lines = [f"{k} {names[k]}:{p}" for k, v in record["items"].items() for p in v.get("problems", [])]
    for x in record["items"].get("1.3", {}).get("violations") or []:
        lines.append(f"1.3 {names['1.3']}:{x.get('verdict')} [{x.get('ref')}]「{x.get('text', '')}」{x.get('basis', '')}")
    if record["items"].get("1.3", {}).get("violated") is None and "1.3" in record["items"]:
        lines.append("1.3 数据准确:核对没有给出可用的结果")
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
    if "usage" in r["items"].get("1.3", {}):
        print(f"  usage {r['items']['1.3']['usage']}")


if __name__ == "__main__":
    main()
