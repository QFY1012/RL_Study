"""Read the rubric items from rubric/judge-dimensions.md.

The markdown is the only copy of the rubric: every table row that starts with an
item number ("| 2.4 | 一图多用 | ...") is an item, with its name, its description
and how it is judged. The basis column (which labels and papers it comes from)
is for people and is not sent to the judge. A scored item also has five band
descriptions under "#### 2.4 一图多用" in the banding section, the way MiMo's
eval rubric describes each of its dimensions.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

RUBRIC = Path(__file__).resolve().parents[2] / "rubric" / "judge-dimensions.md"
ROW = re.compile(r"^\| (\d+\.\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|")
BAND_HEAD = re.compile(r"^#### (\d+\.\d+) ")
BAND = re.compile(r"^- (\[0\.\d, [01]\.\d[)\]]):?(.+)$")


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    description: str
    mode: str  # the rubric's own words, e.g. "门槛", "打分(要按滚动位置截多帧)", "两两"
    bands: tuple[str, ...] = ()  # five "[0.0, 0.2):..." lines for a scored item

    @property
    def gate(self) -> bool:
        return "门槛" in self.mode

    @property
    def scored(self) -> bool:
        return "打分" in self.mode

    @property
    def pairwise(self) -> bool:
        return "两两" in self.mode


def load(path: Path = RUBRIC) -> dict[str, Item]:
    lines = path.read_text(encoding="utf-8").splitlines()
    bands: dict[str, list[str]] = {}
    current = None
    for line in lines:
        head = BAND_HEAD.match(line)
        if head:
            current = head[1]
            bands[current] = []
        elif current and (m := BAND.match(line)):
            bands[current].append(f"{m[1]}:{m[2].strip()}")
        elif line.startswith("#"):
            current = None
    items = {}
    for line in lines:
        m = ROW.match(line)
        if m:
            items[m[1]] = Item(m[1], m[2].strip(), m[3].strip(), m[4].strip(), tuple(bands.get(m[1], ())))
    for it in items.values():
        if it.scored and it.id != "1.2" and len(it.bands) != 5:
            raise ValueError(f"{it.id} is scored but has {len(it.bands)} band descriptions, not 5")
    return items


def rubric_hash(path: Path = RUBRIC) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


if __name__ == "__main__":
    for it in load().values():
        kind = "gate" if it.gate else "scored" if it.scored else "pairwise" if it.pairwise else "?"
        print(f"{it.id:5} {kind:8} {it.name}  [{it.mode}] bands={len(it.bands)}")
