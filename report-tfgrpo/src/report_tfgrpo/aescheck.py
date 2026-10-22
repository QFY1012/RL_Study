"""Check whether a group pick sees more in aesthetics than the worked-example scores.

    PYTHONPATH=src:../report-gepa/src ../report-gepa/.venv/bin/python -m report_tfgrpo.aescheck runs/tf1/step-00

For every story of a step whose pages are judged, runs MiMo's group pick on 3.1
and 3.2 over the story's pages (Williams square, one round per page, the prompt
report-gepa used until 4cb7c68) and sets it beside the per-page scores the run
already has. Prints, per item, how many rounds saw no clear difference and
whether the two orderings of the pages agree; writes <step>/aescheck.json.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import zlib
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

from report_gepa import judge as J
from report_gepa.rubric import load

MODEL = "deepseek-v4.1-flash"
MAX_FRAMES = 15  # per page; three pages of 40 frames is a request deepseek mostly answers empty

PICK = """下面 {n} 个页面用的是同一份数据，编号 1 到 {n}(顺序随机，与质量无关)。对下面每一条，只就这一条挑出明显比组内其他页面更好的页面和明显更差的页面(各可以是 0 个、1 个或多个);整组看不出明显差别就判「无明显差别」，不要硬排。

「明显」的标准：认真看完这几个页面后，能指出具体位置(第几帧、哪张图)、说出具体理由的差别就算明显，不要求一眼看出;说不出具体位置的不算。宁可少选，不要为了凑数把中游的选进来。
各条独立判断，不要因为某一条的结论连带改变其它条。

{items}

写完评语后，最后必须单独输出一行 JSON,每条一个键，不能省略:{{{keys}}}
good 和 bad 里填页面编号(整数),可以为空，两者不能有重复;no_clear_difference 为 true 时 good 和 bad 必须都为空。"""


def orders(n: int, seed: int) -> list[list[int]]:
    base, lo, hi = [0], 1, n - 1
    while len(base) < n:  # Williams' base: 0, n-1, 1, n-2, ...
        base.append(hi)
        hi -= 1
        if len(base) < n:
            base.append(lo)
            lo += 1
    perm = list(range(n))
    random.Random(seed).shuffle(perm)
    return [[perm[(x + r) % n] for x in base] for r in range(n)]


def pick(items, evs: list[Path]) -> dict[str, dict]:
    names = [e.name for e in evs]
    n = len(evs)
    blocks = "\n\n".join(J._item_block(it, False) for it in items)
    keys = ", ".join(f'"{it.id}": {{"good": [], "bad": [], "no_clear_difference": false, "reason": "一两句话，说出被选页面的具体位置"}}'
                     for it in items)
    prompt = PICK.format(n=n, items=blocks, keys=keys)
    parts = {(i, pos): J.evidence_parts(evs[i], str(pos + 1), MAX_FRAMES) for i in range(n) for pos in range(n)}

    def one(order):
        content = [p for pos, i in enumerate(order) for p in parts[(i, pos)]]
        answer = J._ask(MODEL, content + [{"type": "text", "text": prompt}])
        return order, J._json_object(answer["text"]) or {}

    with ThreadPoolExecutor(n) as pool:
        rounds = list(pool.map(one, orders(n, zlib.crc32(evs[0].parent.name.encode()))))
    out = {}
    for it in items:
        net, ncd, usable, reasons = {p: 0 for p in names}, 0, 0, []
        for order, parsed in rounds:
            v = parsed.get(it.id)
            if not isinstance(v, dict):
                continue
            usable += 1
            shown = [names[i] for i in order]
            at = lambda k: shown[int(k) - 1] if str(k).isdigit() and 1 <= int(k) <= n else None  # noqa: E731
            good = {at(k) for k in v.get("good") or []} - {None}
            bad = {at(k) for k in v.get("bad") or []} - {None} - good
            if v.get("no_clear_difference") is True and not good and not bad:
                ncd += 1
            for p in good:
                net[p] += 1
            for p in bad:
                net[p] -= 1
            reasons.append(v.get("reason"))
        out[it.id] = {"rounds": usable, "no_clear_difference": ncd, "net": net, "reasons": reasons}
    return out


def agreement(a: dict[str, float], b: dict[str, float]) -> tuple[int, int, int]:
    """Pairs of pages both orderings rank (agree, disagree); pairs either one calls a tie."""
    agree = disagree = ties = 0
    for x, y in combinations(a, 2):
        da, db = a[x] - a[y], b[x] - b[y]
        if da == 0 or db == 0 or math.isclose(da, 0) or math.isclose(db, 0):
            ties += 1
        elif (da > 0) == (db > 0):
            agree += 1
        else:
            disagree += 1
    return agree, disagree, ties


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", type=Path)
    args = ap.parse_args()
    items = [it for it in load().values() if it.id in ("3.1", "3.2")]
    path = args.step / "aescheck.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for story_dir in sorted(p for p in args.step.iterdir() if p.is_dir()):
        judged_path = story_dir / "judgements.json"
        evs = sorted(story_dir.glob("ev-*"))
        if story_dir.name in report or not judged_path.exists() or len(evs) < 2:
            continue
        judged = json.loads(judged_path.read_text(encoding="utf-8"))
        scores = {it.id: {e.name: judged.get(e.name, {}).get(it.id, {}).get("score") for e in evs} for it in items}
        if any(s is None for per in scores.values() for s in per.values()):
            continue
        report[story_dir.name] = {"pick": pick(items, evs), "scores": scores}
        path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    tot = {it.id: [0, 0, 0, 0, 0] for it in items}  # rounds, ncd, agree, disagree, ties
    for story, r in report.items():
        for it in items:
            p, s = r["pick"][it.id], r["scores"][it.id]
            ag = agreement(s, p["net"])
            t = tot[it.id]
            t[0] += p["rounds"]
            t[1] += p["no_clear_difference"]
            for k in range(3):
                t[2 + k] += ag[k]
            print(f"{story} {it.id}: scores {s}  pick net {p['net']}  ncd {p['no_clear_difference']}/{p['rounds']}  "
                  f"pairs agree/disagree/tie {ag}", flush=True)
    for k, (rounds, ncd, agree, disagree, ties) in tot.items():
        print(f"{k}: no clear difference {ncd}/{rounds} rounds; page pairs agree {agree}, disagree {disagree}, tie {ties}", flush=True)


if __name__ == "__main__":
    main()
