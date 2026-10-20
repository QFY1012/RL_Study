"""Read the rubric items from rubric/judge-dimensions.md.

The markdown is the only copy of the rubric: every table row that starts with an
item number ("| 2.4 | 一图多用 | ...") is an item, with its name, its description
and how it is judged. The basis column (which labels and papers it comes from)
is for people and is not sent to the judge.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

RUBRIC = Path(__file__).resolve().parents[2] / "rubric" / "judge-dimensions.md"
ROW = re.compile(r"^\| (\d+\.\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|")


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    description: str
    mode: str  # the rubric's own words, e.g. "门槛", "打分(要按滚动位置截多帧)", "两两"

    @property
    def gate(self) -> bool:
        return "门槛" in self.mode

    @property
    def binary(self) -> bool:
        return "二值" in self.mode

    @property
    def scored(self) -> bool:
        return "打分" in self.mode

    @property
    def pairwise(self) -> bool:
        return "两两" in self.mode


def load(path: Path = RUBRIC) -> dict[str, Item]:
    items = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if m:
            items[m[1]] = Item(m[1], m[2].strip(), m[3].strip(), m[4].strip())
    return items


def rubric_hash(path: Path = RUBRIC) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


if __name__ == "__main__":
    for it in load().values():
        kind = "gate" if it.gate else "binary" if it.binary else "scored" if it.scored else "pairwise" if it.pairwise else "?"
        print(f"{it.id:5} {kind:8} {it.name}  [{it.mode}]")
