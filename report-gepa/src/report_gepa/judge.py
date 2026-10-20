"""Judge captured pages against the rubric, one call per group of items.

    PYTHONPATH=src .venv/bin/python -m report_gepa.judge page <evidence_dir>... --items 1.1,1.3,2.2,2.3,3.1,3.2 [--per-item] [--out runs/judge]

An evidence directory is what capture.py writes. The judge gets the scroll
frames, the thumbnail, the page text in page order and the scroll story (which
charts stay pinned while the page scrolls and how many states they show).

The rubric's three dimensions are three groups, each judged in one call, the
way MiMo's evaluation rubric returns its seven dimensions from one vision call
(recipes/design, webdev/eval_rubric.py, "各维独立判断"):
- trust (1.x) is a veto: each item violated or not, where, why; any violation
  makes the page 0, like MiMo's runtime gate. 1.1 is decided from the capture
  and 1.2 by an agent that recomputes the page's claims from the data
  (factcheck.py), so the trust call itself holds the items judged by eye (1.3).
  1.1 applies to generated pages only: published Pudding pages throw errors of
  their own (titletowns: "reading 'latitude'") and still work.
- expression (2.x) is scored 0-1, each item with its own five band
  descriptions: pick the band first, then a value inside it; the reason for
  every point taken off is GEPA's feedback text.
- aesthetics (3.x) is scored 0-1 the same way, after worked examples: for each
  item the judge first sees a few pages that were scored by hand (one frame,
  the score, why; taken from the labelled pages, see the rubric), then the page
  to score. Taste has no fixed scale, and words alone leave each call to guess
  where 0.6 is; the examples pin it. Comparing pages within a group was dropped:
  most rounds said there was no clear difference.

--per-item asks one item per call instead. It is the control for coupling: a
judge that sees a whole group at once may let one impression colour the rest,
which shows up as correlation between items that is not in the pages.

Every record keeps the judge model, a hash of the prompt and the rubric, and the
capture version, so scores made under different settings are never mixed.
Records go to <out>/page/<dataset>/<version>/<item>.json, one per item either
way; a group call also leaves its shared answer in group-<dimension>.json beside
them.
Existing records are skipped.
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
from .llm import LLM, OutOfCredit
from .rubric import Item, load, rubric_hash

EVIDENCE = Path(__file__).resolve().parents[2] / "runs" / "evidence"  # where the worked examples' pages are

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
- 真实照片、音频、梗图这类数据里没有、页面也画不出来的素材不算优点也不算缺点;插画和图标算页面自己画的。品牌、logo、署名不看。
- 内容多、篇幅长不是优点。
- 交互不看：悬停提示、点击、筛选、按钮切换这些要读者操作才出现的东西，不算优点也不算缺点，也不因为某些内容要操作才看得到而扣分;只判滚动时看得到的内容。
- 先在证据里找到具体位置(第几帧、哪一节、哪张图)，再下结论。"""

CHECK = """要判的一条:{id} {name}
说明:{description}

判断这个页面有没有犯这一条。只要有一处犯了就算犯了，写出犯在哪里。
最后单独输出一行 JSON:{{"violated": true 或 false, "where": "第几帧/哪一节/哪张图", "reason": "一两句话"}}"""

SCORE = """要打分的一条:{id} {name}
说明:{description}

按这一条给这个页面打一个 0 到 1 的连续分数。先依据下面的五段说明确定分数所在区间，再根据问题的严重程度、数量和影响在区间内连续取值;不要只输出区间端点或固定档位。临界情况选择和证据最匹配的相邻区间。
{bands}
最后单独输出一行 JSON:{{"score": 0 到 1 的小数, "where": "第几帧/哪一节/哪张图", "reason": "扣分的理由;满分就说做到了什么"}}"""

TOGETHER = """下面这几条一起打分，每条打一个 0 到 1 的连续分数。各条独立判断，不要因为某一条表现好或差而连带改变其它条。
每条先依据它自己的五段说明确定分数所在区间，再根据问题的严重程度、数量和影响在区间内连续取值;不要只输出区间端点或固定档位。有典型案例的条目，先把要评的页面和案例逐个对照，说出它和哪个案例最接近、比它好在哪或差在哪，再定分。

{items}

写完评语后，最后必须单独输出一行 JSON,每条一个键，不能省略:{{{keys}}}"""

CHECK_TOGETHER = """下面这几条一起判，每条判这个页面有没有犯。各条独立判断，不要因为某一条的结论连带改变其它条。只要有一处犯了就算犯了，写出犯在哪里。

{items}

写完评语后，最后必须单独输出一行 JSON,每条一个键，不能省略:{{{keys}}}"""



RUBRIC_HASH = rubric_hash()  # taken with the rubric the run loads, so a mid-run edit cannot relabel its records


def prompt_hash(template: str) -> str:
    """The system prompt and the one template a record was made with, plus the rubric."""
    return hashlib.sha256((SYSTEM + template).encode()).hexdigest()[:12] + "-" + RUBRIC_HASH


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


def evidence_parts(ev_dir: Path, label: str, max_frames: int = MAX_FRAMES) -> list[dict]:
    ev = json.loads((ev_dir / "evidence.json").read_text(encoding="utf-8"))
    frames = ev["frames"]
    keep = list(range(len(frames)))
    if len(keep) > max_frames:
        keep = sorted({round(i * (len(frames) - 1) / (max_frames - 1)) for i in range(max_frames)})
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


FIELDS = {
    "score": r'"score"\s*:\s*(-?[0-9]+(?:\.[0-9]+)?)',
    "violated": r'"violated"\s*:\s*(true|false)',
    "winner": r'"winner"\s*:\s*"(A|B|tie)"',
    "where": r'"where"\s*:\s*"(.*?)"\s*,\s*"',
    "reason": r'"reason"\s*:\s*"(.*)"\s*\}',
}


def _fields(text: str) -> dict:
    """The verdict fields read one by one, for a reply whose JSON does not parse
    (glm writes unescaped quotes inside its reasons: ...标签也始终是同一 "FIRST" 样式...)."""
    out = {}
    for key, pattern in FIELDS.items():
        m = re.search(pattern, text, re.S)
        if m:
            raw = m.group(1)
            out[key] = float(raw) if key == "score" else raw == "true" if key == "violated" else raw
    return out


def _verdict(text: str) -> dict | None:
    for m in reversed(list(re.finditer(r"\{[^{}]*\}", text))):
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
    return _fields(text) or None


def _item_verdict(parsed: dict, text: str, item_id: str) -> dict:
    """One item's verdict from a group answer: from the parsed JSON, or read
    field by field from the text after the item's key when the JSON is broken."""
    if isinstance(parsed.get(item_id), dict):
        return parsed[item_id]
    m = re.search(r'"' + re.escape(item_id) + r'"\s*:\s*\{(.*?)\}\s*(?:,\s*"\d+\.\d+"|\}\s*$)', text.strip(), re.S)
    return _fields("{" + m.group(1) + "}") if m else {}


def _ask(model: str, content: list[dict]) -> dict:
    r = LLM(model).chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}], max_tokens=MAX_TOKENS)
    if not r.text.strip():
        # deepseek sometimes ends a long image request with an empty "stop"; that is no judgement at all
        raise RuntimeError(f"empty reply (finish={r.finish_reason}, completion_tokens={r.completion_tokens})")
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
    return {"item": "1.1", "violated": bool(problems), "problems": problems, "generated": generated,
            "capture_version": ev["capture_version"]}


def example_parts(items: list[Item]) -> list[dict]:
    """The worked examples of the items that have them, each one frame with its score and why.
    They go before the page and are marked as examples, so they are not taken for the page."""
    parts = []
    for it in items:
        for e in it.examples:
            parts.append({"type": "text", "text": f"【典型案例，不是要评的页面】{it.id} {it.name}:{e.score} 分。"
                                                  f"{e.story} 第 {e.frame} 帧:{e.note}"})
            parts.append(_image(EVIDENCE / e.story / e.version / "frames" / f"{e.frame:02d}.jpg", FRAME_W))
    if parts:
        parts.insert(0, {"type": "text", "text": "下面先给几个打过分的典型案例，用来对齐分数的尺度。案例之后才是要评的页面。"})
        parts.append({"type": "text", "text": "典型案例到此为止。下面是要评的页面。"})
    return parts


def check(item: Item, ev_dir: Path, model: str = JUDGE_MODEL) -> dict:
    content = evidence_parts(ev_dir, "") + [{"type": "text", "text": CHECK.format(id=item.id, name=item.name, description=item.description)}]
    answer = _ask(model, content)
    v = answer["verdict"] or {}
    violated = v.get("violated") if isinstance(v.get("violated"), bool) else None  # no usable verdict is a failed judgement
    return {"item": item.id, "page": str(ev_dir), "model": model, "prompt_hash": prompt_hash(CHECK),
            "capture_version": _capture_version(ev_dir), "violated": violated, "where": v.get("where"),
            "reason": v.get("reason"), "answer": answer}


def score(item: Item, ev_dir: Path, model: str = JUDGE_MODEL) -> dict:
    prompt = SCORE.format(id=item.id, name=item.name, description=item.description,
                          bands="\n".join(f"- {b}" for b in item.bands))
    content = example_parts([item]) + evidence_parts(ev_dir, "") + [{"type": "text", "text": prompt}]
    answer = _ask(model, content)
    v = answer["verdict"] or {}
    value = v.get("score")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        value = None  # an answer without a usable score is a failed judgement, not a 0
    return {"item": item.id, "page": str(ev_dir), "model": model, "prompt_hash": prompt_hash(SCORE),
            "capture_version": _capture_version(ev_dir), "score": value, "where": v.get("where"),
            "reason": v.get("reason"), "answer": answer}


def _usable_score(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        return None  # an answer without a usable score is a failed judgement, not a 0
    return float(value)


def _item_block(it: Item, with_bands: bool) -> str:
    text = f"{it.id} {it.name}\n说明:{it.description}"
    return text + ("\n" + "\n".join(f"- {b}" for b in it.bands) if with_bands else "")


def page_group(items: list[Item], ev_dir: Path, model: str = JUDGE_MODEL) -> tuple[dict, dict[str, dict]]:
    """One call for a group of scored items or of binary items on one page.
    Returns the shared answer and one record per item."""
    scored = all(it.scored for it in items)
    if not scored and not all(it.binary for it in items):
        raise ValueError("a group is all scored items or all binary items")
    template = TOGETHER if scored else CHECK_TOGETHER
    blocks = "\n\n".join(_item_block(it, scored) for it in items)
    shape = '{"score": 0.0, "where": "第几帧/哪一节/哪张图", "reason": "扣分的理由"}' if scored else '{"violated": false, "where": "第几帧/哪张图", "reason": "一两句话"}'
    keys = ", ".join(f'"{it.id}": {shape}' for it in items)
    content = (example_parts(items) if scored else []) + evidence_parts(ev_dir, "") + [{"type": "text", "text": template.format(items=blocks, keys=keys)}]
    answer = _ask(model, content)
    parsed = _json_object(answer["text"]) or {}
    shared = {"page": str(ev_dir), "model": model, "prompt_hash": prompt_hash(template), "items": [it.id for it in items],
              "answer": answer}
    recs = {}
    for it in items:
        v = _item_verdict(parsed, answer["text"], it.id)
        rec = {"item": it.id, "page": str(ev_dir), "model": model, "mode": "group", "prompt_hash": prompt_hash(template),
               "capture_version": _capture_version(ev_dir), "where": v.get("where"), "reason": v.get("reason")}
        if scored:
            rec["score"] = _usable_score(v.get("score"))
        else:
            rec["violated"] = v.get("violated") if isinstance(v.get("violated"), bool) else None
        recs[it.id] = rec
    return shared, recs


def _json_object(text: str) -> dict | None:
    """The last top-level {...} in the text that parses (a group answer nests objects)."""
    depth, start, found = 0, None, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                try:
                    found = json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    pass
    return found


def judge_page(item: Item, ev_dir: Path, model: str, record_dir: Path) -> dict:
    if item.gate:
        return gate(ev_dir)
    if item.id == "1.2":  # needs the data and arithmetic, not screenshots
        ev = json.loads((ev_dir / "evidence.json").read_text(encoding="utf-8"))
        return factcheck(ev_dir, [Path(p) for p in ev["data"]], record_dir)
    if item.binary:
        return check(item, ev_dir, model)
    if item.scored:
        return score(item, ev_dir, model)
    raise ValueError(f"{item.id} has no judging mode")


def _name(ev_dir: Path) -> tuple[str, str]:
    return ev_dir.parent.name, ev_dir.name


def _groups(items: list[Item], per_item: bool) -> list[list[Item]]:
    """One group per dimension (1.x, 2.x, 3.x); 1.1 and 1.2 are not model calls and stay alone."""
    if per_item:
        return [[it] for it in items]
    by_dim: dict[str, list[Item]] = {}
    for it in items:
        by_dim.setdefault(it.id.split(".")[0], []).append(it)
    out = []
    for its in by_dim.values():
        alone = [it for it in its if it.gate or it.id == "1.2"]
        rest = [it for it in its if it not in alone]
        out += [[it] for it in alone]
        if rest:
            out.append(rest)
    return out


GROUP_ATTEMPTS = 2


def _group_job(folder: Path, dim: str, fn):
    """A group call writes one record per item and its shared answer. An answer
    that leaves any item without a verdict (deepseek once wrote twelve paragraphs
    of review and no JSON) is asked again, and after GROUP_ATTEMPTS it is a
    failure: nothing is written and the next run asks again."""
    def run():
        for attempt in range(GROUP_ATTEMPTS):
            shared, recs = fn()
            missing = [k for k, r in recs.items() if all(r.get(f) is None for f in ("score", "violated"))]
            if not missing:
                break
        else:
            raise RuntimeError(f"no usable verdict for {', '.join(missing)} after {GROUP_ATTEMPTS} attempts")
        folder.mkdir(parents=True, exist_ok=True)
        for item_id, rec in recs.items():
            (folder / f"{item_id}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        shared["results"] = {k: r.get("score", r.get("violated")) for k, r in recs.items()}
        return shared
    return folder / f"group-{dim}.json", run


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("page")
    c.add_argument("pages", type=Path, nargs="+")
    c.add_argument("--items", required=True)
    c.add_argument("--per-item", action="store_true", help="one call per item instead of one per dimension")
    c.add_argument("--out", type=Path, default=Path("runs/judge"))
    c.add_argument("--model", default=JUDGE_MODEL)
    c.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    rubric = load()
    items = [rubric[i] for i in args.items.split(",")]
    groups = _groups(items, args.per_item)

    jobs = []
    for page in args.pages:
        dataset, version = _name(page)
        folder = args.out / "page" / dataset / version
        for group in groups:
            if len(group) == 1:
                it = group[0]
                jobs.append((folder / f"{it.id}.json", (lambda it=it, page=page, folder=folder: judge_page(it, page, args.model, folder))))
            else:
                jobs.append(_group_job(folder, group[0].id.split(".")[0], lambda g=group, page=page: page_group(g, page, args.model)))

    def run(job):
        path, fn = job
        if path.exists():
            return path, json.loads(path.read_text(encoding="utf-8"))
        try:
            rec = fn()
            unusable = rec.get("item") and all(rec.get(k) is None for k in ("score", "violated"))
            if unusable:
                raise RuntimeError("no usable verdict in the answer")
        except OutOfCredit:
            raise
        except Exception as e:  # noqa: BLE001 - a failed call is an infrastructure failure: no record, rerun later
            return path, {"error": str(e)[:300]}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        return path, rec

    pool = ThreadPoolExecutor(args.workers)
    try:
        results = pool.map(run, jobs)
        for path, rec in results:
            if "error" in rec:
                print(f"{path}: FAILED {rec['error']}", flush=True)
            elif "results" in rec:
                print(f"{path}: " + " ".join(f"{k}={v}" for k, v in rec["results"].items()), flush=True)
            elif "violated" in rec:
                print(f"{path}: violated={rec['violated']} {rec.get('where') or ''} {rec.get('reason') or rec.get('problems') or rec.get('wrong') or ''}", flush=True)
            else:
                print(f"{path}: score={rec['score']} {rec.get('where') or ''} {rec.get('reason') or ''}", flush=True)
    except OutOfCredit as e:
        pool.shutdown(wait=True, cancel_futures=True)
        raise SystemExit(f"stopped: out of credit ({e}); top up and rerun the same command, finished records are kept")
    pool.shutdown()


if __name__ == "__main__":
    main()
