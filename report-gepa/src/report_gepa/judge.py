"""Judge captured pages against the rubric, one item per call.

    PYTHONPATH=src .venv/bin/python -m report_gepa.judge page <evidence_dir>... --items 1.1,1.3,2.1,2.4 [--out runs/judge]
    PYTHONPATH=src .venv/bin/python -m report_gepa.judge compare <story_dir>... --pairs original~pudding-ds-1 --items 3.1,3.2 [--out runs/judge]

An evidence directory is what capture.py writes. The judge gets the scroll
frames, the thumbnail, the page text in page order and the scroll story (which
charts stay pinned while the page scrolls and how many states they show), and
judges exactly one rubric item, so that items do not lean on each other and
their coupling can be measured.

The rubric says how each item is judged:
- gate (1.1) is decided from the capture, not by a model. It applies to
  generated pages only: published Pudding pages throw errors of their own
  (titletowns: "reading 'latitude'") and still work.
- trust and expression items (1.2-1.3, 2.x) are scored 0-1 on one page, the
  way MiMo's query judge scores (recipes/design, prompts/query_fit.md): pick the
  band first, then a value inside it; the reason for every point taken off is
  GEPA's feedback text. 1.2 is checked against the data by an agent
  (factcheck.py), not from screenshots.
- aesthetic items (3.x) are compared on two pages built from the same data,
  asked in both orders; if the two orders disagree the result is a tie and the
  disagreement is kept.

Every record keeps the judge model, a hash of the prompt and the rubric, and the
capture version, so scores made under different settings are never mixed.
Records go to <out>/page/<dataset>/<version>/<item>.json and
<out>/compare/<dataset>/<a>~<b>/<item>.json; existing records are skipped.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

from PIL import Image

from .capture import VIEW_H
from .factcheck import factcheck
from .generate import OutOfCredit
from .llm import LLM
from .rubric import Item, load, rubric_hash

JUDGE_MODEL = "glm-5.3-flash"
FRAME_W = 1080  # frames are sent at this width; 1440 cost glm 1.7k tokens a frame
MAX_FRAMES = 40  # per page in one call; longer pages are sampled evenly
MAX_TEXT = 15000  # characters of page text per page
MAX_TOKENS = 32768

SYSTEM = """你是数据报告网页的评审。读者是普通大众，不是设计师。

每个页面给你四样证据:
1. 滚动截图：像真人一样从上往下滚动页面，每隔一段截一屏(1440×900)。滚动触发的动画会在相邻几帧里体现出来。
2. 缩略整页图：整个页面缩小后的样子，用来看全篇。
3. 页面文字：从网页源码里按页面顺序抽出来的文字，每段前面标了它出现在第几帧。截图上的小字看不清时以这里为准。
4. 滚动记录：程序在滚动时记下的事实，哪些图在页面滚动时固定在屏幕上不动、各自变了几种状态。图变了几种状态以这里为准。

规则:
- 只判给你的这一条，不评别的方面。
- 照片、手绘插画、音频、梗图这类数据里没有的外部素材不算优点也不算缺点;品牌、logo、署名不看。
- 内容多、篇幅长不是优点。
- 先在证据里找到具体位置(第几帧、哪一节、哪张图)，再下结论。"""

SCORE = """要打分的一条:{id} {name}
说明:{description}

按这一条给这个页面打一个 0 到 1 的连续分数。先确定区间，再按问题的多少和轻重在区间内取值，不要只输出端点:
- [0.0, 0.2):基本没做到
- [0.2, 0.4):只做到一点表面，大部分没做到
- [0.4, 0.6):做到了主要方向，但有几处明显没做到
- [0.6, 0.8):基本做到，只有少量次要问题
- [0.8, 1.0]:完整做到
最后单独输出一行 JSON:{{"score": 0 到 1 的小数, "where": "第几帧/哪一节/哪张图", "reason": "扣分的理由;满分就说做到了什么"}}"""

COMPARE = """要比的一条:{id} {name}
说明:{description}

页面 A 和页面 B 用的是同一份数据。只就这一条比较哪个页面做得更好;差别不明显就判 tie。
最后单独输出一行 JSON:{{"winner": "A" 或 "B" 或 "tie", "reason": "一两句话，说出两边各自的具体位置"}}"""


def prompt_hash() -> str:
    return hashlib.sha256((SYSTEM + SCORE + COMPARE).encode()).hexdigest()[:12] + "-" + rubric_hash()


def _image(path: Path, width: int | None) -> dict:
    img = Image.open(path).convert("RGB")
    if width and img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, "JPEG", quality=80)
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}


def _frame_of(y: int, frames: list[dict]) -> int:
    best = 0
    for i, f in enumerate(frames):
        if f["scroll_y"] <= y:
            best = i
    return best


def _story(ev: dict) -> str:
    lines = []
    for c in ev.get("scroll_story", []):
        if not c["pinned"] and c["states"] < 2:
            continue
        pinned = "、".join(f"第 {a}–{b} 帧" for a, b in c["pinned"])
        lines.append(f"- 图 {c['chart']}({c['kind']},{c['size'][0]}×{c['size'][1]}):第 {c['frames'][0]}–{c['frames'][1]} 帧在屏幕上;"
                     + (f"{pinned}固定在屏幕上不动(页面在滚);" if pinned else "随页面滚走，没有固定;")
                     + f"共出现 {c['states']} 种状态")
    return "\n".join(lines) or "没有图在滚动时固定在屏幕上，也没有图随滚动改变。"


def evidence_parts(ev_dir: Path, label: str) -> list[dict]:
    ev = json.loads((ev_dir / "evidence.json").read_text(encoding="utf-8"))
    frames = ev["frames"]
    keep = list(range(len(frames)))
    if len(keep) > MAX_FRAMES:
        keep = sorted({round(i * (len(frames) - 1) / (MAX_FRAMES - 1)) for i in range(MAX_FRAMES)})
    text_lines, used = [], 0
    for t in ev["text"]:
        line = f"[第 {_frame_of(t['y'], frames)} 帧]{'(隐藏)' if t['hidden'] else ''}{'(图内)' if t['in_svg'] else ''} {t['text']}"
        if used + len(line) > MAX_TEXT:
            text_lines.append("……(后面的文字省略)")
            break
        text_lines.append(line)
        used += len(line)
    parts = [{"type": "text", "text": f"===== 页面 {label} =====\n页面高 {ev['page_height']}px,截了 {len(frames)} 帧"
                                       + (f",这里给其中均匀抽取的 {len(keep)} 帧" if len(keep) < len(frames) else "")
                                       + f"。\n\n滚动记录:\n{_story(ev)}\n\n页面文字:\n" + "\n".join(text_lines)},
             {"type": "text", "text": f"页面 {label} 的缩略整页图:"}, _image(ev_dir / ev["thumb"], None)]
    for i in keep:
        f = frames[i]
        parts.append({"type": "text", "text": f"页面 {label} 第 {i} 帧(页面 y={f['scroll_y']}–{f['scroll_y'] + VIEW_H}):"})
        parts.append(_image(ev_dir / f["file"], FRAME_W))
    return parts


def _verdict(text: str) -> dict | None:
    for m in reversed(list(re.finditer(r"\{[^{}]*\}", text))):
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
    return None


def _ask(model: str, content: list[dict]) -> dict:
    r = LLM(model).chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}], max_tokens=MAX_TOKENS)
    return {"verdict": _verdict(r.text), "text": r.text, "reasoning_chars": len(r.reasoning), "finish": r.finish_reason,
            "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens, "seconds": r.seconds}


def _capture_version(ev_dir: Path) -> str:
    return json.loads((ev_dir / "evidence.json").read_text(encoding="utf-8"))["capture_version"]


def gate(ev_dir: Path) -> dict:
    """1.1: the page opened, rendered text, and (for generated pages) ran without errors."""
    ev = json.loads((ev_dir / "evidence.json").read_text(encoding="utf-8"))
    generated = not ev["target"].startswith(("http://", "https://"))
    problems = []
    if ev["verdict"] != "ok":
        problems.append(f"verdict {ev['verdict']}")
    if ev.get("hang"):
        problems.append("hang")
    if generated:
        problems += [f"page error: {e}" for e in ev["page_errors"]] + [f"syntax error: {e}" for e in ev["syntax_errors"]]
    return {"item": "1.1", "score": 0.0 if problems else 1.0, "problems": problems, "generated": generated,
            "capture_version": ev["capture_version"]}


def score(item: Item, ev_dir: Path, model: str = JUDGE_MODEL) -> dict:
    content = evidence_parts(ev_dir, "") + [{"type": "text", "text": SCORE.format(**item.__dict__)}]
    answer = _ask(model, content)
    v = answer["verdict"] or {}
    value = v.get("score")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        value = None  # an answer without a usable score is a failed judgement, not a 0
    return {"item": item.id, "page": str(ev_dir), "model": model, "prompt_hash": prompt_hash(),
            "capture_version": _capture_version(ev_dir), "score": value, "where": v.get("where"),
            "reason": v.get("reason"), "answer": answer}


def judge_page(item: Item, ev_dir: Path, model: str, record_dir: Path) -> dict:
    if item.gate:
        return gate(ev_dir)
    if item.id == "1.2":  # needs the data and arithmetic, not screenshots
        ev = json.loads((ev_dir / "evidence.json").read_text(encoding="utf-8"))
        return factcheck(ev_dir, [Path(p) for p in ev["data"]], record_dir)
    if item.scored:
        return score(item, ev_dir, model)
    raise ValueError(f"{item.id} is judged by comparing two pages, use compare")


def compare(item: Item, ev_a: Path, ev_b: Path, model: str = JUDGE_MODEL) -> dict:
    """Ask with a first and with b first; the winner is reported as "a", "b" or "tie"."""
    runs = []
    for first, second in ((ev_a, ev_b), (ev_b, ev_a)):
        content = (evidence_parts(first, "A") + evidence_parts(second, "B")
                   + [{"type": "text", "text": COMPARE.format(**item.__dict__)}])
        answer = _ask(model, content)
        w = (answer["verdict"] or {}).get("winner")
        named = {"A": "a" if first == ev_a else "b", "B": "b" if first == ev_a else "a", "tie": "tie"}.get(w)
        runs.append({"order": "ab" if first == ev_a else "ba", "winner": named, "answer": answer})
    winners = [r["winner"] for r in runs]
    consistent = winners[0] == winners[1]
    return {"item": item.id, "a": str(ev_a), "b": str(ev_b), "model": model, "prompt_hash": prompt_hash(),
            "capture_version": [_capture_version(ev_a), _capture_version(ev_b)],
            "winner": winners[0] if consistent else "tie", "consistent": consistent, "runs": runs}


def _name(ev_dir: Path) -> tuple[str, str]:
    return ev_dir.parent.name, ev_dir.name


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("page")
    c.add_argument("pages", type=Path, nargs="+")
    k = sub.add_parser("compare")
    k.add_argument("stories", type=Path, nargs="+", help="story directories under the evidence root")
    k.add_argument("--pairs", required=True, help="comma-separated version pairs, e.g. original~pudding-ds-1")
    for p in (c, k):
        p.add_argument("--items", required=True)
        p.add_argument("--out", type=Path, default=Path("runs/judge"))
        p.add_argument("--model", default=JUDGE_MODEL)
        p.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    rubric = load()
    items = [rubric[i] for i in args.items.split(",")]

    jobs = []
    if args.cmd == "page":
        for page in args.pages:
            dataset, version = _name(page)
            for it in items:
                if it.pairwise:
                    raise SystemExit(f"{it.id} is judged by comparing two pages, use compare")
                path = args.out / "page" / dataset / version / f"{it.id}.json"
                jobs.append((path, (lambda it=it, page=page, path=path: judge_page(it, page, args.model, path.parent))))
    else:
        for it in items:
            if not it.pairwise:
                raise SystemExit(f"{it.id} is judged on one page, use page")
        for story in args.stories:
            for pair in args.pairs.split(","):
                va, vb = pair.split("~")
                a, b = story / va, story / vb
                if not (a / "evidence.json").exists() or not (b / "evidence.json").exists():
                    print(f"{story.name} {pair}: not captured, skipped", flush=True)
                    continue
                for it in items:
                    path = args.out / "compare" / story.name / pair / f"{it.id}.json"
                    jobs.append((path, (lambda it=it, a=a, b=b: compare(it, a, b, args.model))))

    def run(job):
        path, fn = job
        if path.exists():
            return path, json.loads(path.read_text(encoding="utf-8"))
        try:
            rec = fn()
        except OutOfCredit:
            raise
        except Exception as e:  # noqa: BLE001 - a failed call is an infrastructure failure: no record, rerun later
            return path, {"error": str(e)[:300]}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        return path, rec

    with ThreadPoolExecutor(args.workers) as pool:
        for path, rec in pool.map(run, jobs):
            if "error" in rec:
                print(f"{path}: FAILED {rec['error']}", flush=True)
            elif "winner" in rec:
                print(f"{path}: winner={rec['winner']} consistent={rec['consistent']} "
                      + " | ".join(f"{r['order']}:{r['winner']}" for r in rec["runs"]), flush=True)
            else:
                print(f"{path}: score={rec['score']} {rec.get('where') or ''} {rec.get('reason') or rec.get('problems') or rec.get('summary') or ''}", flush=True)


if __name__ == "__main__":
    main()
