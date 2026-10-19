"""Generate simulated report data (JSON) for every kind in `domains.KINDS`.

    PYTHONPATH=src .venv/bin/python -m report_gepa.datagen data/reports --per-kind 3

Each report draws a scale and whether it carries written conclusions, asks the
model for a JSON export in the shape a real system of that business would
produce, checks it, and sends the problems back for a rewrite (at most twice).
Files land in <out>/<kind>/<id>.json; <out>/manifest.jsonl records the draw and
the structural features of every report, and <out>/split.json the split.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .domains import KINDS, NARRATIVE, SCALES, Kind
from .llm import LLM

DATA_MODEL = "glm-5.3-flash"
MAX_REWRITES = 2

PROMPT = """你在为一个「把 JSON 数据做成报告网页」的系统准备测试输入。请编一份「{name}」的原始数据,像真实业务系统导出给报告作者的那样。

内容:{contents}
规模:{scale}
文字:{narrative}

要求:
- 输出一个 JSON 对象。字段名用英文 snake_case,文本内容用中文。结构按这类数据在真实系统里自然的样子组织,嵌套、数组、对象怎么用都可以,不要套用固定模板。
- 数字之间要自洽:合计等于分项之和,比率和分子分母一致,环比同比和前后数值对得上。要有真实的波动,也要有一两处异常值。
- 公司、产品、人名、地名可以虚构,但要像真的,不要用「某某」「示例」「XXX」「产品A」这类占位符。
- 只写数据本身,不要写任何关于页面怎么排版、用什么图表的说明。
- 只回复一个 ```json 代码块。"""

PLACEHOLDER = re.compile(r"lorem|ipsum|某某|示例|XXX|TODO|待填|产品[A-E](?![a-z])|公司[A-E](?![a-z])", re.I)
DATE_LIKE = re.compile(r"^\d{4}-\d{2}(-\d{2})?([ T]\d{2}:\d{2})?")


def extract_json(text: str):
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.S)
    body = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(body)


def walk(value, depth=1):
    yield value, depth
    if isinstance(value, dict):
        for v in value.values():
            yield from walk(v, depth + 1)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v, depth + 1)


def features(data) -> dict:
    nodes = list(walk(data))
    arrays = [v for v, _ in nodes if isinstance(v, list)]
    strings = [v for v, _ in nodes if isinstance(v, str)]
    return {
        "bytes": len(json.dumps(data, ensure_ascii=False).encode()),
        "depth": max(d for _, d in nodes),
        "numbers": sum(1 for v, _ in nodes if isinstance(v, (int, float)) and not isinstance(v, bool)),
        "arrays": len(arrays),
        "object_arrays": sum(1 for a in arrays if a and all(isinstance(x, dict) for x in a)),
        "longest_array": max((len(a) for a in arrays), default=0),
        "dates": sum(1 for s in strings if DATE_LIKE.match(s)),
        "long_texts": sum(1 for s in strings if len(s) >= 40),
    }


def check(data, scale: str) -> list[str]:
    """Problems a rewrite should fix; an empty list means the report is usable."""
    if not isinstance(data, dict):
        return ["顶层必须是一个 JSON 对象"]
    problems = []
    f = features(data)
    low, high = {"小": (1500, 8000), "中": (4000, 22000), "大": (10000, 60000)}[scale]
    if not low <= f["bytes"] <= high:
        problems.append(f"整份 JSON 有 {f['bytes']} 字节,这个规模应在 {low}–{high} 字节之间")
    if f["object_arrays"] == 0:
        problems.append("没有任何由对象组成的数组,数据太单薄")
    if f["numbers"] < 20:
        problems.append(f"只有 {f['numbers']} 个数值,太少")
    text = json.dumps(data, ensure_ascii=False)
    hits = sorted(set(m.group(0) for m in PLACEHOLDER.finditer(text)))
    if hits:
        problems.append(f"出现了占位符:{'、'.join(hits)}")
    if not re.search(r"[一-鿿]", text):
        problems.append("文本内容不是中文")
    return problems


def make_one(llm: LLM, kind: Kind, scale: str, narrative: str) -> tuple[dict | None, list[dict]]:
    messages = [{"role": "user", "content": PROMPT.format(
        name=kind.name, contents=kind.contents, scale=SCALES[scale], narrative=NARRATIVE[narrative])}]
    attempts = []
    for _ in range(MAX_REWRITES + 1):
        reply = llm.chat(messages)
        try:
            data = extract_json(reply.text)
            problems = check(data, scale)
        except (json.JSONDecodeError, ValueError) as e:
            data, problems = None, [f"不是合法的 JSON:{e}"]
        attempts.append({"problems": problems, "finish": reply.finish_reason, "seconds": reply.seconds})
        if not problems:
            return data, attempts
        messages += [{"role": "assistant", "content": reply.text},
                     {"role": "user", "content": "这份数据有以下问题,请改好后重新输出完整的 JSON 代码块:\n- " + "\n- ".join(problems)}]
    return None, attempts


def split_ids(rows: list[dict], seed: int) -> dict:
    """Test kinds go to test; within every other kind, one report goes to val and the rest to train."""
    rng = random.Random(seed)
    out = {"train": [], "val": [], "test": []}
    by_kind: dict[str, list[str]] = {}
    for r in rows:
        by_kind.setdefault(r["kind"], []).append(r["id"])
    for kind, ids in sorted(by_kind.items()):
        ids = sorted(ids)
        if next(k for k in KINDS if k.id == kind).split == "test":
            out["test"] += ids
            continue
        rng.shuffle(ids)
        out["val"].append(ids[0])
        out["train"] += ids[1:]
    return {k: sorted(v) for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--per-kind", type=int, default=3)
    ap.add_argument("--kinds", help="comma-separated kind ids; default all")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    kinds = [k for k in KINDS if not args.kinds or k.id in args.kinds.split(",")]
    rng = random.Random(args.seed)
    jobs = []
    for kind in kinds:
        for i in range(args.per_kind):
            rid = f"{kind.id}-{i + 1:02d}"
            if (args.out / kind.id / f"{rid}.json").exists():
                continue
            jobs.append((kind, rid, rng.choice(list(SCALES)), rng.choice(list(NARRATIVE))))
    print(f"{len(jobs)} reports to generate with {DATA_MODEL}, {args.workers} at a time", flush=True)

    llm = LLM(model=DATA_MODEL)
    lock = threading.Lock()
    manifest = args.out / "manifest.jsonl"
    args.out.mkdir(parents=True, exist_ok=True)

    def run(job):
        kind, rid, scale, narrative = job
        data, attempts = make_one(llm, kind, scale, narrative)
        row = {"id": rid, "kind": kind.id, "name": kind.name, "scale": scale, "narrative": narrative,
               "ok": data is not None, "attempts": attempts}
        if data is not None:
            path = args.out / kind.id / f"{rid}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            row["data"] = f"{kind.id}/{rid}.json"
            row["features"] = features(data)
        with lock:
            with manifest.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    done = failed = 0
    with ThreadPoolExecutor(args.workers) as pool:
        for fut in as_completed([pool.submit(run, j) for j in jobs]):
            try:
                row = fut.result()
            except Exception as e:  # noqa: BLE001 - one bad call must not stop the batch
                failed += 1
                print(f"error: {e}", flush=True)
                continue
            done += 1
            status = "ok" if row["ok"] else "FAILED " + "; ".join(row["attempts"][-1]["problems"])
            size = row.get("features", {}).get("bytes", "-")
            print(f"[{done + failed}/{len(jobs)}] {row['id']} {row['scale']} {row['narrative']} "
                  f"tries={len(row['attempts'])} bytes={size} {status}", flush=True)

    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    good = {r["id"]: r for r in rows if r["ok"]}
    split = split_ids(list(good.values()), args.seed)
    (args.out / "split.json").write_text(json.dumps(split, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"usable {len(good)}; split train {len(split['train'])} / val {len(split['val'])} / test {len(split['test'])}", flush=True)


if __name__ == "__main__":
    main()
