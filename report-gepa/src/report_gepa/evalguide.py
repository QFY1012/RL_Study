"""Score a guide on the val stories of runs/gepa/full, the way GEPA scores a candidate.

    PYTHONPATH=src:../report-bench/src .venv/bin/python -m report_gepa.evalguide runs/<name> [--guide guides/seed.md] [--with-rubric]

--with-rubric appends the scoring rules the page is scored by: the trust vetoes (1.1-1.3), and every
scored item with its description, its five bands and the text of its worked
examples (the judge also sees the examples' screenshots; a guide carries only
their text). It is the baseline a judge-driven optimiser has to beat: the
writer is told the judge's standard up front. One page per val story is
written and judged by the same Adapter as GEPA's; pages and judgements go to
<run>/rollouts/<guide hash>/ and the guide to <run>/guides/.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from statistics import mean

from .generate import GUIDES
from report_bench.judge import _item_block
from .optimize import Adapter, split
from report_bench.rubric import load

RUBRIC_HEADER = """

下面是这些网页的评分标准。每个网页由评审照这份标准打分:先看可信 1.1–1.3,犯了任何一条就整页 0 分;否则「表达」各条和「美感」各条分别打 0–1 分,总分是这些条的平均,2.2 论证和 2.3 叙事合起来算一条。"""


def rubric_text() -> str:
    rubric = load()
    parts = [f"{it.id} {it.name}(一票否决)\n说明:{it.description}" for it in rubric.values() if "门槛" in it.mode]
    for it in (r for r in rubric.values() if r.scored):
        block = _item_block(it, True)
        if it.examples:
            block += "\n典型案例:\n" + "\n".join(f"- {e.score} 分:{e.note}" for e in it.examples)
        parts.append(block)
    return RUBRIC_HEADER + "\n\n" + "\n\n".join(parts) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--guide", type=Path, default=GUIDES / "seed.md")
    ap.add_argument("--with-rubric", action="store_true", help="append the judge's scoring rules to the guide")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--browsers", type=int, default=4)
    args = ap.parse_args()

    guide = args.guide.read_text(encoding="utf-8") + (rubric_text() if args.with_rubric else "")
    _, val, _ = split(8, 19, 0)  # GEPA's split of runs/gepa/full
    args.run.mkdir(parents=True, exist_ok=True)
    adapter = Adapter(args.run, args.workers, args.browsers)
    print(f"== {args.guide.name}{' + rubric' if args.with_rubric else ''}: {len(guide)} characters, {len(val)} val stories", flush=True)
    batch = adapter.evaluate(val, {"guide": guide})
    for story, r in zip(val, batch.outputs):
        print(f"{story:18} {r['score']:.3f}  {r['summary']}", flush=True)
    print(f"val mean {mean(batch.scores):.3f}", flush=True)


if __name__ == "__main__":
    main()
