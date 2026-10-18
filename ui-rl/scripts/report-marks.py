"""给标注页 labels/report-marks.html 准备页面和页面对:控制变量那次(data-ablation.mjs)的报告页面,每份数据 editorial、design 各 3 版。

    python3 ui-rl/scripts/report-marks.py <实验目录> [--sets S0,S-bare,S-mix,P0,P-small] [--extra P0:editorial-2:design-1,...]

实验目录里 gen/<集>/{editorial,design}-<k>.png 是 plain-report.mjs 截的 1440px 宽整页图。写出:
  labels/report-marks-pages/<页面>.webp   整页截图(webp,原尺寸);不进 git,标注页发布时一起传
  labels/report-marks.json                标注页的清单:pages(页面编号、属于哪份数据、图、尺寸)和 pairs(要比的两页,左右各是哪页)
  labels/report-marks-key.json            每个页面编号是哪份数据的哪一版(editorial / design);标注页不发布这个文件
页面编号是「<集>-<a..f>」(组内顺序打乱,固定种子),看编号看不出是哪种提示词。每份数据比 7 对:
editorial 之间 3 对、design 之间 3 对(训练时要分的是同一个提示词出的相近几版,评委在这上面还没测过),
editorial-1 对 design-1 1 对(差别早有结论,只为记下好在哪)。几份数据轮流排(标到一半停下,每份都有),左右随机;
--extra 再加几对要你判的(<集>:<一版>:<另一版>,比如评委和预设结论不一致的对),排在轮流的对后面;
最后加 3 对前面出现过的对,左右调换(repeat 记着是哪一对),看自己前后判得一不一致。
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
pid_of = {(v["set"], v["version"]): k for k, v in key.items()}
per_set = {}
for s in sets:
    two = [(f"{t}-{i}", f"{t}-{j}") for t in ("editorial", "design") for i, j in ((1, 2), (1, 3), (2, 3))] + [("editorial-1", "design-1")]
    rng.shuffle(two)
    per_set[s] = [(a, b) if rng.random() < 0.5 else (b, a) for a, b in two]
pairs = []
for n in range(max(len(v) for v in per_set.values())):
    for s in sets:
        if n < len(per_set[s]):
            a, b = per_set[s][n]
            pairs.append({"id": f"{s}-{n + 1}", "set": s, "left": pid_of[(s, a)], "right": pid_of[(s, b)]})
            print(f"{s}-{n + 1}", a, "|", b)
extra = [x.split(":") for x in args[args.index("--extra") + 1].split(",")] if "--extra" in args else []
for n, (s, a, b) in enumerate(extra, 1):
    if rng.random() < 0.5:
        a, b = b, a
    pairs.append({"id": f"{s}-x{n}", "set": s, "left": pid_of[(s, a)], "right": pid_of[(s, b)]})
    print(f"{s}-x{n}", a, "|", b)
for p in rng.sample(pairs[: len(pairs) // 2], 3):
    pairs.append({"id": f"{p['id']}-r", "set": p["set"], "left": p["right"], "right": p["left"], "repeat": p["id"]})
    print(f"{p['id']}-r 重复 {p['id']},左右调换")
(ROOT / "labels" / "report-marks.json").write_text(json.dumps({"pages": pages, "pairs": pairs}, ensure_ascii=False, indent=1))
(ROOT / "labels" / "report-marks-key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1))
print(f"{len(pages)} 页,{len(pairs)} 对")
