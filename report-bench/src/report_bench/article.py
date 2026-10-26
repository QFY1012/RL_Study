"""Rubric items 2.2 and 2.3, read from the page's prose alone: is the argument followed, is there a story?

    PYTHONPATH=../report-gepa/src:src ../report-gepa/.venv/bin/python -m report_bench.article <evidence_dir>... [--out runs/article] [--model m]

The prose is the text capture.py read from the DOM: the visible headings,
paragraphs, list items and quotes, without the text inside svg charts. Captions
and method notes stay in; the prompts tell the model to skip them, since pages
mark them up in no common way. Both items are judged from words: what makes a
page argue or tell a story is in its sentences, and the screenshots would only
let the model fill in what the text does not say.

- 2.2 argument: one call splits the prose into sections and quotes, for each,
  the earlier sentence it serves (a point it is evidence for, a question it
  answers). The code then looks the quote up: it counts only if it is in the
  prose and starts before the section does, so the model cannot supply a link
  the page never wrote. Sections before the first one that serves anything are
  the opening and are not counted. The score is the share of counted sections
  that serve an earlier sentence.
- 2.3 narrative: one call with the item's five bands, like judge.py's items,
  but every part of the story it credits (an individual who wants something,
  an expectation broken, what happened after) has to be quoted.

Every record keeps the model, a hash of the prompt and the rubric, and the
capture version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .llm import LLM, OutOfCredit
from .rubric import load, rubric_hash

MODEL = "deepseek-v4.1-flash"
MAX_TOKENS = 32768
MAX_PROSE = 16000  # characters
PROSE_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "dd"}
QUOTE_CHARS = 40  # a quote is looked up by its first this many normalised characters

INTRO = "下面是一篇数据报道的正文(从网页上读出来的文字;图下面的说明、图表里的零碎标签、方法说明、来源、致谢也混在里面，不算正文，跳过它们)。"

ARGUMENT = INTRO + """只判一件事：{id} {name}。不评文笔，有没有讲故事也不看。

{description}

按顺序把正文分成若干节，每节是讲一件事的一段内容(按内容分，不按小标题分)。每节写:
- start:这一节的第一句，原文照抄。
- serves:这一节在为前面哪句话服务，原文照抄那句话。可以是这一节之前写出来的一个观点(一个判断，不是话题或数字),这一节是它的证据;可以是这一节之前提出的一个问题，这一节在回答它;结尾的总结，引出它所总结的那个前面的观点。那句话要在这一节之前出现，在这一节里或之后才写出来的不算。这一节跟前面的观点和问题都不沾边，读者不知道它为什么在这里，就写 null。开头还没有任何观点或问题的几节，也写 null。
- how:这一节怎么证明那个观点、怎么回答那个问题，一句话;serves 是 null 的，写这一节讲了什么。

只看文章写出来的，不要替文章补上它没写的观点或问题。

只输出 JSON:{{"sections": [{{"start": "...", "serves": "... 或 null", "how": "..."}}]}}

正文:
{prose}
"""

NARRATIVE = INTRO + """只判一件事：{id} {name}。

{description}

先逐个列出文章里的具体个体，每个引出三样东西的原文，引不出的写 null;再按下面的分段定区间，在区间内连续取值。
{bands}

只输出 JSON:{{"individuals": [{{"who": "...", "wants": "引原文，或 null", "expected": "被打破的常规：默认的看法或预期，引原文，或 null", "broken": "事情不是那样，引原文，或 null", "after": "怎么应对、后来怎样，引原文，或 null", "tie": "和数据怎么接上，或没接上"}}], "score": 0 到 1 的小数, "reason": "扣分的理由;满分就说做到了什么"}}

正文:
{prose}
"""


def prompt_hash(template: str) -> str:
    return hashlib.sha256(template.encode()).hexdigest()[:12] + "-" + rubric_hash()


def prose(ev: dict) -> str:
    """The page's visible prose in page order, each piece once."""
    seen, keep = set(), []
    for t in ev["text"]:
        if t["hidden"] or t["in_svg"] or t["tag"] not in PROSE_TAGS or t["text"] in seen:
            continue
        seen.add(t["text"])
        keep.append(t["text"])
    return "\n".join(keep)[:MAX_PROSE]


def _norm(s: str | None) -> str:
    return re.sub(r"\W+", " ", s or "").strip().lower()


def _at(text: str, quote: str | None) -> int:
    """Where the quote starts in the normalised text, -1 if it is not there."""
    q = _norm(quote)[:QUOTE_CHARS]
    return text.find(q) if q else -1


def _json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def _ask(model: str, prompt: str) -> tuple[dict | None, dict]:
    r = LLM(model).chat([{"role": "user", "content": prompt}], max_tokens=MAX_TOKENS)
    return _json(r.text), {"text": r.text, "finish": r.finish_reason, "prompt_tokens": r.prompt_tokens,
                           "completion_tokens": r.completion_tokens, "seconds": r.seconds}


def argument(ev: dict, model: str = MODEL) -> dict:
    """2.2: the share of sections that serve a sentence written before them."""
    item = load()["2.2"]
    text = prose(ev)
    parsed, answer = _ask(model, ARGUMENT.format(id=item.id, name=item.name, description=item.description, prose=text))
    sections = (parsed or {}).get("sections")
    if not isinstance(sections, list) or not sections:
        return {"score": None, "where": None, "reason": None, "sections": None, "answer": answer}
    norm = _norm(text)
    for s in sections:
        start, served = _at(norm, s.get("start")), _at(norm, s.get("serves") if s.get("serves") != "null" else None)
        s["holds"] = 0 <= served < start
    first = next((i for i, s in enumerate(sections) if s["holds"]), len(sections))
    judged = sections[first:]
    off = [s for s in judged if not s["holds"]]
    score = (len(judged) - len(off)) / len(judged) if judged else 0.0
    where = ";".join(f"「{(s.get('start') or '')[:60]}」" for s in off) or None
    reason = (f"{len(judged)} 节里 {len(off)} 节不为前面的观点或问题服务:" + ";".join(s.get("how") or "" for s in off)
              if off else f"{len(judged)} 节都在为前面写出的观点或问题服务")
    if not judged:
        reason = "没有一节在为前面写出的观点或问题服务"
    return {"score": round(score, 3), "where": where, "reason": reason, "opening": first, "sections": sections, "answer": answer}


def narrative(ev: dict, model: str = MODEL) -> dict:
    """2.3: scored on the five bands, every credited part of the story quoted."""
    item = load()["2.3"]
    parsed, answer = _ask(model, NARRATIVE.format(id=item.id, name=item.name, description=item.description,
                                                  bands="\n".join(f"- {b}" for b in item.bands), prose=prose(ev)))
    v = parsed or {}
    value = v.get("score")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        value = None  # an answer without a usable score is a failed judgement, not a 0
    who = [i.get("who") for i in v.get("individuals") or [] if isinstance(i, dict)]
    return {"score": value, "where": "、".join(map(str, who)) or None, "reason": v.get("reason"),
            "individuals": v.get("individuals"), "answer": answer}


JUDGES = {"2.2": (argument, ARGUMENT), "2.3": (narrative, NARRATIVE)}


def judge(item_id: str, ev_dir: Path, model: str = MODEL) -> dict:
    """One item's record for the page captured in ev_dir."""
    fn, template = JUDGES[item_id]
    ev = json.loads((ev_dir / "evidence.json").read_text(encoding="utf-8"))
    return {"item": item_id, "page": str(ev_dir), "model": model, "prompt_hash": prompt_hash(template),
            "capture_version": ev["capture_version"], **fn(ev, model)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", type=Path, nargs="+", help="evidence directories written by capture.py")
    ap.add_argument("--items", default="2.2,2.3")
    ap.add_argument("--out", type=Path, default=Path("runs/article"))
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    jobs = [(page, i) for page in args.pages for i in args.items.split(",")]

    def run(job):
        page, item_id = job
        path = args.out / page.parent.name / page.name / f"{item_id}.json"
        if path.exists():
            return path, json.loads(path.read_text(encoding="utf-8"))
        try:
            rec = judge(item_id, page, args.model)
        except OutOfCredit:
            raise
        except Exception as e:  # noqa: BLE001 - a failed call is an infrastructure failure: no record, rerun later
            return path, {"error": str(e)[:300]}
        if rec["score"] is None:
            return path, {"error": "no usable verdict in the answer"}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        return path, rec

    with ThreadPoolExecutor(args.workers) as pool:
        for path, rec in pool.map(run, jobs):
            if "error" in rec:
                print(f"{path}: FAILED {rec['error']}", flush=True)
            else:
                print(f"{path}: score={rec['score']} {rec.get('reason') or ''}"[:300], flush=True)


if __name__ == "__main__":
    main()
