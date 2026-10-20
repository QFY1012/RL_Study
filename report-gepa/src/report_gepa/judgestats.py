"""Summarize judge records: scores by version, coupling between items, the known answer.

    PYTHONPATH=src .venv/bin/python -m report_gepa.judgestats runs/judge [--min-pages 10]

- By version: for every item, the mean score (2.x) or the share of pages that
  violate it (1.x), per page version (original, seed-ds-1, pudding-ds-1...).
- Coupling: Spearman correlation between every two items over the pages that
  have both. Two items that move together almost always are one item judged
  twice, or one item leaning on the other; pairs above 0.7 are listed.
- Known answer: Pudding originals are taken to be better than generated pages
  (PLAN.md section 3). For every story, the original's expression total is
  compared with each generated version's.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path


def load(root: Path) -> dict[tuple[str, str], dict[str, float]]:
    """(story, version) -> {item: value}; a violation is 1, no violation 0."""
    pages: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for path in (root / "page").glob("*/*/*.json"):
        rec = json.loads(path.read_text(encoding="utf-8"))
        key = (path.parent.parent.name, path.parent.name)
        if rec.get("score") is not None:
            pages[key][rec["item"]] = float(rec["score"])
        elif rec.get("violated") is not None:
            pages[key][rec["item"]] = 1.0 if rec["violated"] else 0.0
    return pages


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float | None:
    ra, rb = _ranks(a), _ranks(b)
    n = len(ra)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra)
    vb = sum((y - mb) ** 2 for y in rb)
    return None if va == 0 or vb == 0 else cov / (va * vb) ** 0.5


def _key(item: str) -> tuple[int, int]:
    a, b = item.split(".")
    return int(a), int(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--min-pages", type=int, default=10)
    args = ap.parse_args()
    pages = load(args.root)
    items = sorted({i for v in pages.values() for i in v}, key=_key)
    versions = sorted({v for _, v in pages})

    print(f"{len(pages)} pages, items {', '.join(items)}\n")
    print("by version (2.x mean score 1-5, 1.x share violated):")
    print("item  " + "".join(f"{v:>16}" for v in versions))
    for it in items:
        row = []
        for v in versions:
            xs = [p[it] for (s, ver), p in pages.items() if ver == v and it in p]
            row.append(f"{sum(xs) / len(xs):>11.2f} n={len(xs):<2}" if xs else f"{'-':>16}")
        print(f"{it:5} " + "".join(row))

    print("\ncoupling (Spearman over pages that have both items):")
    pairs = []
    for a, b in combinations([i for i in items if i != "1.1"], 2):
        common = [p for p in pages.values() if a in p and b in p]
        if len(common) < args.min_pages:
            continue
        r = spearman([p[a] for p in common], [p[b] for p in common])
        if r is not None:
            pairs.append((r, a, b, len(common)))
    for r, a, b, n in sorted(pairs, key=lambda x: -abs(x[0])):
        flag = "  <- coupled" if abs(r) > 0.7 else ""
        print(f"  {a:5} {b:5} r={r:+.2f} n={n}{flag}")

    print("\nknown answer (original's expression total vs each generated version):")
    expr = [i for i in items if i.startswith("2.")]
    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for (story, ver), p in pages.items():
        if ver == "original":
            continue
        orig = pages.get((story, "original"))
        if not orig or any(i not in orig or i not in p for i in expr):
            continue
        so, sg = sum(orig[i] for i in expr), sum(p[i] for i in expr)
        tally[ver][0 if so > sg else 1 if so == sg else 2] += 1
    for ver, (win, tie, lose) in sorted(tally.items()):
        print(f"  original vs {ver}: original higher {win}, equal {tie}, lower {lose}")


if __name__ == "__main__":
    main()
