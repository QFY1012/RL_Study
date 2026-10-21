"""Generate raw mock data the way The Pudding publishes it: one CSV of records per task.

    PYTHONPATH=src .venv/bin/python -m report_gepa.rawgen data/mock --per-kind 2 | tee runs/rawgen.log

For every kind in `domains.KINDS` the model writes a stdlib-only Python script.
`python gen.py gen data.csv` writes one row per business record (a visit, an
order, a ticket ...) with a few patterns planted in it; `python gen.py check
data.csv` reads the CSV back and prints, for every planted pattern, the numbers
that show it and whether it holds. The harness runs both in the task folder,
checks the CSV and the findings, and sends problems back for a rewrite (at most
twice). Findings are recomputed from the written CSV, so they are true of the
data by construction; they are the answer key for whether a page found them.

Output: <out>/<id>/{data.csv, gen.py, findings.json}; <out>/manifest.jsonl
records the draw, the attempts and the CSV's shape.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .domains import KINDS, Kind
from .llm import LLM, OutOfCredit

MODEL = "glm-5.3-flash"
MAX_REWRITES = 2
MAX_TOKENS = 65536
RUN_SECONDS = 300

# What one row is, per kind: the record a real system of that business logs.
RECORDS = {
    "sales_monthly": "一行一个订单明细(订单号、下单时间、大区、城市、渠道、品类、商品、数量、单价、实付金额、成本)",
    "ecommerce_funnel": "一行一次访问会话(会话号、用户、日期时间、流量渠道、设备、是否加购、是否下单、是否支付、支付金额、是否老客)",
    "product_weekly": "一行一个用户一天的活跃记录(日期、用户、注册日期、客户端版本、平台、使用的主要功能、会话数、是否崩溃)",
    "weather_city": "一行一个站点一小时的观测(时间、站点、气温、降水、风速、相对湿度、天气现象、AQI、PM2.5、PM10、O3)",
    "finance_budget": "一行一笔记账凭证(日期、部门、一级科目、二级科目、金额、对应预算科目、摘要)",
    "ab_test": "一行一个实验用户(用户、分组、进组日期、新老用户、平台、各核心指标和护栏指标的取值)",
    "survey_nps": "一行一份问卷(提交时间、渠道、年龄段、使用时长、推荐打分 0–10、各选择题的答案、开放题原话)",
    "support_tickets": "一行一张工单(工单号、创建时间、渠道、问题分类、首次响应时间、解决时间、是否重开、满意度评分、问题描述)",
    "logistics": "一行一个包裹(运单号、线路、始发仓、承运商、发货时间、签收时间、承诺时效、是否延误、延误原因)",
    "energy": "一行一栋楼一小时的用电(时间、楼栋、用途、有功电量、需量、峰平谷时段、电价)",
    "store_ops": "一行一家门店一天的经营(日期、门店、城市、面积、客流、成交单数、销售额、是否新开或闭店)",
    "hr_recruiting": "一行一位候选人(投递日期、岗位、部门、招聘渠道、走到的最后环节、各环节日期、是否接受 offer、未通过原因)",
    "education_scores": "一行一个学生一科的成绩(学号、班级、科目、本次得分、上次得分、各大题得分)",
    "server_sla": "一行一个服务一分钟的监控(时间、服务、请求数、错误数、P50、P95、P99 延迟、是否处于事故中)",
    "ad_campaign": "一行一个素材一天的投放(日期、渠道、广告组、素材、花费、曝光、点击、转化、转化收入)",
    "app_flow": "一行一位测试者在一款 App 的一个步骤(测试者、App、流程、步骤序号、步骤名、要填的内容、操作次数、耗时秒数、是否出错、出错描述)",
    "project_status": "一行一个任务(任务号、模块、负责人、优先级、计划开始和结束、实际开始和结束、预估工时、已用工时、状态、所属里程碑)",
    "competitor_matrix": "一行一个产品的一个功能点(产品、价格档位、功能分组、功能点、支持情况:支持/部分支持/不支持/收费、备注)",
    "inventory": "一行一个 SKU 一天的库存流水(日期、仓库、SKU、品类、供应商、期初库存、入库、出库、在途、是否缺货)",
    "weather_multi": "一行一个城市一天的观测(日期、城市、平均气温、最高最低气温、降水、日照时数、极端天气事件)",
    "hospital_outpatient": "一行一次就诊(就诊日期、挂号时段、科室、医生、职称、是否复诊、候诊分钟、是否投诉、投诉类别)",
    "transit_ridership": "一行一个车站一小时的进出站(日期、是否节假日、线路、车站、小时、进站人数、出站人数、断面满载率)",
    "agriculture": "一行一个地块一周的记录(周次、地块、作物、面积、本周降水、积温、病虫害记录、投入成本,收获周的产量)",
    "real_estate": "一行一套房源(楼盘、片区、楼栋、户型、面积、推售日期、成交日期或空、成交单价、成交总价)",
}

SCALES = {"小": (300, 3000), "中": (3000, 30000), "大": (30000, 300000)}

PROMPT = """你在为一个「数据分析报告」评测准备输入数据。参赛的 AI 只拿到一个 CSV 文件,要自己分析、自己找规律,再做成数据报告网页。请写一个 Python 脚本,造一份「{name}」的原始明细数据。

每一行是什么:{record}
行数:{low} 到 {high} 行。

数据要像真实业务系统直接导出的明细,和 The Pudding 公开的数据一样:
- 一行一条记录,每一列含义固定、单位统一;不要汇总行、不要小计、不要把不同粒度的东西混在一张表里。
- 列名用英文 snake_case,文本内容用中文。公司、人名、地名可以虚构但要像真的,不要「某某」「示例」「XXX」「产品A」这类占位符。
- 有真实的噪声和波动,有少量缺失值(空单元格),可以有一两处录入错误或极端值。

在数据里埋 3 到 5 条规律,让认真分析的人能发现,但不能一眼看出:
- 至少一条要分组或交叉才看得出(比如整体看不明显,拆到某个维度才显著)。
- 至少一条和时间有关(趋势、拐点、周期、某段时间的异常)。
- 效应要足够大,扣掉噪声后用数据能明确验证,不要埋在噪声里看不出来。
- 不要在任何列里写出结论文字。

脚本要求:
- 只用 Python 标准库(random、csv、datetime、math、statistics 等),固定随机种子 {seed}。
- `python gen.py gen <路径>` 写出 CSV(UTF-8,有表头)。
- `python gen.py check <路径>` 只用 csv 模块把这个 CSV 读回来,对每条规律重新计算能证明它的数字,向标准输出打印一个 JSON 列表,每项是 {{"finding": 中文一句话写清规律和关键数字, "numbers": {{指标名: 数值}}, "holds": 规律是否成立的布尔值}}。holds 要按你设的判定标准真正计算,不要写死。
- 只回复一个 ```python 代码块。"""

PLACEHOLDER = re.compile(r"lorem|ipsum|某某|示例|XXX|TODO|待填|产品[A-E](?![a-z])|公司[A-E](?![a-z])", re.I)
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")


def extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    return m.group(1) if m else text


def run(folder: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", "gen.py", *args], cwd=folder, capture_output=True,
                          text=True, timeout=RUN_SECONDS)


def shape(path: Path) -> dict:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    cells = [c for r in body for c in r]
    return {"rows": len(body), "columns": len(header), "header": header, "bytes": path.stat().st_size,
            "empty_cells": sum(1 for c in cells if c.strip() == ""),
            "ragged_rows": sum(1 for r in body if len(r) != len(header))}


def check(folder: Path, scale: str) -> tuple[list[str], dict | None, list | None]:
    """Run the script; return the problems a rewrite should fix, the CSV's shape and the findings."""
    try:
        gen = run(folder, "gen", "data.csv")
    except subprocess.TimeoutExpired:
        return [f"gen 运行超过 {RUN_SECONDS} 秒"], None, None
    if gen.returncode != 0:
        return [f"gen 运行出错:\n{gen.stderr[-2000:]}"], None, None
    path = folder / "data.csv"
    if not path.exists():
        return ["gen 没有写出 data.csv"], None, None
    s = shape(path)
    problems = []
    low, high = SCALES[scale]
    if not low <= s["rows"] <= high:
        problems.append(f"CSV 有 {s['rows']} 行,应在 {low}–{high} 行之间")
    if s["ragged_rows"]:
        problems.append(f"{s['ragged_rows']} 行的列数和表头不一致")
    bad = [h for h in s["header"] if not SNAKE.match(h)]
    if bad:
        problems.append(f"列名不是英文 snake_case:{', '.join(bad)}")
    if s["empty_cells"] == 0:
        problems.append("没有任何缺失值")
    text = path.read_text(encoding="utf-8")
    hits = sorted({m.group(0) for m in PLACEHOLDER.finditer(text)})
    if hits:
        problems.append(f"出现了占位符:{'、'.join(hits)}")
    if not re.search(r"[一-鿿]", text):
        problems.append("文本内容不是中文")
    try:
        chk = run(folder, "check", "data.csv")
    except subprocess.TimeoutExpired:
        return problems + [f"check 运行超过 {RUN_SECONDS} 秒"], s, None
    if chk.returncode != 0:
        return problems + [f"check 运行出错:\n{chk.stderr[-2000:]}"], s, None
    try:
        findings = json.loads(chk.stdout)
        assert isinstance(findings, list) and all({"finding", "numbers", "holds"} <= set(f) for f in findings)
    except (json.JSONDecodeError, AssertionError, TypeError):
        return problems + [f"check 的输出不是要求的 JSON 列表:{chk.stdout[:500]}"], s, None
    if not 3 <= len(findings) <= 5:
        problems.append(f"埋了 {len(findings)} 条规律,应为 3 到 5 条")
    for f in findings:
        if f["holds"] is not True:
            problems.append(f"这条规律在生成的数据里不成立,把效应做大或修正判定:{f['finding']}({f['numbers']})")
    return problems, s, findings


def make_one(llm: LLM, kind: Kind, scale: str, seed: int, folder: Path) -> tuple[dict | None, list | None, list[dict]]:
    low, high = SCALES[scale]
    messages = [{"role": "user", "content": PROMPT.format(name=kind.name, record=RECORDS[kind.id], low=low, high=high, seed=seed)}]
    attempts = []
    folder.mkdir(parents=True, exist_ok=True)
    for _ in range(MAX_REWRITES + 1):
        reply = llm.chat(messages, max_tokens=MAX_TOKENS)
        (folder / "gen.py").write_text(extract_code(reply.text), encoding="utf-8")
        problems, s, findings = check(folder, scale)
        attempts.append({"problems": problems, "finish": reply.finish_reason, "seconds": reply.seconds})
        if not problems:
            return s, findings, attempts
        messages += [{"role": "assistant", "content": reply.text},
                     {"role": "user", "content": "运行后发现以下问题,请改好后重新输出完整脚本:\n- " + "\n- ".join(problems)}]
    return None, None, attempts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--per-kind", type=int, default=2)
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
            scale, seed = rng.choice(list(SCALES)), rng.randrange(10**6)
            if not (args.out / rid / "findings.json").exists():
                jobs.append((kind, rid, scale, seed))
    print(f"{len(jobs)} datasets to generate with {MODEL}, {args.workers} at a time", flush=True)

    llm = LLM(model=MODEL)
    lock = threading.Lock()
    manifest = args.out / "manifest.jsonl"
    args.out.mkdir(parents=True, exist_ok=True)

    def one(job):
        kind, rid, scale, seed = job
        folder = args.out / rid
        s, findings, attempts = make_one(llm, kind, scale, seed, folder)
        row = {"id": rid, "kind": kind.id, "name": kind.name, "scale": scale, "seed": seed,
               "ok": findings is not None, "attempts": attempts}
        if findings is not None:
            (folder / "findings.json").write_text(json.dumps(findings, ensure_ascii=False, indent=1), encoding="utf-8")
            row["shape"] = {k: v for k, v in s.items() if k != "header"} | {"header": s["header"]}
        with lock, manifest.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    done = failed = 0
    with ThreadPoolExecutor(args.workers) as pool:
        for fut in as_completed([pool.submit(one, j) for j in jobs]):
            try:
                row = fut.result()
            except OutOfCredit:
                raise SystemExit("stopped: out of credit; top up and rerun the same command, finished datasets are kept")
            except Exception as e:  # noqa: BLE001 - one bad dataset must not stop the batch
                failed += 1
                print(f"error: {e}", flush=True)
                continue
            done += 1
            status = "ok" if row["ok"] else "FAILED " + "; ".join(p.splitlines()[0] for p in row["attempts"][-1]["problems"])
            rows = row.get("shape", {}).get("rows", "-")
            print(f"[{done + failed}/{len(jobs)}] {row['id']} {row['scale']} tries={len(row['attempts'])} rows={rows} {status}", flush=True)


if __name__ == "__main__":
    main()
