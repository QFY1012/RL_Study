"""Finding milestones: what a Pudding story found in its data, and whether a page says it too (pilot).

    PYTHONPATH=../report-gepa/src:src ../report-gepa/.venv/bin/python -m report_bench.milestones make <original_evidence_dir> <task_dir> <out_dir>
    PYTHONPATH=../report-gepa/src:src ../report-gepa/.venv/bin/python -m report_bench.milestones score <page_evidence_dir> <task_dir> <milestones.json> <out_dir>

make: an LLM reads the original story's prose and lists the findings it states,
each with the sentence it says it in and where it comes from: the data the task
gives (tables and columns), data the task does not give, or background. A pi
agent then recomputes every finding of the first kind from the task's data.
The ones the data bears out are the milestones (milestones.json), in the
data's numbers: the story's point, and the numbers a page made from this data
would get (the published data is not always the version the story used).

score: the findings a page states, in page order, each with the page's own
sentence and the data it comes from: the page agent's insights.json when it
wrote one, else an LLM that does not see the milestones reads them off the page. A quoted sentence the page does not have drops that
finding. A second call matches the milestones against those findings: stated,
partial (half) or absent or contradicted (none); coverage is the mean.
"""

from __future__ import annotations

import csv
import difflib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

from .llm import LLM

csv.field_size_limit(sys.maxsize)
MODEL = "deepseek-v4.1-flash"
PROSE = {"p", "h1", "h2", "h3", "h4", "li", "blockquote", "figcaption"}


def page_lines(ev: dict) -> list[str]:
    """The page's visible text in reading order: prose, and chart annotations long enough to say something."""
    seen, out = set(), []
    for t in sorted(ev["text"], key=lambda t: (t["y"], t["x"])):
        s = re.sub(r"\s+", " ", t["text"]).strip()
        if t["hidden"] or s in seen:
            continue
        if t["in_svg"] and len(s) >= 15:
            out.append(f"[chart] {s}")
        elif not t["in_svg"] and t["tag"] in PROSE and len(s) >= 20:
            out.append(s)
        else:
            continue
        seen.add(s)
    return out


def schema(task_dir: Path) -> str:
    """Each table's name, row count and columns with a few values: what the data is, without the data."""
    parts = []
    for p in sorted((task_dir / "data").glob("*.csv")):
        with p.open(encoding="utf-8", newline="") as f:
            rows = csv.reader(f)
            header = next(rows)
            sample = [r for _, r in zip(range(200), rows)]
            n = len(sample) + sum(1 for _ in rows)
        cols = []
        for i, c in enumerate(header):
            vals = list(dict.fromkeys(r[i] for r in sample if i < len(r) and r[i].strip()))[:3]
            cols.append(f"  - {c}: " + " | ".join(v[:40] for v in vals))
        parts.append(f"{p.name} ({n} rows)\n" + "\n".join(cols))
    return "\n\n".join(parts)


def ask_json(llm: LLM, prompt: str) -> tuple[dict, dict]:
    reply = llm.chat([{"role": "user", "content": prompt}])
    text = reply.text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0)) if m else {}
    return data, {"prompt_tokens": reply.prompt_tokens, "completion_tokens": reply.completion_tokens, "seconds": reply.seconds}


FINDINGS = """Below is the text of a published data story, in reading order ([chart] marks text drawn on a chart), and the tables of data a reader is given.

List the main findings the story is built around: what it sets out to show about the data, and the answers it gives (a comparison, a trend, a share, a relationship, an extreme). Only those; leave out supporting details, examples, single cases, results for subgroups, and the method, FAQ, credits, newsletter text and navigation hints. A finding stated in general and again for subgroups is one finding, the general one.

For each finding:
- claim: the finding in one plain sentence, with the story's numbers
- quote: one sentence copied exactly from the text where the story says it
- basis: "given" if it can be computed from the tables below alone; "external" if it also needs data the tables do not have; "background" if it is history, context, a quote or an explanation rather than something the data shows
- tables: for "given", the tables and columns it needs, like "measurements.csv: menWomen, maxHeightFront"
- missing: for "external", what data is missing

Answer with JSON only: {"findings": [{"claim": "...", "quote": "...", "basis": "...", "tables": "...", "missing": "..."}]}

TABLES
{schema}

STORY TEXT
{text}
"""

VERIFY = """The working directory has data/ (the tables) and findings.json: findings a published story states about this data, each with the sentence the story says it in.

For every finding, check with python on data/ whether the data shows it. Work out the numbers the claim rests on yourself, and where the story's sentence says what a term means (who counts, what counts as making it), use that. Result:
- holds: the data shows it; a number within 10% of yours counts, and so does a difference of rounding or units
- differs: the data shows the same thing in the same direction, but a number is off by more than 10%, or a member of a list does not belong (the story used a version of the data you do not have)
- fails: the data shows the opposite, or nothing like it
- cannot: the tables cannot settle it (a column it needs is not there, or it depends on a filter you cannot reproduce)

For holds and differs, also write the finding again as this data shows it: the same point, with your numbers and lists.

Write verified.json: {"findings": [{"id": <the finding's id>, "result": "holds|differs|fails|cannot", "claim": "the finding as this data shows it (holds and differs)", "values": "the numbers you got, short", "how": "how you computed them, one line"}]}

There is no browser and no network. Stop once verified.json is written.
"""

NARRATIVE = """Below is the text of a data report web page, in reading order ([chart] marks text drawn on a chart), and the tables of data it was made from.

List every finding the page states, in the order it appears. A finding is what the page says the data shows (a comparison, a trend, a share, a relationship, an extreme). A run of numbers with nothing said about them is not a finding. For each:
- claim: the finding in one plain sentence
- quote: one sentence copied exactly from the page where it says it
- data: "given" with the tables and columns it comes from (like "players.csv: rank, drafted"), or "external" / "background" if it does not come from these tables

Answer with JSON only: {"beats": [{"claim": "...", "quote": "...", "data": "..."}]}

TABLES
{schema}

PAGE TEXT
{text}
"""

MATCH = """MILESTONES are findings a published story made from a dataset. FINDINGS are what a web page about the same data states, with the page's own sentences.

For every milestone, decide whether the page states its point. Judge the point and its direction, not the numbers: the page may have computed the same thing a little differently, and numbers are checked elsewhere.
- stated: a finding makes the same point in the same direction
- partial: it points the same way but only loosely, or makes only part of the point
- absent: no finding makes the point; a page showing the data without saying the point is absent
- contradicted: a finding makes the opposite point

Answer with JSON only: {"milestones": [{"id": <id>, "result": "stated|partial|absent|contradicted", "beats": [<indexes of the findings you used>], "why": "one line"}]}

MILESTONES
{milestones}

FINDINGS
{beats}
"""


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("—", "-").replace("–", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def quoted(quote: str, text: str) -> bool:
    """Whether the page has this sentence: as written, or with a few words changed."""
    q, t = norm(quote), norm(text)
    if not q:
        return False
    if q in t:
        return True
    window = len(q)
    best = max((difflib.SequenceMatcher(None, q, t[i:i + window]).ratio() for i in range(0, max(1, len(t) - window + 1), max(1, window // 4))), default=0)
    return best >= 0.85


def make(orig_ev: Path, task_dir: Path, out: Path, model: str = MODEL) -> dict:
    from report_gepa.generate import run_agent  # the page agent's runner; only make needs it

    out.mkdir(parents=True, exist_ok=True)
    ev = json.loads((orig_ev / "evidence.json").read_text(encoding="utf-8"))
    text = "\n".join(page_lines(ev))
    llm = LLM(model)
    found, usage = ask_json(llm, FINDINGS.replace("{schema}", schema(task_dir)).replace("{text}", text))
    findings = found.get("findings", [])
    for i, f in enumerate(findings):
        f["id"] = i
        f["quote_found"] = quoted(f.get("quote", ""), text)
    (out / "findings.json").write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    given = [f for f in findings if f.get("basis") == "given"]
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        ws = Path(tmp) / "ws"
        shutil.copytree(task_dir / "data", ws / "data")
        (ws / "findings.json").write_text(json.dumps([{k: f.get(k, "") for k in ("id", "claim", "quote", "tables")} for f in given], ensure_ascii=False, indent=1), encoding="utf-8")
        system, task = Path(tmp) / "system.md", Path(tmp) / "task.txt"
        system.write_text("You check findings against data. You only check; you do not judge writing or design.\n", encoding="utf-8")
        task.write_text(VERIFY, encoding="utf-8")
        run = run_agent(ws, system, model, "high", f"  verify {task_dir.name}", task, "verified.json")
        verified = json.loads((ws / "verified.json").read_text(encoding="utf-8")) if (ws / "verified.json").exists() else {"findings": []}
    results = {v["id"]: v for v in verified.get("findings", [])}
    milestones = []
    for f in given:
        v = results.get(f["id"], {})
        f["verify"] = v
        # what the story found, in the numbers of the data the task gives
        if v.get("result") in ("holds", "differs") and f["quote_found"]:
            milestones.append({"id": len(milestones), "claim": v.get("claim") or f["claim"], "story_claim": f["claim"], "result": v["result"],
                               "values": v.get("values", ""), "tables": f.get("tables", ""), "quote": f["quote"]})
    rec = {"task": task_dir.name, "model": model, "milestones": milestones,
           "findings": findings, "usage": usage, "agent": {k: run.get(k) for k in ("steps", "seconds", "input_tokens", "output_tokens", "error") if k in run}}
    (out / "milestones.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def score(page_ev: Path, task_dir: Path, milestones_path: Path, out: Path, model: str = MODEL,
          insights: Path | None = None, drop: list[str] = ()) -> dict:
    """insights: the page agent's own insights.json (insight, data, the page's sentence); without it an LLM reads
    the findings off the page. drop: sentences to remove from the page text first (an adversarial copy of a page)."""
    out.mkdir(parents=True, exist_ok=True)
    ev = json.loads((page_ev / "evidence.json").read_text(encoding="utf-8"))
    lines = [l for l in page_lines(ev) if not any(norm(d) in norm(l) for d in drop)]
    text = "\n".join(lines)
    llm = LLM(model)
    if insights:
        own = json.loads(insights.read_text(encoding="utf-8"))
        own = own.get("insights", own) if isinstance(own, dict) else own
        beats = [{"claim": i.get("insight", ""), "quote": i.get("sentence", ""), "data": i.get("data", "")} for i in own if i.get("sentence")]
        u1 = None
    else:
        narr, u1 = ask_json(llm, NARRATIVE.replace("{schema}", schema(task_dir)).replace("{text}", text))
        beats = narr.get("beats", [])
    for b in beats:
        b["quote_found"] = quoted(b.get("quote", ""), text)
    kept = [b for b in beats if b["quote_found"]]
    ms = json.loads(milestones_path.read_text(encoding="utf-8"))["milestones"]
    listing = "\n".join(f"[{m['id']}] {m['claim']}" for m in ms)
    found = "\n".join(f"[{i}] {b['claim']} | page: \"{b['quote']}\"" for i, b in enumerate(kept))
    matched, u2 = ask_json(llm, MATCH.replace("{milestones}", listing).replace("{beats}", found or "(none)"))
    by_id = {m["id"]: m for m in matched.get("milestones", [])}
    credit = {"stated": 1.0, "partial": 0.5, "absent": 0.0, "contradicted": 0.0}
    rows = [{"id": m["id"], "claim": m["claim"], **by_id.get(m["id"], {"result": "absent", "why": "not answered"})} for m in ms]
    total, weight = sum(credit.get(r["result"], 0.0) for r in rows), len(rows)
    rec = {"page": str(page_ev), "from": "insights.json" if insights else "page", "dropped": list(drop),
           "coverage": round(total / weight, 3) if weight else None, "beats": len(beats), "beats_quote_missing": len(beats) - len(kept),
           "milestones": rows, "findings": beats, "usage": [u1, u2]}
    (out / "score.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def main():
    import argparse

    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    for a in ("original", "task", "out"):
        m.add_argument(a, type=Path)
    s = sub.add_parser("score")
    for a in ("page", "task", "milestones", "out"):
        s.add_argument(a, type=Path)
    s.add_argument("--insights", type=Path, help="the page agent's insights.json")
    s.add_argument("--drop", action="append", default=[], help="a sentence to take out of the page first")
    args = ap.parse_args()
    if args.cmd == "make":
        rec = make(args.original, args.task, args.out)
        print(json.dumps({"milestones": rec["milestones"],
                          "findings": [{k: f.get(k) for k in ("id", "basis", "claim", "quote_found")} | {"verify": f.get("verify", {}).get("result")} for f in rec["findings"]]},
                         ensure_ascii=False, indent=1))
    else:
        rec = score(args.page, args.task, args.milestones, args.out, insights=args.insights, drop=args.drop)
        print(json.dumps({k: rec[k] for k in ("from", "coverage", "beats", "beats_quote_missing", "milestones")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
