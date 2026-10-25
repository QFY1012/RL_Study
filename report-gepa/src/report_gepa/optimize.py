"""GEPA on the page-writing guide, scored by the rubric judge (PLAN section 6).

    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.optimize runs/gepa/<name> [--max-calls 120] [--val 8] [--train 19]

Data: The Pudding's stories whose published original is a scrolling story
(original_static in data/pudding/manifest.jsonl). The stories people labelled
(labels/round1) are the test set and never enter the run; the rest are shuffled
with --seed and split into val (GEPA's Pareto set) and train (its feedback
minibatches).

Reflection uses REFLECT instead of GEPA's default prompt, which asks to put
"all niche and domain specific factual information" into the instruction: with
pages of one story as the examples, it rewrote the guide into instructions for
that story ("把 The Pudding 的「Who is the Biggest Pop Star?」数据制作成一个中文网页报告").
The guide is used on every story, so REFLECT asks for general practice only.

One rollout is one story with one guide. The pi agent writes the page (and its
facts.json) with the guide as its system prompt and the benchmark's task
(generate.py), and the page is scored the one way every page is scored
(report_bench.score.score_page, judged by deepseek): trust items 1.1-1.3 veto
the page to 0; otherwise the score is the mean of the expression and
aesthetics items. The result's feedback lines are what reflection reads.

Each rollout's page, evidence, trust check and judgements stay in
<run>/rollouts/<guide hash>/<story>/ and are reused when present, so a restart or
GEPA asking again costs nothing; result.json holds the score.
Reflection replies are kept in <run>/reflections/<prompt hash>.md the same way, so a restart
mid-iteration proposes the same guide again and reuses its rollouts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gepa
from gepa.core.adapter import EvaluationBatch

from report_bench.llm import LLM, OutOfCredit
from report_bench.score import score_page
from .generate import GUIDES, generate_page

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "pudding"
LABELS = ROOT / "labels" / "round1"
GEN_MODEL = "deepseek-v4.1-flash"
JUDGE_MODEL = "deepseek-v4.1-flash"
REFLECT_MODEL = "deepseek-v4.1-flash"
REFLECT = """下面是一个写数据报告网页的 agent 用的指南(它的系统提示词):
```
<curr_param>
```

agent 按这份指南，为下面几份数据各写了一个网页。每个网页由一个评审按 rubric 打了分，并写了理由:
```
<side_info>
```

你的任务：改写这份指南，让 agent 以后写出的网页得分更高。

要求:
- 这份指南会用在各种完全不同的数据上(体育、文化、科学、社会……),上面只是其中几份。指南里只写通用的做法，不要出现任何具体数据集的名字、字段、数字、人物或结论，也不要针对某个话题写规定。
- 页面用什么语言、写到哪个文件、能用哪些工具，由固定的任务说明决定，指南里不要规定。
- 从分数和理由里找出反复出现的问题和做得好的地方，归纳成可操作的原则(怎么选图、怎么组织叙事、怎么写字、怎么标注、怎么让形象和气质贴合话题……)。不要只为某一条分数去改，也不要把评审的原话照抄成规则。
- 可信(1.1 页面可渲染、1.2 引用完整、1.3 数据准确)犯了任何一条整页 0 分：理由里指出的问题要写成明确的禁止。
- 保留原指南里有效的部分;新指南要完整，能直接替换原指南使用。

把新指南完整地写在一个 ``` 代码块里。"""


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

    propose_new_texts = None  # GEPA reads this; None means its own reflection with reflection_lm

    def __init__(self, run: Path, workers: int, browsers: int):
        self.run = run
        self.workers = workers
        self.browsers = threading.Semaphore(browsers)
        self.meta = {r["id"]: r for r in stories()}
        self.locks: dict[str, threading.Lock] = {}
        self.locks_lock = threading.Lock()

    def _lock(self, key: str) -> threading.Lock:
        with self.locks_lock:
            return self.locks.setdefault(key, threading.Lock())

    def rollout(self, guide: str, story: str) -> dict:
        h = guide_hash(guide)
        base = self.run / "rollouts" / h / story
        result_path = base / "result.json"
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
        record = base / "page" / "record.json"
        rec = (json.loads(record.read_text(encoding="utf-8")) if record.exists() else
               generate_page(guide_path, [DATA / story], base, "page", GEN_MODEL, render_slots=self.browsers))
        if not rec["delivered"]:
            return {"score": 0.0, "summary": f"no page: {rec.get('detail')}", "feedback": [f"没有交付页面:{rec.get('detail')}"]}
        return score_page(base / "page", [DATA / story], base, JUDGE_MODEL, self.browsers)

    # GEPA's adapter protocol

    def evaluate(self, batch: list[str], candidate: dict[str, str], capture_traces: bool = False) -> EvaluationBatch:
        guide = candidate["guide"]

        def one(story: str) -> dict:
            try:
                return self.rollout(guide, story)
            except OutOfCredit:
                raise  # not the guide's fault: stop the run rather than hand GEPA a 0
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


REFLECTIONS: Path  # set by main to <run>/reflections


def reflection_path(messages) -> Path:
    return REFLECTIONS / f"{hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()[:12]}.md"


def reflection_lm(prompt) -> str:
    messages = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else prompt
    path = reflection_path(messages)
    if path.exists():
        return path.read_text(encoding="utf-8")
    text = LLM(REFLECT_MODEL).chat(messages, max_tokens=16384).text
    path.write_text(text, encoding="utf-8")
    return text


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
    args = ap.parse_args()

    args.run.mkdir(parents=True, exist_ok=True)
    global REFLECTIONS
    REFLECTIONS = args.run / "reflections"
    REFLECTIONS.mkdir(exist_ok=True)
    train, val, test = split(args.val, args.train, args.seed)
    (args.run / "split.json").write_text(json.dumps({"train": train, "val": val, "test": test}, indent=1), encoding="utf-8")
    print(f"train {len(train)}: {' '.join(train)}\nval {len(val)}: {' '.join(val)}\ntest {len(test)} (not used here)", flush=True)

    adapter = Adapter(args.run, args.workers, args.browsers)
    try:
        result = gepa.optimize(
            seed_candidate={"guide": args.seed_guide.read_text(encoding="utf-8")},
            trainset=train, valset=val, adapter=adapter, reflection_lm=reflection_lm, reflection_prompt_template=REFLECT,
            reflection_minibatch_size=args.minibatch, max_metric_calls=args.max_calls,
            run_dir=str(args.run / "gepa"), seed=args.seed, display_progress_bar=False,
        )
    except OutOfCredit as e:
        raise SystemExit(f"stopped: out of credit ({e}); top up and rerun the same command: GEPA resumes from its saved state and finished rollouts are reused")
    best = result.candidates[result.best_idx]["guide"]
    (args.run / "best-guide.md").write_text(best, encoding="utf-8")
    summary = {"best_idx": result.best_idx, "val_scores": result.val_aggregate_scores,
               "guides": [guide_hash(c["guide"]) for c in result.candidates]}
    (args.run / "result.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"best candidate {result.best_idx} ({guide_hash(best)}), val {result.val_aggregate_scores[result.best_idx]:.3f}; "
          f"seed val {result.val_aggregate_scores[0]:.3f}", flush=True)


if __name__ == "__main__":
    main()
