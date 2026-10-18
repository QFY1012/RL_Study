"""给标注页 labels/report-marks.html 准备页面:控制变量那次(data-ablation.mjs)的报告页面,每份数据 editorial、design 各 3 版。

    python3 ui-rl/scripts/report-marks.py <实验目录> [--sets S0,S-bare,S-mix,P0,P-small]

实验目录里 gen/<集>/{editorial,design}-<k>.png 是 plain-report.mjs 截的 1440px 宽整页图。写出:
  labels/report-marks-pages/<页面>.webp   整页截图(webp,原尺寸);不进 git,标注页发布时一起传
  labels/report-marks.json                标注页的页面清单:页面编号、属于哪份数据、图、尺寸
  labels/report-marks-key.json            每个页面编号是哪份数据的哪一版(editorial / design);标注页不发布这个文件
同一份数据的 6 版排在一起,组内顺序打乱(固定种子),编号是「<集>-<a..f>」,看编号看不出是哪种提示词。
"""
import json
import random
import sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
src = Path(args[0])
sets = args[args.index("--sets") + 1].split(",") if "--sets" in args else ["S0", "S-bare", "S-mix", "P0", "P-small"]
out = ROOT / "labels" / "report-marks-pages"
out.mkdir(parents=True, exist_ok=True)

rng = random.Random(20261018)
pages, key = [], {}
for s in sets:
    names = [f"{p}-{k}" for p in ("editorial", "design") for k in (1, 2, 3)]
    rng.shuffle(names)
    for letter, name in zip("abcdef", names):
        pid = f"{s}-{letter}"
        im = Image.open(src / "gen" / s / f"{name}.png").convert("RGB")
        im.save(out / f"{pid}.webp", quality=82)
        pages.append({"id": pid, "set": s, "image": f"report-marks-pages/{pid}.webp", "w": im.width, "h": im.height})
        key[pid] = {"set": s, "version": name}
        print(pid, name, f"{im.width}x{im.height}", f"{(out / f'{pid}.webp').stat().st_size // 1024}KB")
(ROOT / "labels" / "report-marks.json").write_text(json.dumps(pages, ensure_ascii=False, indent=1))
(ROOT / "labels" / "report-marks-key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1))
print(f"{len(pages)} 页")
