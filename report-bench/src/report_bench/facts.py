"""Data facts: the findings a page's writer delivers, and the computation behind each, run again by us.

facts.json is a list of facts:

    {"id": "west-returns-most",
     "claim": "Among regions with at least 100 orders, the West has the highest return rate: 19% of its 160 orders.",
     "series": [{"table": "orders.csv",
                 "filter": "region.map(region.value_counts()) >= 100",
                 "group": "region",
                 "measure": "mean(returned == 'yes')"}]}

A series keeps the rows `filter` selects (DataFrame.query), splits them by `group`
(a column or an expression, DataFrame.eval, or a list of them to group by
several at once; a group is then named "a | b") and gives every group one value:
`count` rows, or an aggregation (mean, median, sum, max, min) of a column or an
expression. A table is named by its path under the writer's data/, which holds
the given files and folders by their own names (as generate.py copies them).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

AGGS = ("mean", "median", "sum", "max", "min")


class FactError(ValueError):
    """A fact that cannot be run: bad JSON, a missing table, an expression pandas rejects."""


def load(path: Path) -> list[dict]:
    try:
        facts = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise FactError(f"{path.name}: {e}") from e
    if not isinstance(facts, list) or not all(isinstance(f, dict) and f.get("id") and f.get("claim") and f.get("series") for f in facts):
        raise FactError(f"{path.name}: not a list of facts with id, claim and series")
    return facts


def tables(data: list[Path]) -> dict[str, Path]:
    """Every file the writer saw, by its path under data/."""
    out = {}
    for p in data:
        if p.is_dir():
            out.update({f"{p.name}/{f.relative_to(p).as_posix()}": f for f in sorted(p.rglob("*")) if f.is_file()})
        else:
            out[p.name] = p
    return out


def run_series(files: dict[str, Path], s: dict) -> pd.DataFrame:
    """One row per group: the group, its value and how many rows it has."""
    if s.get("table") not in files:
        raise FactError(f"table {s.get('table')!r} is not in data/")
    try:
        df = pd.read_csv(files[s["table"]])
        rows = df.query(s["filter"], engine="python") if s.get("filter") else df
        group = s.get("group") or []
        parts = [pd.Series(rows.eval(g, engine="python"), index=rows.index).astype(object).fillna("<missing>").astype(str)
                 for g in ([group] if isinstance(group, str) else group)]
        key = pd.concat(parts, axis=1).agg(" | ".join, axis=1) if parts else pd.Series("all", index=rows.index)
        if s["measure"] == "count":
            values, agg = pd.Series(1, index=rows.index), "sum"
        else:
            m = re.fullmatch(r"\s*(\w+)\((.*)\)\s*", s["measure"])
            if not m or m.group(1) not in AGGS:
                raise FactError(f"measure {s['measure']!r}: use count or one of {', '.join(AGGS)}(...)")
            values, agg = pd.Series(rows.eval(m.group(2), engine="python"), index=rows.index).astype(float), m.group(1)
        out = values.groupby(key).agg([agg, "size"])
        return out.set_axis(["value", "rows"], axis=1).rename_axis("group").reset_index().sort_values("value", ascending=False)
    except FactError:
        raise
    except Exception as e:  # noqa: BLE001 - whatever pandas raises, the fact does not run
        raise FactError(f"{s.get('table')}: {type(e).__name__}: {str(e)[:200]}") from e


def run(files: dict[str, Path], fact: dict) -> list[pd.DataFrame]:
    """The result of every series of a fact."""
    return [run_series(files, s) for s in fact["series"]]
