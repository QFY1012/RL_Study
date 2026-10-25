"""Read the rubric items from rubric/judge-dimensions.md.

The markdown is the only copy of the rubric: every table row that starts with an
item number ("| 2.7 | 视图连贯 | ...") is an item, with its name, its description
and how it is judged. The basis column (which labels and papers it comes from)
is for people and is not sent to the judge. A scored item also has five band
descriptions under "#### 2.7 视图连贯" in the banding section, the way MiMo's
eval rubric describes each of its dimensions. An aesthetic item adds worked
examples under its bands ("- 例 0.9 hype/original 第 3 帧:..."): a page from
runs/evidence, the frame that shows it, its score and why; the judge sees the
frame before scoring, so the bands mean the same thing on every call.
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
EXAMPLE = re.compile(r"^- 例 ([01](?:\.\d+)?) ([\w-]+)/([\w-]+) 第 (\d+) 帧:(.+)$")


@dataclass(frozen=True)
class Example:
    score: float
    story: str
    version: str
    frame: int
    note: str


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    description: str
    mode: str  # the rubric's own words, e.g. "门槛,代码", "打分(要按滚动位置截多帧)", "打分(照典型案例)"
    bands: tuple[str, ...] = ()  # five "[0.0, 0.2):..." lines for a scored item
    examples: tuple[Example, ...] = ()  # worked examples for an aesthetic item

    @property
    def scored(self) -> bool:
        return "打分" in self.mode


def load(path: Path = RUBRIC) -> dict[str, Item]:
    lines = path.read_text(encoding="utf-8").splitlines()
    bands: dict[str, list[str]] = {}
    examples: dict[str, list[Example]] = {}
    current = None
    for line in lines:
        head = BAND_HEAD.match(line)
        if head:
            current = head[1]
            bands[current] = []
            examples[current] = []
        elif current and (m := EXAMPLE.match(line)):
            examples[current].append(Example(float(m[1]), m[2], m[3], int(m[4]), m[5].strip()))
        elif current and (m := BAND.match(line)):
            bands[current].append(f"{m[1]}:{m[2].strip()}")
        elif line.startswith("#"):
            current = None
    items = {}
    for line in lines:
        m = ROW.match(line)
        if m:
            items[m[1]] = Item(m[1], m[2].strip(), m[3].strip(), m[4].strip(), tuple(bands.get(m[1], ())),
                               tuple(examples.get(m[1], ())))
    for it in items.values():
        if it.scored and len(it.bands) != 5:
            raise ValueError(f"{it.id} is scored but has {len(it.bands)} band descriptions, not 5")
    return items


def rubric_hash(path: Path = RUBRIC) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


if __name__ == "__main__":
    for it in load().values():
        print(f"{it.id:5} {'scored' if it.scored else 'trust':7} {it.name}  [{it.mode}] bands={len(it.bands)} examples={len(it.examples)}")
