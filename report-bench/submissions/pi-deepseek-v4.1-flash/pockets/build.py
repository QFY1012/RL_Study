import pandas as pd, numpy as np, html, json

d = pd.read_csv('data/measurements.csv')
w = d[d.menWomen == 'women']
m = d[d.menWomen == 'men']

g = d.groupby('menWomen')
front_mean = g.maxHeightFront.mean()
back_mean = g.maxHeightBack.mean()
front_min_mean = g.minHeightFront.mean()
back_min_mean = g.minHeightBack.mean()
front_w = g.maxWidthFront.mean()
back_w = g.maxWidthBack.mean()
front_wmin = g.minWidthFront.mean()

MEN = '#2d5f8a'
WOM = '#b8442a'
INK = '#20201d'
MUTED = '#6f6a60'
GRID = '#ddd6ca'


def fmt(x, n=2):
    return f'{x:.{n}f}'


# ---------------------------------------------------------------- chart: grouped bars front vs back
def bar_chart():
    cats = [('Front pocket, max height', 'maxHeightFront'),
            ('Front pocket, min height', 'minHeightFront'),
            ('Back pocket, max height', 'maxHeightBack'),
            ('Back pocket, min height', 'minHeightBack')]
    W, H = 1000, 360
    left, right, top, bot = 210, 30, 30, 56
    plot_w, plot_h = W - left - right, H - top - bot
    ymax = 26
    y = lambda v: top + plot_h - v / ymax * plot_h
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Average front and back pocket heights for men and women">']
    for v in range(0, 26, 5):
        s.append(f'<line x1="{left}" x2="{W-right}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{left-10}" y="{y(v)+4:.1f}" text-anchor="end" font-size="12" fill="{MUTED}">{v}"</text>')
    s.append(f'<text x="{left-10}" y="{top-14}" text-anchor="end" font-size="11" fill="{MUTED}">inches</text>')
    bw = 62
    for i, (label, col) in enumerate(cats):
        cx = left + (i + 0.5) * plot_w / len(cats)
        for j, (grp, color) in enumerate([('men', MEN), ('women', WOM)]):
            val = d[d.menWomen == grp][col].mean()
            x = cx - bw - 3 + j * (bw + 6)
            s.append(f'<rect x="{x:.1f}" y="{y(val):.1f}" width="{bw}" height="{top+plot_h-y(val):.1f}" fill="{color}" rx="2"/>')
            s.append(f'<text x="{x+bw/2:.1f}" y="{y(val)-7:.1f}" text-anchor="middle" font-size="13" font-weight="600" fill="{color}">{val:.1f}</text>')
        s.append(f'<text x="{cx:.1f}" y="{top+plot_h+22}" text-anchor="middle" font-size="12.5" fill="{INK}">{label}</text>')
    s.append(f'<line x1="{left}" x2="{W-right}" y1="{top+plot_h}" y2="{top+plot_h}" stroke="#9c958a" stroke-width="1"/>')
    # legend
    lx = W - right - 210
    for k, (name, color) in enumerate([('Men', MEN), ('Women', WOM)]):
        s.append(f'<rect x="{lx + k*100}" y="8" width="12" height="12" rx="2" fill="{color}"/>')
        s.append(f'<text x="{lx + k*100 + 18}" y="18" font-size="12.5" fill="{INK}">{name}</text>')
    s.append('</svg>')
    return ''.join(s)


# ---------------------------------------------------------------- chart: dot strip
def strip_chart():
    W, H = 1000, 330
    left, right, top = 70, 40, 36
    plot_w = W - left - right
    xmin, xmax = 10.5, 28.5
    x = lambda v: left + (v - xmin) / (xmax - xmin) * plot_w
    rows = {'men': 120, 'women': 235}
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Front pocket height of every pair of jeans, by gender">']
    for v in range(12, 29, 2):
        s.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{top-16}" y2="285" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{x(v):.1f}" y="308" text-anchor="middle" font-size="12" fill="{MUTED}">{v}"</text>')
    s.append(f'<text x="{W-right}" y="326" text-anchor="end" font-size="11.5" fill="{MUTED}">maximum front pocket height, inches</text>')
    for grp, color in [('men', MEN), ('women', WOM)]:
        sub = d[d.menWomen == grp].sort_values('maxHeightFront').reset_index(drop=True)
        base = rows[grp]
        s.append(f'<text x="20" y="{base-38}" font-size="13" font-weight="700" fill="{color}">{grp.capitalize()}</text>')
        s.append(f'<text x="20" y="{base-23}" font-size="11" fill="{MUTED}">n = {len(sub)}</text>')
        s.append(f'<line x1="{left}" x2="{W-right}" y1="{base+34}" y2="{base+34}" stroke="{GRID}" stroke-width="1"/>')
        for i, v in enumerate(sub.maxHeightFront):
            jitter = ((i * 37) % 23) - 11
            cy = base + jitter * 0.9
            s.append(f'<circle cx="{x(v):.1f}" cy="{cy:.1f}" r="6.4" fill="{color}" fill-opacity="0.62" stroke="#f7f4ee" stroke-width="0.8"/>')
        med = sub.maxHeightFront.median()
        s.append(f'<line x1="{x(med):.1f}" x2="{x(med):.1f}" y1="{base-46}" y2="{base+46}" stroke="{color}" stroke-width="2.2" stroke-dasharray="5 4"/>')
        s.append(f'<text x="{x(med):.1f}" y="{base-52}" text-anchor="middle" font-size="12" font-weight="600" fill="{color}">median {med:.1f}</text>')
    s.append('</svg>')
    return ''.join(s)


# ---------------------------------------------------------------- chart: women styles
def style_chart():
    styles = [('skinny', 'Skinny'), ('straight', 'Straight'), ('boot-cut', 'Boot-cut')]
    vals = [(lab, w[w.style == k].maxHeightFront.mean(), (w.style == k).sum()) for k, lab in styles]
    W, H = 470, 250
    left, right, top, bot = 96, 24, 26, 44
    plot_w, plot_h = W - left - right, H - top - bot
    xmax = 18
    x = lambda v: left + v / xmax * plot_w
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Average front pocket height of women\'s jeans by style">']
    for v in range(0, 19, 3):
        s.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{top-8}" y2="{top+plot_h}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{x(v):.1f}" y="{top+plot_h+18}" text-anchor="middle" font-size="11.5" fill="{MUTED}">{v}</text>')
    bh = 40
    for i, (lab, val, n) in enumerate(vals):
        y = top + i * (plot_h / len(vals)) + 4
        s.append(f'<text x="{left-10}" y="{y+bh/2+4:.1f}" text-anchor="end" font-size="12.5" fill="{INK}">{lab}</text>')
        s.append(f'<rect x="{left}" y="{y:.1f}" width="{x(val)-left:.1f}" height="{bh}" fill="{WOM}" fill-opacity="0.85" rx="2"/>')
        s.append(f'<text x="{x(val)+8:.1f}" y="{y+bh/2+5:.1f}" font-size="13" font-weight="600" fill="{WOM}">{val:.2f}<tspan font-size="11" font-weight="400" fill="{MUTED}">  in · n={n}</tspan></text>')
    s.append(f'<text x="{left}" y="16" font-size="11" fill="{MUTED}">inches, average of the maximum front pocket height</text>')
    s.append('</svg>')
    return ''.join(s)


# ---------------------------------------------------------------- chart: women brands
def brand_chart():
    b = w.groupby('brand').maxHeightFront.agg(['mean', 'size']).sort_values('mean')
    W = 1000
    rowh = 26
    top, bot = 34, 30
    H = top + bot + rowh * len(b)
    left, right = 200, 90
    plot_w = W - left - right
    xmax = 21
    x = lambda v: left + v / xmax * plot_w
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Average front pocket height of women\'s jeans by brand">']
    for v in (0, 5, 10, 15, 20):
        s.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{top-10}" y2="{H-bot}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{x(v):.1f}" y="{H-bot+18}" text-anchor="middle" font-size="11.5" fill="{MUTED}">{v}</text>')
    for i, (brand, row) in enumerate(b.iterrows()):
        y = top + i * rowh
        col = '#8f3320' if brand in ('Guess', "Levi's") else (WOM if brand == 'Abercrombie' else '#d3b3a8')
        s.append(f'<text x="{left-12}" y="{y+15}" text-anchor="end" font-size="12.5" fill="{INK}">{html.escape(brand)}</text>')
        s.append(f'<rect x="{left}" y="{y+3}" width="{x(row["mean"])-left:.1f}" height="15" fill="{col}" rx="1.5"/>')
        s.append(f'<text x="{x(row["mean"])+7:.1f}" y="{y+15}" font-size="11.5" fill="{MUTED}">{row["mean"]:.2f}</text>')
    s.append('</svg>')
    return ''.join(s)


# ---------------------------------------------------------------- chart: price scatter
def price_chart():
    W, H = 470, 330
    left, right, top, bot = 52, 26, 22, 52
    plot_w, plot_h = W - left - right, H - top - bot
    lx0, lx1 = np.log10(9), np.log10(260)
    x = lambda v: left + (np.log10(v) - lx0) / (lx1 - lx0) * plot_w
    ymin, ymax = 10, 29
    y = lambda v: top + plot_h - (v - ymin) / (ymax - ymin) * plot_h
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Scatter plot of price against front pocket height">']
    for v in (10, 15, 20, 25):
        s.append(f'<line x1="{left}" x2="{W-right}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{left-8}" y="{y(v)+4:.1f}" text-anchor="end" font-size="11" fill="{MUTED}">{v}</text>')
    for p in (10, 30, 100, 200):
        s.append(f'<line x1="{x(p):.1f}" x2="{x(p):.1f}" y1="{top}" y2="{top+plot_h}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{x(p):.1f}" y="{top+plot_h+20}" text-anchor="middle" font-size="11.5" fill="{MUTED}">${p}</text>')
    s.append(f'<text x="{W-right}" y="{H-8}" text-anchor="end" font-size="11" fill="{MUTED}">price (log scale)</text>')
    s.append(f'<text x="{left}" y="{top-8}" font-size="11" fill="{MUTED}" text-anchor="start">pocket height, in</text>')
    for grp, color in [('men', MEN), ('women', WOM)]:
        for _, r in d[d.menWomen == grp].iterrows():
            s.append(f'<circle cx="{x(r.price):.1f}" cy="{y(r.maxHeightFront):.1f}" r="4.6" fill="{color}" fill-opacity="0.55" stroke="#f7f4ee" stroke-width="0.7"/>')
    for k, (name, color) in enumerate([('Men', MEN), ('Women', WOM)]):
        lx = W - right - 118 + k * 62
        s.append(f'<circle cx="{lx}" cy="10" r="5" fill="{color}" fill-opacity="0.7"/>')
        s.append(f'<text x="{lx+10}" y="14" font-size="11.5" fill="{INK}">{name}</text>')
    s.append('</svg>')
    return ''.join(s)


# ---------------------------------------------------------------- extremes tables
shallow = d.nsmallest(5, 'maxHeightFront')[['brand', 'name', 'menWomen', 'maxHeightFront']]
deep = d.nlargest(4, 'maxHeightFront')[['brand', 'name', 'menWomen', 'maxHeightFront']]

def rows_html(df):
    out = []
    for _, r in df.iterrows():
        out.append(
            f'<tr><td><span class="dot {"men" if r.menWomen=="men" else "women"}"></span>{html.escape(r.brand)}</td>'
            f'<td class="nm">{html.escape(r["name"])}</td>'
            f'<td class="num">{r.maxHeightFront:.1f}&#8201;in</td></tr>')
    return ''.join(out)


# ---------------------------------------------------------------- full table
tbl = d.sort_values(['menWomen', 'maxHeightFront'], ascending=[True, False])
table_rows = []
for _, r in tbl.iterrows():
    cls = 'men-row' if r.menWomen == 'men' else 'women-row'
    table_rows.append(
        f'<tr class="{cls}"><td>{html.escape(r.brand.strip())}</td>'
        f'<td>{html.escape(r.style)}</td>'
        f'<td>{r.menWomen}</td>'
        f'<td class="nm">{html.escape(r["name"])}</td>'
        f'<td class="num">${r.price:g}</td>'
        f'<td class="num">{r.maxHeightFront:g}</td>'
        f'<td class="num">{r.minHeightFront:g}</td>'
        f'<td class="num">{r.maxHeightBack:g}</td>'
        f'<td class="num">{r.minHeightBack:g}</td>'
        f'<td class="num">{r.maxWidthFront:g}</td>'
        f'<td class="num">{r.maxWidthBack:g}</td></tr>')


def pct_drop():
    return (1 - front_mean['women'] / front_mean['men']) * 100

HTML = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pocket depth: jeans measured, men's vs women's</title>
<style>
  :root {{
    --bg: #f7f4ee; --card: #fffdf9; --ink: #20201d; --muted: #6f6a60;
    --line: #e2dbcf; --men: {MEN}; --women: {WOM};
  }}
  * {{ box-sizing: border-box; }}
  html {{ background: var(--bg); }}
  body {{
    margin: 0; color: var(--ink); background: var(--bg);
    font-family: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
    font-size: 17px; line-height: 1.6; -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 0 40px; }}
  header {{ padding: 74px 0 34px; border-bottom: 1px solid var(--line); }}
  .kicker {{
    font-family: ui-sans-serif, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 11.5px; letter-spacing: .19em; text-transform: uppercase;
    color: var(--women); font-weight: 700; margin-bottom: 18px;
  }}
  h1 {{ font-size: 50px; line-height: 1.08; margin: 0 0 18px; font-weight: 600; letter-spacing: -0.015em; max-width: 900px; }}
  .standfirst {{ font-size: 20.5px; line-height: 1.5; color: #3b3831; max-width: 790px; margin: 0; }}
  .byline {{
    font-family: ui-sans-serif, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    margin-top: 26px; font-size: 12.5px; color: var(--muted);
  }}
  .byline b {{ color: var(--ink); font-weight: 600; }}
  section {{ padding: 54px 0; border-bottom: 1px solid var(--line); }}
  h2 {{ font-size: 30px; line-height: 1.2; margin: 0 0 10px; font-weight: 600; letter-spacing: -0.01em; }}
  h2 .num {{
    font-family: ui-sans-serif, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 12px; color: var(--women); font-weight: 700; letter-spacing: .12em;
    display: block; margin-bottom: 8px;
  }}
  p {{ margin: 0 0 16px; }}
  .two {{ display: grid; grid-template-columns: 1.55fr 1fr; gap: 44px; align-items: center; }}
  .stack .txt {{ max-width: 750px; }}
  .stack .card {{ margin-top: 28px; }}
  .card {{
    background: var(--card); border: 1px solid var(--line); border-radius: 6px;
    padding: 22px 24px 16px; box-shadow: 0 1px 0 rgba(0,0,0,.02);
  }}
  .card h3 {{
    font-family: ui-sans-serif, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 12px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted);
    margin: 0 0 14px; font-weight: 600;
  }}
  .cap {{
    font-family: ui-sans-serif, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 12px; color: var(--muted); line-height: 1.5; margin: 10px 2px 0;
  }}
  .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 26px; padding: 44px 0 0; }}
  .stat {{ border-top: 2px solid var(--ink); padding-top: 14px; }}
  .stat .big {{ font-size: 44px; line-height: 1; font-weight: 600; letter-spacing: -0.02em; }}
  .stat .big small {{ font-size: 19px; font-weight: 400; color: var(--muted); letter-spacing: 0; }}
  .stat .lbl {{
    font-family: ui-sans-serif, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 12.5px; color: var(--muted); margin-top: 10px; line-height: 1.45;
  }}
  .w {{ color: var(--women); }}
  .m {{ color: var(--men); }}
  .num {{ font-variant-numeric: tabular-nums; }}
  table {{ width: 100%; border-collapse: collapse; font-family: ui-sans-serif, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 13px; }}
  th {{ text-align: left; font-weight: 600; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); border-bottom: 1px solid #b9b1a3; padding: 8px 8px; }}
  td {{ padding: 8px; border-bottom: 1px solid var(--line); }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.nm {{ color: #3b3831; }}
  .dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; vertical-align: 1px; }}
  .dot.men {{ background: var(--men); }}
  .dot.women {{ background: var(--women); }}
  .split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 40px; align-items: start; }}
  .note {{
    background: #efe9dd; border-left: 3px solid var(--women); padding: 16px 20px;
    font-size: 15.5px; color: #3b3831; border-radius: 0 4px 4px 0;
  }}
  .note p:last-child {{ margin-bottom: 0; }}
  details {{ margin-top: 8px; }}
  summary {{
    cursor: pointer; font-family: ui-sans-serif, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 13px; letter-spacing: .06em; text-transform: uppercase; color: var(--women);
    font-weight: 600; padding: 12px 0; outline: none;
  }}
  .scroll {{ max-height: 620px; overflow: auto; border: 1px solid var(--line); border-radius: 4px; background: var(--card); }}
  .scroll thead th {{ position: sticky; top: 0; background: #f2ece1; }}
  .men-row td:first-child {{ box-shadow: inset 3px 0 0 var(--men); }}
  .women-row td:first-child {{ box-shadow: inset 3px 0 0 var(--women); }}
  footer {{ padding: 40px 0 70px; color: var(--muted); font-family: ui-sans-serif, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 12.5px; }}
  footer p {{ margin: 0 0 8px; }}
  .src {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #3b3831; }}
  @media (max-width: 900px) {{
    .two, .two-rev, .split, .stats {{ grid-template-columns: 1fr; gap: 28px; }}
    h1 {{ font-size: 36px; }}
    .wrap {{ padding: 0 22px; }}
  }}
</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="kicker">Data report &middot; Tape-measure study</div>
  <h1>Pockets for him, pockets for her: 80 pairs of jeans, measured</h1>
  <p class="standfirst">A set of front- and back-pocket measurements taken from jeans sold by 21 popular brands finds a layout that is nearly identical at the back of the garment and strikingly different at the front: men's front pockets run about nine inches deeper than women's.</p>
  <div class="byline"><b>80 pairs</b> &middot; 40 men's, 40 women's &middot; 21 brands &middot; measurements in inches &middot; data file <span class="src">data/measurements.csv</span></div>
</header>

<div class="stats">
  <div class="stat">
    <div class="big num">{front_mean['men']:.1f}<small> in</small></div>
    <div class="lbl">average maximum front-pocket height on men's jeans</div>
  </div>
  <div class="stat">
    <div class="big num w">{front_mean['women']:.1f}<small> in</small></div>
    <div class="lbl">the same measure on women's jeans &mdash; {pct_drop():.0f}% shallower</div>
  </div>
  <div class="stat">
    <div class="big num">29<small> of 40</small></div>
    <div class="lbl">women's pairs whose front pocket is shorter than their own back pocket</div>
  </div>
</div>

<section>
  <div class="stack">
    <div class="txt">
      <h2><span class="num">01 / The gap</span>Front pockets shrink; back pockets don't</h2>
      <p>Measured four ways &mdash; maximum and minimum height of the front pocket, and of the back pocket &mdash; the two halves of the garment tell different stories. Across the 40 men's pairs the front pocket's maximum height averages <b class="num m">{front_mean['men']:.2f}&nbsp;in</b>; across the 40 women's pairs it averages <b class="num w">{front_mean['women']:.2f}&nbsp;in</b>.</p>
      <p>At the back the gap almost vanishes: <b class="num m">{back_mean['men']:.2f}&nbsp;in</b> for men against <b class="num w">{back_mean['women']:.2f}&nbsp;in</b> for women. The same is true of back-pocket width, {back_w['men']:.2f}&nbsp;in versus {back_w['women']:.2f}&nbsp;in.</p>
      <p>Front pockets also differ in width, but far less dramatically: {front_w['men']:.2f}&nbsp;in maximum width for men against {front_w['women']:.2f}&nbsp;in for women.</p>
    </div>
    <div class="card">
      <h3>Average pocket dimensions, inches</h3>
      {bar_chart()}
      <p class="cap">Front pockets are measured from the top edge; the data records a maximum and a minimum height for each pocket. Men's and women's back pockets are within an inch of each other on every measure.</p>
    </div>
  </div>
</section>

<section>
  <h2><span class="num">02 / Every pair</span>Two separate populations, not one spread</h2>
  <p>The averages could hide a wide overlap. They don't. Plotted pair by pair, the two groups barely touch: women's front pockets run from <span class="num">11.5</span> to <span class="num">21.5&nbsp;in</span> (median <span class="num">14.0</span>), men's from <span class="num">20.0</span> to <span class="num">28.0&nbsp;in</span> (median <span class="num">22.5</span>). Only one women's pair reaches 20&nbsp;in, and only two men's pairs fall below 21&nbsp;in.</p>
  <div class="card" style="margin-top:26px">
    <h3>Maximum front-pocket height, one dot per pair</h3>
    {strip_chart()}
    <p class="cap">Each dot is a pair of jeans. Dashed lines mark each group's median. Dots are nudged vertically only to stop them overlapping.</p>
  </div>
  <p style="margin-top:24px">A consequence of the pattern: in <b>29 of the 40</b> women's pairs the front pocket's maximum height is smaller than the back pocket's. Among men's pairs that never happens &mdash; <b>0 of 40</b>. Men's front pockets average <span class="num">1.44&times;</span> the height of their back pockets; women's average <span class="num">0.95&times;</span>, i.e. slightly less.</p>
</section>

<section>
  <h2><span class="num">03 / Explanations that fail</span>Not the cut, not the price</h2>
  <p>The obvious suspects are the garment's shape and its price. Neither explains the gap. Among women's jeans, skinny, straight and boot-cut pairs average <span class="num">14.27</span>, <span class="num">14.42</span> and <span class="num">14.25&nbsp;in</span> respectively &mdash; indistinguishable from one another and all far below the men's mean.</p>
  <div class="split" style="margin-top:26px">
    <div class="card">
      <h3>Women's jeans by style</h3>
      {style_chart()}
      <p class="cap">Average maximum front-pocket height. Styles are nearly identical; the men's average ({front_mean['men']:.1f}&nbsp;in) is off the scale of this chart.</p>
    </div>
    <div class="card">
      <h3>Price against pocket height</h3>
      {price_chart()}
      <p class="cap">Each dot is a pair; the horizontal axis is price on a log scale. Expensive jeans do not buy deeper front pockets.</p>
    </div>
  </div>
  <p style="margin-top:24px">The correlation between price and front-pocket height across all 80 pairs is <b class="num">&minus;0.08</b> &mdash; effectively none. A pair at $199 sits with 13&nbsp;in pockets; a pair at $9.99 is no worse off on this measure. Price tracks brand and fabric, not pocket geometry.</p>
</section>

<section>
  <h2><span class="num">04 / Brand by brand</span>The shortfall is industry-wide</h2>
  <p>Within women's jeans, the brand averages fan out from <span class="num">12.00&nbsp;in</span> at Guess and <span class="num">12.35&nbsp;in</span> at Levi's to <span class="num">19.75&nbsp;in</span> at Abercrombie. But even the most generous label in this sample stays below the men's average of {front_mean['men']:.2f}&nbsp;in, and most brands cluster between 13 and 15&nbsp;in.</p>
  <div class="card" style="margin-top:26px">
    <h3>Average maximum front-pocket height, women's jeans, by brand (inches)</h3>
    {brand_chart()}
    <p class="cap">Brands with a single women's pair in the dataset are shown as that pair's measurement. Guess and Levi's are highlighted as the lowest, Abercrombie as the highest.</p>
  </div>
</section>

<section>
  <h2><span class="num">05 / The extremes</span>The four shallowest pockets are all women's</h2>
  <p>At the shallow end sit Guess's Power Stretch Skinny and J.&nbsp;Crew's 8&Prime; Tooth Pick at <span class="num">11.5&nbsp;in</span>, followed by Calvin Klein's Midrise Skinny and Old Navy's Original Boot Cut at <span class="num">12.0&nbsp;in</span>. The deepest pockets are men's: Wrangler's Regular Fit (<span class="num">28.0&nbsp;in</span>) and Slim Fit (<span class="num">27.5&nbsp;in</span>), then True Religion's Geno Slim (<span class="num">26.2&nbsp;in</span>).</p>
  <div class="split" style="margin-top:26px">
    <div class="card">
      <h3>Five shallowest front pockets</h3>
      <table>
        <thead><tr><th>Brand</th><th>Pair</th><th style="text-align:right">Max height</th></tr></thead>
        <tbody>{rows_html(shallow)}</tbody>
      </table>
    </div>
    <div class="card">
      <h3>Four deepest front pockets</h3>
      <table>
        <thead><tr><th>Brand</th><th>Pair</th><th style="text-align:right">Max height</th></tr></thead>
        <tbody>{rows_html(deep)}</tbody>
      </table>
    </div>
  </div>
</section>

<section>
  <h2><span class="num">06 / Caveats</span>What these numbers can and cannot support</h2>
  <div class="note">
    <p><b>The height columns are not always ordered.</b> In 14 of the 80 pairs the recorded <i>maximum</i> front height is smaller than the recorded <i>minimum</i> front height (for example Lucky's Sweet Boot, 15.0 against 16.5). The two columns appear to come from two different measurement passes, so treat a single pair's numbers as approximate; the group averages are what carry the signal.</p>
    <p><b>Small, non-random sample.</b> Two to four pairs per brand, chosen by the original survey, not a random sample of what is on sale. Differences of a few tenths of an inch between brands or styles are noise.</p>
    <p><b>One surveyor's method.</b> Every measurement comes from the same protocol. That is good for comparisons within the data, but absolute values may not match a tape measure at home.</p>
  </div>
  <p style="margin-top:24px">There is also a flag column for a pocket <i>cutout</i>: six men's pairs and three women's pairs carry it. It is too rare, and too unevenly spread, to read as a pattern.</p>
</section>

<section style="border-bottom:none">
  <h2><span class="num">Appendix</span>All 80 pairs</h2>
  <p>Sorted by gender and then by maximum front-pocket height, deepest first. All heights and widths in inches.</p>
  <details open>
    <summary>Show the full measurement table</summary>
    <div class="scroll">
      <table>
        <thead>
          <tr><th>Brand</th><th>Style</th><th>Group</th><th>Pair</th><th style="text-align:right">Price</th>
          <th style="text-align:right">Front max h</th><th style="text-align:right">Front min h</th>
          <th style="text-align:right">Back max h</th><th style="text-align:right">Back min h</th>
          <th style="text-align:right">Front max w</th><th style="text-align:right">Back max w</th></tr>
        </thead>
        <tbody>{''.join(table_rows)}</tbody>
      </table>
    </div>
  </details>
</section>

<footer>
  <p><b>Source:</b> <span class="src">data/measurements.csv</span> &mdash; 80 rows, 16 columns: brand, style, men/women, product name, fabric, price, and ten pocket measurements (max/min height and width at front and back, plus front rivet height) and a cutout flag.</p>
  <p>Figures on this page are computed from that file; pocket heights are in inches as recorded. Chart axes share a common zero where bars are used.</p>
</footer>

</div>
</body>
</html>
'''

open('index.html', 'w').write(HTML)
print('written', len(HTML))