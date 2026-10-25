"""Data facts: what a page computed from the data, run again by us.

facts.json is a list of facts. A fact is one finding and the computation behind it:

    {"id": "books-female-animals",
     "claim": "Among animals in at least 10 books, only birds and ducks are more often female.",
     "series": [{"table": "kids-book-animals.csv",
                 "filter": "pronoun in ['he/him', 'she/her'] and title.groupby(animal).transform('nunique') >= 10",
                 "group": "animal",
                 "measure": "mean(pronoun == 'she/her')"}]}

A series keeps the rows `filter` selects (DataFrame.query), splits them by `group`
(a column or an expression, DataFrame.eval) and gives every group one value:
`count` rows, or an aggregation (mean, median, sum, max, min) of a column or an
expression. Two series compare two tables grouped the same way.

A table is named by its path under the page writer's data/, which holds the
given files and folders by their own names (as generate.py copies them), so
`tables` maps those names back to the files.

Running a fact gives its result: one table of group values per series. `context`
turns a result into the text a model checks a page against, with the arithmetic
a sentence might rest on already done (shares, differences, ratios, percent
differences, correlations), since models are poor at arithmetic.
"""

from __future__ import annotations

import json
import re
from itertools import combinations
from pathlib import Path

import pandas as pd

AGGS = ("mean", "median", "sum", "max", "min")
MISSING = "<NA>"
FULL_TABLE = 40  # groups shown in full; a longer table shows its ends and the groups the page names
ENDS = 10


class FactError(ValueError):
    """A fact that cannot be run: bad JSON, a missing table, an expression pandas rejects."""


def load(path: Path) -> list[dict]:
    try:
        facts = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise FactError(f"{path.name}: {e}") from e
    if not isinstance(facts, list) or not all(isinstance(f, dict) and f.get("id") and f.get("series") for f in facts):
        raise FactError(f"{path.name}: not a list of facts with id and series")
    return facts


def tables(data: list[Path]) -> dict[str, Path]:
    """Every file the page writer saw, by its path under data/."""
    out = {}
    for p in data:
        if p.is_dir():
            out.update({f"{p.name}/{f.relative_to(p).as_posix()}": f for f in sorted(p.rglob("*")) if f.is_file()})
        else:
            out[p.name] = p
    return out


def run_series(files: dict[str, Path], s: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, str]:
    """The table, the kept rows, each row's group, each row's measured value (1 for count) and the aggregation."""
    if s.get("table") not in files:
        raise FactError(f"table {s.get('table')!r} is not in data/")
    try:
        df = pd.read_csv(files[s["table"]])
        rows = df.query(s["filter"], engine="python") if s.get("filter") else df
        key = rows.eval(s["group"], engine="python") if s.get("group") else pd.Series("all", index=rows.index)
        if not isinstance(key, pd.Series):
            key = pd.Series(key, index=rows.index)
        key = key.astype(object).where(key.notna(), MISSING).astype(str)
        if s["measure"] == "count":
            return df, rows, key, pd.Series(1.0, index=rows.index), "count"
        m = re.fullmatch(r"\s*(\w+)\((.*)\)\s*", s["measure"])
        if not m or m.group(1) not in AGGS:
            raise FactError(f"measure {s['measure']!r}: use count or one of {', '.join(AGGS)}(...)")
        values = rows.eval(m.group(2), engine="python")
        if not isinstance(values, pd.Series):
            values = pd.Series(values, index=rows.index)
        return df, rows, key, values.astype(float), m.group(1)
    except FactError:
        raise
    except Exception as e:  # noqa: BLE001 - whatever pandas raises, the fact does not run
        raise FactError(f"{s.get('table')}: {type(e).__name__}: {str(e)[:200]}") from e


def run(files: dict[str, Path], fact: dict) -> list[dict]:
    """One result per series: rows kept and every group's value (and size)."""
    out = []
    for s in fact["series"]:
        df, rows, key, values, agg = run_series(files, s)
        size = key.value_counts()
        value = size.astype(float) if agg == "count" else values.groupby(key).agg(agg)
        # a mean of a condition is a share: keep how many rows met it, which pages state as "50 of 53"
        hits = values.groupby(key).sum() if agg == "mean" and values.dropna().isin([0, 1]).all() else None
        out.append({"series": s, "agg": agg, "rows": len(rows), "table_shape": df.shape,
                    "groups": {g: (float(value[g]), int(size[g])) for g in value.sort_values(ascending=False).index},
                    "hits": None if hits is None else {g: int(hits[g]) for g in hits.index}})
    return out


def num(x: float) -> str:
    """Enough digits to check a page against: $107.75 must not come out as 107.8."""
    return f"{x:.6g}" if abs(x) < 1e6 else f"{x:,.0f}"


def pair(a: str, x: float, b: str, y: float) -> str:
    parts = [f"{a} - {b} = {num(x - y)}"]
    if y:
        parts.append(f"{a} / {b} = {num(x / y)}")
        parts.append(f"({a} - {b}) / {b} = {num((x - y) / y * 100)}%")
    if x:
        parts.append(f"({a} - {b}) / {a} = {num((x - y) / x * 100)}%")
    if x + y:
        parts.append(f"({a} - {b}) / mean = {num((x - y) / ((x + y) / 2) * 100)}%")
    return "; ".join(parts)


def named(groups: list[str], text: str) -> list[str]:
    """Groups the page's sentences mention by name."""
    low = text.lower()
    return [g for g in groups if g != MISSING and re.search(rf"(?<!\w){re.escape(g.lower())}(?:e?s)?(?!\w)", low)]


def context(fact: dict, result: list[dict], text: str = "") -> str:
    """What the page's sentences about this fact are checked against. `text` is
    what the page says about it, used to pick the groups to show from a long table."""
    lines = [f"[{fact['id']}]"]
    shared = set.intersection(*(set(r["groups"]) for r in result)) if len(result) > 1 else set()
    for i, (s, r) in enumerate(zip(fact["series"], result)):
        groups = list(r["groups"])
        keep = named(groups, text) + [g for g in groups if g in shared]
        what = "rows" if r["agg"] == "count" else f"{r['agg']} of {s['measure'][len(r['agg']) + 1:-1]}"
        lines.append(f"series {i}: {s['table']} ({r['table_shape'][0]} rows, {r['table_shape'][1]} columns in all); filter: {s.get('filter') or 'none'}; group by: {s.get('group') or 'none'}; "
                     f"value: {what}; {r['rows']} rows in {len(groups)} groups")
        shown = groups if len(groups) <= FULL_TABLE else [g for g in groups if g in set(groups[:ENDS] + keep + groups[-ENDS:])]
        total = sum(v for v, _ in r["groups"].values())
        for g in shown:
            v, n = r["groups"][g]
            share = f" ({num(v / total * 100)}% of all rows)" if r["agg"] == "count" and total else ""
            size = "" if r["agg"] == "count" else f" ({r['hits'][g]} of {n})" if r["hits"] else f" (n={n})"
            lines.append(f"  {g}: {num(v)}{share}{size}")
        if len(shown) < len(groups):
            lines.append(f"  ({len(groups) - len(shown)} more groups not shown; the list is sorted by value, so they lie between their neighbours)")
        compare = groups if len(groups) <= 3 else named(groups, text)[:4]
        for a, b in combinations(compare, 2):
            lines.append(f"  {pair(a, r['groups'][a][0], b, r['groups'][b][0])}")
    if len(result) > 1:
        tables = pd.concat([pd.Series({g: v for g, (v, _) in r["groups"].items()}) for r in result], axis=1, join="inner")
        for a, b in combinations(range(len(result)), 2):
            if len(tables) > 2:
                lines.append(f"series {a} vs {b}, {len(tables)} shared groups: spearman {num(tables[[a, b]].corr('spearman').iloc[0, 1])}, "
                             f"pearson {num(tables[[a, b]].corr().iloc[0, 1])}")
            else:
                for g in tables.index:
                    lines.append(f"  {g}: {pair(f'series {a}', tables.at[g, a], f'series {b}', tables.at[g, b])}")
    return "\n".join(lines)
