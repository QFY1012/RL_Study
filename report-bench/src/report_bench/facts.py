"""Data facts: the findings a page's writer delivers, with the code behind each, run again by us.

facts.json is a list of facts:

    {"id": "west-returns-most",
     "claim": "Among regions with at least 100 orders, the West has the highest return rate, 19%, against 14% in the East and 13% in the North.",
     "tables": {"orders": "data/orders.csv"},
     "code": "orders[orders.region.map(orders.region.value_counts()) >= 100].groupby('region').returned.apply(lambda s: (s == 'yes').mean())"}

`tables` names the files (paths from the writer's folder, as data/orders.csv)
that are read with pd.read_csv into variables; `code` is one Python expression over them, with pd
and np available. Every fact's code is evaluated as written, in the page agent's
sandbox (report-gepa/agent/sandbox.sh: no network, nothing but the workspace),
since it is code someone else wrote, and its value is printed the way pandas
prints it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[3] / "report-gepa" / "agent" / "sandbox.sh"
TIMEOUT = 600

RUN = r'''
import json
import numpy as np
import pandas as pd

pd.set_option("display.width", 200)
out = {}
for f in json.load(open("facts.json")):
    try:
        env = {"pd": pd, "np": np}
        env.update({name: pd.read_csv(path) for name, path in f["tables"].items()})
        value = eval(f["code"], env)
        out[f["id"]] = {"output": value.to_string() if hasattr(value, "to_string") else str(value)}
    except Exception as e:
        out[f["id"]] = {"error": f"{type(e).__name__}: {e}"[:300]}
print(json.dumps(out))
'''


class FactError(ValueError):
    """facts.json that cannot be read as a list of facts."""


def load(path: Path) -> list[dict]:
    try:
        facts = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise FactError(f"{path.name}: {e}") from e
    keys = ("id", "claim", "tables", "code")
    if not isinstance(facts, list) or not all(isinstance(f, dict) and all(f.get(k) for k in keys) for f in facts):
        raise FactError(f"{path.name}: not a list of facts with {', '.join(keys)}")
    return facts


def run(facts: list[dict], data: list[Path]) -> dict[str, dict]:
    """Every fact's printed value ("output") or why it failed ("error"), by id.
    `data` is what the writer found in data/: files and folders, by their own names."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "data").mkdir()
        for p in data:
            if p.is_dir():
                shutil.copytree(p, ws / "data" / p.name, copy_function=os.link)
            else:
                os.link(p, ws / "data" / p.name)
        (ws / "facts.json").write_text(json.dumps(facts), encoding="utf-8")
        (ws / "run.py").write_text(RUN, encoding="utf-8")
        proc = subprocess.run([str(SANDBOX), str(ws), "python3 run.py"], capture_output=True, text=True, timeout=TIMEOUT)
    if proc.returncode != 0:
        return {f["id"]: {"error": f"the run failed: {proc.stderr.strip()[-300:]}"} for f in facts}
    return json.loads(proc.stdout.strip().splitlines()[-1])
