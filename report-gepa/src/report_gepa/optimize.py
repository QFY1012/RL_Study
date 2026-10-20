"""GEPA on the page-writing guide, scored by the rubric judge (PLAN section 6).

    PYTHONPATH=src .venv/bin/python -m report_gepa.optimize runs/gepa/<name> [--max-calls 120] [--val 8] [--train 19]

Data: The Pudding's stories whose published original is a scrolling story
(original_static in data/pudding/manifest.jsonl). The stories people labelled
(labels/round1) are the test set and never enter the run; the rest are shuffled
with --seed and split into val (GEPA's Pareto set) and train (its feedback
minibatches).

One rollout is one story with one guide. The pi agent writes the page with the
guide as its system prompt; the fixed task adds that the page is in English and
that pageshot (agent/bin) shows the page the way the judge sees it. The page is
captured and judged by deepseek:
- trust: 1.1 from the capture and 1.3 by eye; a violation makes the score 0.
  1.2 (the agent fact check) is left out.
- expression: every scored 2.x item, 0-1, in one call.
- aesthetics: 3.1 and 3.2 by group pick against a ladder of three fixed opponents
  for the story, made once and reused: a page by the seed guide (low), a page by
  guides/detailed.md (middle) and the published Pudding original (high). The
  page and the three opponents form a group of four judged in four Latin-square
  rounds, at PICK_FRAMES frames a page. The page's net share of votes in [-1, 1]
  maps to [0, 1]. One opponent alone either always wins (the original) or soon
  always loses (the seed page), and then the score stops telling versions apart;
  the reasons the judge gives for the original's wins are also how reflection
  learns what no generated page has done yet.
The score is the mean of the expression items and the two aesthetics items: equal weights until weights are fitted on whole-page labels.
An item the judge gave no verdict for is left out of the mean, not counted as 0.

Each rollout's page, evidence and judgements stay in
<run>/rollouts/<guide hash>/<story>/ and are reused when present, so a restart or
GEPA asking again costs nothing; result.json (result-compare.json) holds the score.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gepa
from gepa.core.adapter import EvaluationBatch

from . import judge as J
from .capture import capture
from .generate import GUIDES, generate_page
from .llm import LLM
from .rubric import load

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "pudding"
LABELS = ROOT / "labels" / "round1"
ORIGINALS = ROOT / "runs" / "evidence"
ANCHORS = {"seed": GUIDES / "seed.md", "detail": GUIDES / "detailed.md"}
ANCHOR_NAMES = {"seed": "种子指南页", "detail": "详细指南页", "original": "Pudding 原文", "evidence": "这一版"}
PICK_FRAMES = 12
GEN_MODEL = "deepseek-v4.1-flash"
JUDGE_MODEL = "deepseek-v4.1-flash"
REFLECT_MODEL = "deepseek-v4.1-flash"
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
TASK = """工作目录下的 data/ 里是一份报告的数据(有 README 的话是数据说明)。先读懂数据,再按系统提示词的要求把它做成一个网页,写到工作目录的 index.html。页面上的文字用英文写。
index.html 是一个完整的 HTML 文件,CSS 和脚本都写在里面,不引用任何外部资源(打开页面时没有网络)。
想看页面的效果,运行 pageshot index.html:它像读者一样滚动页面,每屏截一张图到 _shots/frames/,再给一张缩小的整页图 _shots/thumb.jpg,用 read 工具看这些图。改页面用 edit 工具直接改 index.html。写完就结束。"""


def stories() -> list[dict]:
    rows = [json.loads(line) for line in (DATA / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if r["ok"] and r["original_static"]]


def labelled() -> set[str]:
    out = set()
    for path in LABELS.glob("*.csv"):
        if not path.name.endswith("-boxes.csv"):
            out |= {row["dataset"] for row in csv.DictReader(path.open(encoding="utf-8-sig"))}
    return out


def split(n_val: int, n_train: int, seed: int) -> tuple[list[str], list[str], list[str]]:
    static = {r["id"] for r in stories()}
    test = labelled() & static
    rest = sorted(static - test)
    random.Random(seed).shuffle(rest)
    return rest[n_val:n_val + n_train], rest[:n_val], sorted(test)


def guide_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


class Adapter:
    """GEPA adapter: a candidate is {"guide": text}; a data instance is a story id."""

    def __init__(self, run: Path, workers: int, browsers: int, compare: bool):
        self.run = run
        self.workers = workers
        self.browsers = threading.Semaphore(browsers)
        self.compare = compare
        self.rubric = load()
        self.scored = [it for it in self.rubric.values() if it.scored]
        self.pick_items = [it for it in self.rubric.values() if it.pairwise]
        self.task = run / "task.txt"
        self.task.write_text(TASK, encoding="utf-8")
        self.meta = {r["id"]: r for r in stories()}
        self.locks: dict[str, threading.Lock] = {}
        self.locks_lock = threading.Lock()

    def _lock(self, key: str) -> threading.Lock:
        with self.locks_lock:
            return self.locks.setdefault(key, threading.Lock())

    def _page(self, guide_path: Path, story: str, pages: Path, name: str, ev: Path) -> dict:
        """Write and capture one page, reusing what is already there."""
        record = pages / name / "record.json"
        rec = (json.loads(record.read_text(encoding="utf-8")) if record.exists() else
               generate_page(guide_path, [DATA / story], pages, name, GEN_MODEL, render_slots=self.browsers, task_path=self.task))
        if rec["delivered"] and not (ev / "evidence.json").exists():
            with self.browsers:
                capture(str(pages / name / "index.html"), ev, None, [DATA / story])
        return rec

    def anchor(self, story: str, name: str) -> Path | None:
        """One fixed opponent of the ladder: "seed" or "detail" (a page by that guide) or "original"."""
        with self._lock(f"anchor/{story}/{name}"):
            if name == "original":
                ev = ORIGINALS / story / "original"
                if not (ev / "evidence.json").exists():
                    with self.browsers:
                        capture(self.meta[story]["url"], ev, PROXY, [DATA / story])
                return ev
            base = self.run / "anchors" / story
            rec = self._page(ANCHORS[name], story, base / "pages", name, base / name)
            return base / name if rec["delivered"] else None

    def rollout(self, guide: str, story: str) -> dict:
        h = guide_hash(guide)
        base = self.run / "rollouts" / h / story
        result_path = base / ("result-compare.json" if self.compare else "result.json")
        with self._lock(f"{h}/{story}"):
            if result_path.exists():
                return json.loads(result_path.read_text(encoding="utf-8"))
            base.mkdir(parents=True, exist_ok=True)
            guide_path = self.run / "guides" / f"{h}.md"
            guide_path.parent.mkdir(parents=True, exist_ok=True)
            guide_path.write_text(guide, encoding="utf-8")
            result = self._rollout(guide_path, story, base)
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[rollout] {h}/{story}: score={result['score']:.3f} {result['summary']}", flush=True)
            return result

    def _rollout(self, guide_path: Path, story: str, base: Path) -> dict:
        ev = base / "evidence"
        names = ["seed", "detail", "original"] if self.compare else []
        with ThreadPoolExecutor(1 + len(names)) as pool:
            page = pool.submit(self._page, guide_path, story, base, "page", ev)
            anchors = [pool.submit(self.anchor, story, n) for n in names]
            rec, anchors = page.result(), [a.result() for a in anchors]
        if not rec["delivered"]:
            return {"score": 0.0, "summary": f"no page: {rec.get('detail')}", "feedback": [f"没有交付页面:{rec.get('detail')}"]}

        judged = base / "judgements.json"
        items: dict[str, dict] = json.loads(judged.read_text(encoding="utf-8")) if judged.exists() else {}
        gate = J.gate(ev)
        items["1.1"] = {"violated": gate["violated"], "reason": "; ".join(gate["problems"])}
        jobs = [("1.3", lambda: {"1.3": J.check(self.rubric["1.3"], ev, JUDGE_MODEL)}, ["1.3"]),
                ("2.x", lambda: J.page_group(self.scored, ev, JUDGE_MODEL)[1], [it.id for it in self.scored])]
        group = [a for a in anchors if a] + [ev]
        if self.compare and len(group) >= 2:
            jobs.append(("3.x", lambda: J.pick(self.pick_items, group, JUDGE_MODEL, PICK_FRAMES)[1], [it.id for it in self.pick_items]))
        for name, fn, ids in jobs:
            if all(i in items for i in ids):
                continue
            try:
                items.update(fn())
            except Exception as e:  # noqa: BLE001 - a judge failure leaves these items out, it is not a 0
                print(f"[judge] {base.parent.name}/{story} {name}: FAILED {str(e)[:200]}", flush=True)
        judged.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")

        vetoed = [k for k in ("1.1", "1.3") if items.get(k, {}).get("violated") is True]
        parts = {it.id: items[it.id]["score"] for it in self.scored if items.get(it.id, {}).get("score") is not None}
        if self.compare:
            for it in self.pick_items:
                r = items.get(it.id)
                if r and r.get("ok"):
                    parts[it.id] = (r["pick_norm"]["evidence"] + 1) / 2
        score = 0.0 if vetoed else (sum(parts.values()) / len(parts) if parts else 0.0)
        return {"score": score, "vetoed": vetoed, "parts": parts,
                "summary": ("vetoed by " + ",".join(vetoed) if vetoed else " ".join(f"{k}={v:.2f}" for k, v in parts.items())),
                "feedback": self._feedback(items, vetoed, ev)}

    def _feedback(self, items: dict, vetoed: list[str], ev: Path) -> list[str]:
        out = []
        for k in vetoed:
            r = items[k]
            out.append(f"{k} {self.rubric[k].name}:犯了,整页 0 分。{r.get('where') or ''} {r.get('reason') or ''}".strip())
        for it in self.scored:
            r = items.get(it.id)
            if r and r.get("score") is not None:
                out.append(f"{it.id} {it.name}:{r['score']:.2f}。{r.get('where') or ''} {r.get('reason') or ''}".strip())
        if self.compare:
            for it in self.pick_items:
                r = items.get(it.id)
                if not r or not r.get("ok"):
                    continue
                net = r["pick_norm"]["evidence"]
                verdict = "在对手梯子里偏上" if net > 0 else "在对手梯子里偏下" if net < 0 else "和对手们没有明显差别"
                tally = ",".join(f"{ANCHOR_NAMES.get(n, n)} {v:+d}" for n, v in r["pick_sum"].items())
                rounds = []
                for p in r.get("per_round", []):
                    if p.get("usable") and p.get("reason"):
                        order = ",".join(f"页面{i}={ANCHOR_NAMES.get(n, n)}" for i, n in enumerate(p["order"], 1))
                        rounds.append(f"(本轮:{order}){p['reason']}")
                out.append(f"{it.id} {it.name}(和种子指南页、详细指南页、Pudding 原文组内比较):{verdict};"
                           f"各页净票数 {tally}。" + " / ".join(rounds))
        evid = json.loads((ev / "evidence.json").read_text(encoding="utf-8"))
        out.append(f"页面高 {evid.get('page_height')}px,滚动截了 {len(evid.get('frames', []))} 帧,"
                   f"滚动时固定在屏幕上的图 {sum(1 for c in evid.get('scroll_story', []) if c['pinned'])} 张。")
        return out

    # GEPA's adapter protocol

    def evaluate(self, batch: list[str], candidate: dict[str, str], capture_traces: bool = False) -> EvaluationBatch:
        guide = candidate["guide"]

        def one(story: str) -> dict:
            try:
                return self.rollout(guide, story)
            except Exception as e:  # noqa: BLE001 - GEPA wants a score for every example
                print(f"[rollout] {guide_hash(guide)}/{story}: FAILED {str(e)[:200]}", flush=True)
                return {"score": 0.0, "summary": "failed", "feedback": [f"生成或评判出错:{str(e)[:200]}"]}

        with ThreadPoolExecutor(min(self.workers, len(batch))) as pool:
            results = list(pool.map(one, batch))
        return EvaluationBatch(outputs=results, scores=[r["score"] for r in results],
                               trajectories=[{"story": s, **r} for s, r in zip(batch, results)] if capture_traces else None)

    def make_reflective_dataset(self, candidate: dict[str, str], eval_batch: EvaluationBatch, components_to_update: list[str]):
        records = []
        for t in eval_batch.trajectories:
            m = self.meta[t["story"]]
            records.append({
                "Inputs": {"data": f"The Pudding 公开的数据「{m['title']}」,文件:{', '.join(m['files'][:12])}"
                                   + (f" 等 {len(m['files'])} 个" if len(m["files"]) > 12 else "")},
                "Generated Outputs": f"按指南写出的网页,得分 {t['score']:.2f}(0–1)",
                "Feedback": "\n".join(t["feedback"]),
            })
        return {name: records for name in components_to_update}


def reflection_lm(prompt) -> str:
    messages = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else prompt
    return LLM(REFLECT_MODEL).chat(messages, max_tokens=16384).text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--seed-guide", type=Path, default=GUIDES / "seed.md")
    ap.add_argument("--val", type=int, default=8)
    ap.add_argument("--train", type=int, default=19)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-calls", type=int, default=120, help="rollouts GEPA may spend, seed evaluation included")
    ap.add_argument("--minibatch", type=int, default=3)
    ap.add_argument("--workers", type=int, default=8, help="rollouts at the same time")
    ap.add_argument("--browsers", type=int, default=4)
    ap.add_argument("--no-compare", dest="compare", action="store_false",
                    help="leave aesthetics out: no ladder pages, no group pick")
    args = ap.parse_args()

    args.run.mkdir(parents=True, exist_ok=True)
    train, val, test = split(args.val, args.train, args.seed)
    (args.run / "split.json").write_text(json.dumps({"train": train, "val": val, "test": test}, indent=1), encoding="utf-8")
    print(f"train {len(train)}: {' '.join(train)}\nval {len(val)}: {' '.join(val)}\ntest {len(test)} (not used here)", flush=True)

    adapter = Adapter(args.run, args.workers, args.browsers, args.compare)
    result = gepa.optimize(
        seed_candidate={"guide": args.seed_guide.read_text(encoding="utf-8")},
        trainset=train, valset=val, adapter=adapter, reflection_lm=reflection_lm,
        reflection_minibatch_size=args.minibatch, max_metric_calls=args.max_calls,
        run_dir=str(args.run / "gepa"), seed=args.seed, display_progress_bar=False,
    )
    best = result.candidates[result.best_idx]["guide"]
    (args.run / "best-guide.md").write_text(best, encoding="utf-8")
    summary = {"best_idx": result.best_idx, "val_scores": result.val_aggregate_scores,
               "guides": [guide_hash(c["guide"]) for c in result.candidates]}
    (args.run / "result.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"best candidate {result.best_idx} ({guide_hash(best)}), val {result.val_aggregate_scores[result.best_idx]:.3f}; "
          f"seed val {result.val_aggregate_scores[0]:.3f}", flush=True)


if __name__ == "__main__":
    main()
