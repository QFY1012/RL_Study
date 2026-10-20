"""Analyse judge records: score coupling, agreement between runs, agreement with people.

    PYTHONPATH=src .venv/bin/python -m report_gepa.judgestats stats runs/judge/glm-a
    PYTHONPATH=src .venv/bin/python -m report_gepa.judgestats agree runs/judge/glm-a runs/judge/glm-b
    PYTHONPATH=src .venv/bin/python -m report_gepa.judgestats human runs/judge/glm-a labels/round1

stats
  - mean 0-1 score per item and page version (original, seed-ds-1, pudding-ds-1);
  - coupling: Spearman correlation between every two items over the pages that
    have both, pairs above 0.7 flagged;
  - multicollinearity: each item regressed on all the others over the pages that
    have every item; R^2 and VIF = 1 / (1 - R^2). VIF above 5 means the item is
    mostly predictable from the rest, i.e. it adds little that the others do not
    already say. The eigenvalues of the correlation matrix show how many
    independent directions the items really span.

agree (two runs over the same pages: the same judge twice, or two judge models)
  - per item: Spearman, mean absolute difference, how often both land in the
    same of the five score bands, and quadratic-weighted kappa on the bands.

human (labels exported by the labeling page: original vs pudding-ds-1)
  - per item: on the stories where people preferred one page, how often the item
    scores that page higher (ties counted apart);
  - per layer, and the rubric's page score: 0 when trust vetoes the page
    (1.1 failed, or 1.2 / 1.3 under 0.6), otherwise the mean expression score;
  - the aesthetic comparisons (3.x) against the same labels.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np

BANDS = (0.2, 0.4, 0.6, 0.8)


def _key(item: str) -> tuple[int, int]:
    a, b = item.split(".")
    return int(a), int(b)


def load(root: Path) -> dict[tuple[str, str], dict[str, float]]:
    """(story, version) -> {item: 0-1 score}."""
    pages: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for path in (root / "page").glob("*/*/*.json"):
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("score") is not None:
            pages[(path.parent.parent.name, path.parent.name)][rec["item"]] = float(rec["score"])
    return pages


def load_compare(root: Path) -> dict[tuple[str, str, str, str], str]:
    """(story, a, b, item) -> "a" | "b" | "tie"."""
    out = {}
    for path in (root / "compare").glob("*/*/*.json"):
        rec = json.loads(path.read_text(encoding="utf-8"))
        a, b = path.parent.name.split("~")
        out[(path.parent.parent.name, a, b, rec["item"])] = rec["winner"]
    return out


def _ranks(xs: np.ndarray) -> np.ndarray:
    order = np.argsort(xs, kind="mergesort")
    ranks = np.empty(len(xs))
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2
        i = j + 1
    return ranks


def spearman(a, b) -> float | None:
    ra, rb = _ranks(np.asarray(a, float)), _ranks(np.asarray(b, float))
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def band(x: float) -> int:
    return sum(x >= t for t in BANDS)


def weighted_kappa(a: list[int], b: list[int], k: int = 5) -> float | None:
    obs = np.zeros((k, k))
    for x, y in zip(a, b):
        obs[x, y] += 1
    n = obs.sum()
    if n == 0:
        return None
    w = np.array([[(i - j) ** 2 for j in range(k)] for i in range(k)]) / (k - 1) ** 2
    exp = np.outer(obs.sum(1), obs.sum(0)) / n
    denom = (w * exp).sum()
    return None if denom == 0 else float(1 - (w * obs).sum() / denom)


def stats(root: Path, min_pages: int) -> None:
    pages = load(root)
    items = sorted({i for v in pages.values() for i in v}, key=_key)
    versions = sorted({v for _, v in pages})
    print(f"{len(pages)} pages, items {', '.join(items)}\n")
    print("mean score by version:")
    print("item  " + "".join(f"{v:>18}" for v in versions))
    for it in items:
        cells = []
        for v in versions:
            xs = [p[it] for (_, ver), p in pages.items() if ver == v and it in p]
            cells.append(f"{np.mean(xs):>12.2f} n={len(xs):<3}" if xs else f"{'-':>18}")
        print(f"{it:5} " + "".join(cells))

    scored = [i for i in items if i != "1.1"]  # the gate is 0/1 and almost always 1
    print("\ncoupling (Spearman, pages with both items):")
    pairs = []
    for a, b in combinations(scored, 2):
        common = [p for p in pages.values() if a in p and b in p]
        if len(common) >= min_pages:
            r = spearman([p[a] for p in common], [p[b] for p in common])
            if r is not None:
                pairs.append((r, a, b, len(common)))
    for r, a, b, n in sorted(pairs, key=lambda x: -abs(x[0])):
        print(f"  {a:5} {b:5} r={r:+.2f} n={n}" + ("  <- coupled" if abs(r) > 0.7 else ""))

    full = [p for p in pages.values() if all(i in p for i in scored)]
    keep = [i for i in scored if np.std([p[i] for p in full]) > 0] if full else []
    print(f"\nmulticollinearity over {len(full)} pages that have all {len(scored)} items"
          + (f" (constant, left out: {', '.join(sorted(set(scored) - set(keep), key=_key))})" if set(scored) - set(keep) else "") + ":")
    if len(full) <= len(keep) + 1:
        print("  too few pages for the regression")
        return
    X = np.array([[p[i] for i in keep] for p in full])
    Z = (X - X.mean(0)) / X.std(0)
    for j, it in enumerate(keep):
        y = Z[:, j]
        others = np.column_stack([np.ones(len(Z)), np.delete(Z, j, axis=1)])
        coef, *_ = np.linalg.lstsq(others, y, rcond=None)
        r2 = 1 - ((y - others @ coef) ** 2).sum() / ((y - y.mean()) ** 2).sum()
        vif = float("inf") if r2 >= 1 else 1 / (1 - r2)
        print(f"  {it:5} R^2={r2:.2f} VIF={vif:6.1f}" + ("  <- mostly said by the others" if vif > 5 else ""))
    eig = np.sort(np.linalg.eigvalsh(np.corrcoef(Z, rowvar=False)))[::-1]
    share = eig / eig.sum()
    print("  correlation eigenvalues: " + " ".join(f"{e:.2f}" for e in eig))
    print(f"  first component explains {share[0]:.0%}; components needed for 80%: {int(np.searchsorted(np.cumsum(share), 0.8)) + 1}")


def agree(root_a: Path, root_b: Path) -> None:
    pa, pb = load(root_a), load(root_b)
    items = sorted({i for v in pa.values() for i in v} & {i for v in pb.values() for i in v}, key=_key)
    print(f"{root_a} vs {root_b}")
    print(f"{'item':5} {'n':>4} {'spearman':>9} {'|diff|':>7} {'same band':>10} {'kappa_w':>8}")
    for it in items:
        keys = [k for k in pa if it in pa[k] and k in pb and it in pb[k]]
        if not keys:
            continue
        a = [pa[k][it] for k in keys]
        b = [pb[k][it] for k in keys]
        r = spearman(a, b)
        diff = np.mean(np.abs(np.array(a) - np.array(b)))
        same = np.mean([band(x) == band(y) for x, y in zip(a, b)])
        kw = weighted_kappa([band(x) for x in a], [band(y) for y in b])
        print(f"{it:5} {len(keys):>4} {'-' if r is None else f'{r:+.2f}':>9} {diff:>7.2f} {same:>10.0%} {'-' if kw is None else f'{kw:+.2f}':>8}")
    ca, cb = load_compare(root_a), load_compare(root_b)
    common = [k for k in ca if k in cb]
    if common:
        print(f"comparisons: same winner on {np.mean([ca[k] == cb[k] for k in common]):.0%} of {len(common)}")


VETO_BELOW = 0.6  # rubric: 1.1 failed, or 1.2 / 1.3 under this, makes the page 0


def vetoed(p: dict[str, float]) -> bool:
    return p.get("1.1") == 0.0 or any(p.get(i) is not None and p[i] < VETO_BELOW for i in ("1.2", "1.3"))


def read_labels(folder: Path) -> dict[str, str]:
    """story -> "original" | "pudding-ds-1" | "tie" (both good or both bad)."""
    out = {}
    for path in sorted(folder.glob("*.csv")):
        if path.name.endswith("-boxes.csv"):
            continue
        for row in csv.DictReader(path.open(encoding="utf-8-sig")):
            out[row["dataset"]] = row["winner"] if row["winner"] in ("original", "pudding-ds-1") else "tie"
    return out


def _verdict(x: float, y: float) -> str:
    return "original" if x > y else "pudding-ds-1" if y > x else "tie"


def human(root: Path, labels_dir: Path) -> None:
    labels = read_labels(labels_dir)
    pages = load(root)
    decided = {s: w for s, w in labels.items() if w != "tie"}
    print(f"{len(labels)} labelled stories, {len(decided)} with a preferred page "
          f"({sum(w == 'original' for w in decided.values())} original, {sum(w == 'pudding-ds-1' for w in decided.values())} generated)\n")

    def report(name: str, value) -> None:
        agree_n = disagree = tie = 0
        for s, w in decided.items():
            o, g = pages.get((s, "original")), pages.get((s, "pudding-ds-1"))
            if not o or not g:
                continue
            vo, vg = value(o), value(g)
            if vo is None or vg is None:
                continue
            v = _verdict(vo, vg)
            agree_n += v == w
            disagree += v not in (w, "tie")
            tie += v == "tie"
        n = agree_n + disagree + tie
        if n:
            print(f"  {name:12} agree {agree_n}/{n} ({agree_n / n:.0%})  opposite {disagree}  tie {tie}")

    items = sorted({i for v in pages.values() for i in v}, key=_key)
    print("per item (the item alone picks the page with the higher score):")
    for it in items:
        report(it, lambda p, it=it: p.get(it))
    def mean_of(prefixes: tuple[str, ...]):
        def f(p):
            xs = [v for k, v in p.items() if k.startswith(prefixes) and k != "1.1"]
            return float(np.mean(xs)) if xs else None
        return f

    expression = mean_of(("2.",))

    def page_score(p):
        """The rubric's rule: a trust veto makes the page 0, otherwise the mean expression score."""
        if vetoed(p):
            return 0.0
        return expression(p)

    print("\nper layer:")
    report("layer 1", mean_of(("1.",)))
    report("layer 2", expression)
    report("veto+layer2", page_score)
    vetoes = [(s, v) for (s, v), p in pages.items() if vetoed(p)]
    print(f"\nvetoed pages ({len(vetoes)}): " + ", ".join(f"{s}/{v}" for s, v in sorted(vetoes)))

    comps = load_compare(root)
    if comps:
        print("\naesthetic comparisons (3.x):")
        for it in sorted({k[3] for k in comps}, key=_key):
            agree_n = n = 0
            for (s, a, b, i), w in comps.items():
                if i != it or s not in decided:
                    continue
                named = {"a": a, "b": b}.get(w, "tie")
                n += 1
                agree_n += named == decided[s]
            if n:
                print(f"  {it:12} agree {agree_n}/{n} ({agree_n / n:.0%})")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stats")
    s.add_argument("root", type=Path)
    s.add_argument("--min-pages", type=int, default=10)
    a = sub.add_parser("agree")
    a.add_argument("a", type=Path)
    a.add_argument("b", type=Path)
    h = sub.add_parser("human")
    h.add_argument("root", type=Path)
    h.add_argument("labels", type=Path)
    args = ap.parse_args()
    if args.cmd == "stats":
        stats(args.root, args.min_pages)
    elif args.cmd == "agree":
        agree(args.a, args.b)
    else:
        human(args.root, args.labels)


if __name__ == "__main__":
    main()
