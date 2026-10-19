"""把标注页 labels/report-marks.html 打包成一个能离线打开的 HTML:页面清单和整页截图(data URI)、之前的标注都写进文件里。

    python3 ui-rl/scripts/report-marks-offline.py <输出 html> [<之前的标注目录>]

之前的标注目录是用 ArtifactData 把 marks 集合存下来的目录(每对一个 <对>.json),打开离线页时接着标。
离线页的标注存在浏览器本地,「导出标注」存成一个 JSON 文件:{<对>: 标注},和 db 里每对的文档一样。
"""
import base64
import json
import sys
from pathlib import Path

LABELS = Path(__file__).resolve().parent.parent / "labels"
if len(sys.argv) < 2:
    sys.exit(__doc__)
out = Path(sys.argv[1])
seed = {}
if len(sys.argv) > 2:
    for f in sorted(Path(sys.argv[2]).glob("*.json")):
        d = json.loads(f.read_text())
        seed[d["pair"]] = d
data = json.loads((LABELS / "report-marks.json").read_text())
for p in data["pages"]:
    p["image"] = "data:image/webp;base64," + base64.b64encode((LABELS / p["image"]).read_bytes()).decode()
page = (LABELS / "report-marks.html").read_text()
head = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"></head><body>'
inline = f"<script>window.REPORT_MARKS = {json.dumps(data, ensure_ascii=False)};\nwindow.REPORT_MARKS_SEED = {json.dumps(seed, ensure_ascii=False)};</script>\n"
i = page.index("<script>")
out.write_text(head + page[:i] + inline + page[i:] + "</body></html>")
print(f"{out}:{len(data['pairs'])} 对,{len(data['pages'])} 页截图,之前的标注 {len(seed)} 对,{out.stat().st_size // 1024} KB")
