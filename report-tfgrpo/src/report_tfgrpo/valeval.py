"""Score an experience list on GEPA's validation stories, the way GEPA scores a guide.

    PYTHONPATH=src:../report-gepa/src:../report-bench/src ../report-gepa/.venv/bin/python -m report_tfgrpo.valeval runs/tf2 [--step N]

The system prompt is the one a further step would have used (seed guide plus the
step's experiences); one page per val story is written and judged by report-gepa's
own adapter, so the mean is comparable with the val scores in
report-gepa/runs/gepa/full (seed 0.541, best 0112 0.669). Pages and judgements go
to <run>/val/; a page already judged is reused.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean

from report_gepa.generate import GUIDES
from report_gepa.optimize import Adapter, split

from . import prompts as P
from .practice import format_experiences


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--step", type=int, help="experiences after this step (default: the last one)")
    ap.add_argument("--guide", type=Path, default=GUIDES / "seed.md")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--browsers", type=int, default=4)
    args = ap.parse_args()

    steps = sorted((args.run / "experiences").glob("step-*.json"))
    path = args.run / "experiences" / f"step-{args.step:02d}.json" if args.step is not None else steps[-1]
    exps = json.loads(path.read_text(encoding="utf-8"))
    guide = args.guide.read_text(encoding="utf-8") + (P.EXPERIENCE_HEADER + format_experiences(exps) if exps else "")

    _, val, _ = split(8, 19, 0)  # GEPA's split of runs/gepa/full
    out = args.run / "val"
    out.mkdir(exist_ok=True)
    adapter = Adapter(out, args.workers, args.browsers)
    print(f"== {path.name}: {len(exps)} experiences, {len(val)} val stories", flush=True)
    batch = adapter.evaluate(val, {"guide": guide})
    for story, r in zip(val, batch.outputs):
        print(f"{story:18} {r['score']:.3f}  {r['summary']}", flush=True)
    print(f"val mean {mean(batch.scores):.3f}", flush=True)


if __name__ == "__main__":
    main()
