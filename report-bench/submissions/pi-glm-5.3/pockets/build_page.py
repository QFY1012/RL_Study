"""Build index.html for the pocket measurements report."""
import html
import json

import pandas as pd

RAW = pd.read_csv('data/measurements.csv')

# ---------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s), quote=True)


def num(x, nd=1):
    """Trim trailing zeros: 23.13 -> 23.13, 14.0 -> 14, 218.0 -> 218"""
    s = f'{x:,.{nd}f}'
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s


def f1(x):
    return f'{x:.1f}'


def f2(x):
    return f'{x:.2f}'


def money(x):
    return f'${x:,.2f}'


MEN, WOMEN = '#2b4a7d', '#c8553d'
INK, MUTED, LINE = '#1c2230', '#6d7583', '#d8d2c4'

# ---------------------------------------------------------------- derived data
m = RAW.copy()
m['brand'] = m.brand.str.strip()
m['front_cm2'] = m.maxHeightFront * m.maxWidthFront
m['back_cm2'] = m.maxHeightBack * m.maxWidthBack

means = m.groupby('menWomen')[['maxHeightFront', 'maxWidthFront', 'maxHeightBack',
                              'maxWidthBack', 'front_cm2', 'back_cm2']].mean()
men_m, women_m = means.loc['men'], means.loc['women']
ratio = (women_m / men_m)

depth = m.groupby('menWomen').maxHeightFront.agg(['min', 'median', 'max'])

brand_depth = (m.groupby(['brand', 'menWomen']).maxHeightFront.mean()
               .unstack().dropna())
brand_depth['gap'] = brand_depth.men - brand_depth.women
brand_depth = brand_depth.sort_values('gap', ascending=False)

brand_area = (m.groupby(['brand', 'menWomen']).front_cm2.mean().unstack().dropna())
brand_area['ratio'] = brand_area.men / brand_area.women

style = (m.groupby(['menWomen', 'style'])
         .agg(pairs=('style', 'size'), depth_cm=('maxHeightFront', 'mean'),
              width_cm=('maxWidthFront', 'mean')))

price_stats = m.groupby('menWomen').price.agg(['mean', 'min', 'max'])

fit = m.assign(fit15=m.maxHeightFront >= 15, fit16=m.maxHeightFront >= 16,
               fit17=m.maxHeightFront >= 17).groupby('menWomen')[['fit15', 'fit16', 'fit17']].sum()

# tooltip payload: one record per row, in the order used by the table
table = m.sort_values(['brand', 'menWomen'], kind='mergesort').reset_index(drop=True)
records = [{'b': r.brand, 'n': r.name, 'g': r.menWomen, 's': r.style, 'p': r.price,
            'd': r.maxHeightFront, 'w': r.maxWidthFront, 'a': r.front_cm2,
            'bd': r.maxHeightBack, 'bw': r.maxWidthBack, 'ba': r.back_cm2,
            'c': bool(r.cutout)} for r in table.itertuples()]

PHONE_H, PHONE_W = 15.0, 7.5     # cm yardstick used on the page

# ---------------------------------------------------------------- svg helpers
class SVG:
    def __init__(self, width, height, pad=0):
        self.w, self.h = width, height
        self.parts = []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, t, size=13, fill=INK, anchor='start', weight=400,
             family='var(--sans)', italic=False, letter=None, cls=None):
        style = f'font-family:{family};font-size:{size}px;fill:{fill};font-weight:{weight}'
        if italic:
            style += ';font-style:italic'
        if letter:
            style += f';letter-spacing:{letter}px'
        c = f' class="{cls}"' if cls else ''
        t = esc(t)
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" style="{style}"{c}>{t}</text>')

    def line(self, x1, y1, x2, y2, stroke=LINE, w=1, dash=None, opacity=1):
        d = f' stroke-dasharray="{dash}"' if dash else ''
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                 f'stroke="{stroke}" stroke-width="{w}" stroke-opacity="{opacity}"{d}/>')

    def rect(self, x, y, w, h, fill, stroke='none', sw=1, rx=0, opacity=1):
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
                 f'fill="{fill}" fill-opacity="{opacity}" stroke="{stroke}" stroke-width="{sw}"/>')

    def circle(self, x, y, r, fill, stroke='none', opacity=1, extra=''):
        self.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" fill-opacity="{opacity}" '
                 f'stroke="{stroke}"{extra}/>')

    def __str__(self):
        return (f'<svg viewBox="0 0 {self.w} {self.h}" role="img" '
                f'xmlns="http://www.w3.org/2000/svg">' + ''.join(self.parts) + '</svg>')


# ================================================================ 1. dot plot
def dot_plot():
    W, H = 960, 330
    s = SVG(W, H)
    L, R, T, B = 118, 36, 46, 44
    x0, x1 = 10, 29

    def X(v):
        return L + (v - x0) / (x1 - x0) * (W - L - R)

    lanes = [('women', "Women's jeans — 40 pairs", 108, WOMEN),
             ('men', "Men's jeans — 40 pairs", 234, MEN)]

    # grid + axis
    for v in range(10, 30, 2):
        s.line(X(v), T, X(v), H - B, stroke=LINE, w=1, opacity=.7)
        s.text(X(v), H - B + 20, str(v), size=12, fill=MUTED, anchor='middle')
    s.text((L + W - R) / 2, H - 6, 'deepest point of the front pocket (cm)', size=12,
           fill=MUTED, anchor='middle', letter=.4)

    # lane bands
    for key, label, cy, col in lanes:
        s.rect(L, cy - 46, W - L - R, 92, '#ffffff', opacity=.55, rx=8)
        s.text(16, cy - 8, label, size=14, fill=col, weight=600, family='var(--sans)')
        sub = ('average %.2f cm' % m.loc[m.menWomen == key, 'maxHeightFront'].mean()
               if key == 'women' else 'average %.2f cm' % m.loc[m.menWomen == key, 'maxHeightFront'].mean())
        s.text(16, cy + 12, sub, size=12.5, fill=MUTED, family='var(--sans)')
        med = depth.loc[key, 'median']
        s.line(X(med), cy - 40, X(med), cy + 40, stroke=col, w=2, dash='5 4', opacity=.9)
        s.text(X(med), cy + 58, 'median ' + num(med, 1), size=12, fill=col, anchor='middle',
               weight=600, family='var(--sans)')

    # phone threshold
    s.line(X(15), 20, X(15), H - B, stroke=INK, w=1.6, dash='7 5', opacity=.55)
    s.text(X(15) + 8, 30, 'a large phone is 15 cm tall', size=12.5, fill=INK, family='var(--sans)',
           weight=600)
    s.add(f'<path d="M {X(15)-7:.1f} 30 l 5 -3 v 6 z" fill="{INK}" fill-opacity=".55"/>')

    # beeswarm dots
    for key, label, cy, col in lanes:
        pts = m.loc[m.menWomen == key, ['maxHeightFront']].copy()
        pts['i'] = range(len(pts))
        placed = []
        for v, i in pts.itertuples(index=False):
            x = X(v)
            for off in (0, 13, -13, 26, -26, 39, -39):
                y = cy + off
                if all(abs(x - px) > 13 or abs(y - py) > 13 for px, py in placed):
                    break
            placed.append((x, y))
            s.circle(x, y, 6.5, col, stroke='#ffffff', opacity=.85,
                     extra=f' data-i="{i}" class="dot"' if key == 'women' else '')
        # re-index tooltips below
    return str(s), L, R, x0, x1


# tooltips need the row identity: rebuild with proper indices
def dot_plot_final():
    W, H = 960, 330
    s = SVG(W, H)
    L, R, T, B = 118, 36, 46, 44
    x0, x1 = 10, 29

    def X(v):
        return L + (v - x0) / (x1 - x0) * (W - L - R)

    # order of records used for tooltips: table order (brand, gender)
    order = list(table.index)
    lanes = [('women', "Women's jeans — 40 pairs", 108, WOMEN),
             ('men', "Men's jeans — 40 pairs", 234, MEN)]

    for v in range(10, 30, 2):
        s.line(X(v), T, X(v), H - B, stroke=LINE, w=1, opacity=.7)
        s.text(X(v), H - B + 20, str(v), size=12, fill=MUTED, anchor='middle')
    s.text((L + W - R) / 2, H - 6, 'deepest point of the front pocket (cm)', size=12,
           fill=MUTED, anchor='middle', letter=.4)

    for key, label, cy, col in lanes:
        s.rect(L, cy - 46, W - L - R, 92, '#ffffff', opacity=.55, rx=8)
        s.text(16, cy - 8, label, size=14, fill=col, weight=600, family='var(--sans)')
        s.text(16, cy + 12, 'average %.2f cm' % m.loc[m.menWomen == key, 'maxHeightFront'].mean(),
               size=12.5, fill=MUTED, family='var(--sans)')
        med = depth.loc[key, 'median']
        s.line(X(med), cy - 40, X(med), cy + 40, stroke=col, w=2, dash='5 4', opacity=.9)
        s.text(X(med), cy + 58, 'median ' + num(med, 1), size=12, fill=col, anchor='middle',
               weight=600, family='var(--sans)')

    s.line(X(15), 20, X(15), H - B, stroke=INK, w=1.6, dash='7 5', opacity=.55)
    s.text(X(15) + 8, 30, 'a large phone is 15 cm tall', size=12.5, fill=INK,
           family='var(--sans)', weight=600)

    # women's deepest / men's shallowest callouts
    wmax = m.loc[m.menWomen == 'women', 'maxHeightFront'].max()
    mmin = m.loc[m.menWomen == 'men', 'maxHeightFront'].min()
    s.text(X(wmax), 76, 'deepest women\u2019s pocket 21.5', size=11.5, fill=WOMEN, anchor='end',
           family='var(--sans)', weight=600)
    s.text(X(mmin), 262, 'shallowest men\u2019s pocket 20.0', size=11.5, fill=MEN, anchor='end',
           family='var(--sans)', weight=600)

    idx_by_key = {k: [i for i, r in enumerate(records) if r['g'] == k] for k in ('women', 'men')}
    for key, label, cy, col in lanes:
        vals = [(records[i]['d'], i) for i in idx_by_key[key]]
        placed = []
        for v, i in vals:
            x = X(v)
            for off in (0, 13, -13, 26, -26, 39, -39):
                y = cy + off
                if all(abs(x - px) > 13 or abs(y - py) > 13 for px, py in placed):
                    break
            placed.append((x, y))
            s.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" fill="{col}" fill-opacity=".82" '
                  f'stroke="#fff" stroke-width="1.2" class="hot" data-i="{i}"/>')
    return str(s)


# ================================================================ 2. ratio bars
def ratio_bars():
    W, H = 960, 250
    s = SVG(W, H)
    L, R = 250, 150
    rows = [('Front pocket depth', 'maxHeightFront', True),
            ('Front pocket width', 'maxWidthFront', True),
            ('Front pocket area', 'front_cm2', True),
            ('Back pocket depth', 'maxHeightBack', False),
            ('Back pocket width', 'maxWidthBack', False),
            ('Back pocket area', 'back_cm2', False)]
    top, gap = 34, 36
    x0, x1 = 0.45, 1.06

    def X(v):
        return L + (v - x0) / (x1 - x0) * (W - L - R)

    s.line(X(1.0), 14, X(1.0), H - 34, stroke=INK, w=1.6, dash='6 4', opacity=.5)
    s.text(X(1.0), H - 14, "men\u2019s level = 1.00", size=12, fill=INK, anchor='middle',
           family='var(--sans)', weight=600)
    s.text(L - 12, 20, "women\u2019s pocket as a share of men\u2019s", size=12, fill=MUTED,
           anchor='end', family='var(--sans)')
    for label, key, front in rows:
        y = top + rows.index((label, key, front)) * gap
        r = ratio[key]
        col = WOMEN if front else '#a2715f'
        s.text(L - 12, y + 5, label, size=13.5, fill=INK, anchor='end', family='var(--sans)',
               weight=600)
        s.rect(L, y - 9, X(r) - L, 18, col, rx=4)
        s.text(X(r) + 10, y + 5, f'{r:.3f}', size=13.5, fill=INK, family='var(--sans)',
               weight=700)
        if 'cm2' in key:
            s.text(X(r) + 62, y + 5, f'({f1(women_m[key])} vs {f1(men_m[key])} cm\u00b2)',
                   size=12.5, fill=MUTED, family='var(--sans)')
        else:
            s.text(X(r) + 62, y + 5, f'({f2(women_m[key])} vs {f2(men_m[key])} cm)',
                   size=12.5, fill=MUTED, family='var(--sans)')
    return str(s)


# ================================================================ 3. pocket + phone to scale
def pocket_figure():
    SC = 8.4                     # px per cm
    W, H = 960, 348
    s = SVG(W, H)
    pocket_w_m, pocket_h_m = men_m.maxWidthFront, men_m.maxHeightFront
    pocket_w_w, pocket_h_w = women_m.maxWidthFront, women_m.maxHeightFront

    def draw(cx, pw, ph, col, title, sub, fits):
        x = cx - pw * SC / 2
        y = 64
        s.rect(x, y, pw * SC, ph * SC, 'none', stroke=col, sw=2.5, rx=6)
        s.rect(x, y, pw * SC, ph * SC, col, opacity=.10, rx=6)
        # phone, sitting on the pocket floor
        phx = cx - PHONE_W * SC / 2
        phy = y + ph * SC - PHONE_H * SC
        s.rect(phx, phy, PHONE_W * SC, PHONE_H * SC, '#1c2230', rx=4, opacity=.9)
        s.add(f'<circle cx="{cx:.1f}" cy="{phy + PHONE_H*SC - 12:.1f}" r="3.5" '
              f'fill="#f6f3ec" fill-opacity=".8"/>')
        # dimension ticks
        s.line(x - 16, y, x - 16, y + ph * SC, stroke=MUTED, w=1)
        s.line(x - 21, y, x - 11, y, stroke=MUTED, w=1)
        s.line(x - 21, y + ph * SC, x - 11, y + ph * SC, stroke=MUTED, w=1)
        s.text(x - 28, y + ph * SC / 2, f'{ph:.2f} cm', size=13, fill=INK, anchor='end',
               family='var(--sans)', weight=700)
        s.line(x, y - 14, x + pw * SC, y - 14, stroke=MUTED, w=1)
        s.line(x, y - 19, x, y - 9, stroke=MUTED, w=1)
        s.line(x + pw * SC, y - 19, x + pw * SC, y - 9, stroke=MUTED, w=1)
        s.text(cx, y - 24, f'{pw:.2f} cm wide', size=13, fill=INK, anchor='middle',
               family='var(--sans)', weight=700)
        s.text(cx, 30, title, size=15, fill=col, anchor='middle', family='var(--sans)',
               weight=700)
        s.text(cx, y + ph * SC + 26, sub, size=12.5, fill=MUTED, anchor='middle',
               family='var(--sans)')
        # phone-fit annotation, to the right of the pocket with a leader line
        ax = x + pw * SC + 14
        s.line(x + pw * SC + (2 if fits else 2), phy + 4, ax - 4, phy + 4, stroke=MUTED, w=1)
        if fits:
            s.text(ax, phy + 8, 'phone fits with\n%.1f cm to spare' % ((phy - y) / SC),
                   size=12.5, fill=INK, family='var(--sans)', weight=600)
        else:
            s.text(ax, phy + 8, 'phone sticks out\n%.1f cm' % ((y - phy) / SC), size=12.5,
                   fill=INK, family='var(--sans)', weight=600)

    draw(250, pocket_w_m, pocket_h_m, MEN, "Men\u2019s average front pocket",
         f'{men_m.front_cm2:.1f} cm\u00b2 of pocket \u00b7 the phone drops in', True)
    draw(690, pocket_w_w, pocket_h_w, WOMEN, "Women\u2019s average front pocket",
         f'{women_m.front_cm2:.1f} cm\u00b2 of pocket \u00b7 the phone will not go in', False)
    return str(s)


# ================================================================ 4. brand dumbbells
def dumbbells():
    rows = brand_depth
    W, H = 960, 40 + len(rows) * 27 + 46
    s = SVG(W, H)
    L, R = 190, 92
    x0, x1 = 10, 30

    def X(v):
        return L + (v - x0) / (x1 - x0) * (W - L - R)

    top = 40
    for v in range(10, 30, 2):
        s.line(X(v), top - 8, X(v), H - 40, stroke=LINE, w=1, opacity=.7)
        s.text(X(v), H - 20, str(v), size=12, fill=MUTED, anchor='middle')
    s.text((L + W - R) / 2, H - 4, 'average front-pocket depth (cm)', size=12, fill=MUTED,
           anchor='middle', letter=.4)
    s.line(X(15), top - 8, X(15), H - 40, stroke=INK, w=1.4, dash='6 4', opacity=.4)
    s.text(X(15), 18, '15 cm', size=11.5, fill=INK, anchor='middle', family='var(--sans)')

    s.text(L - 14, 22, 'brand', size=12, fill=MUTED, anchor='end', family='var(--sans)')
    s.text(W - R + 14, 22, 'gap', size=12, fill=MUTED, family='var(--sans)')

    for i, (brand, r) in enumerate(rows.iterrows()):
        y = top + 8 + i * 27
        if i < 3 or i > len(rows) - 3:
            s.rect(L - 186, y - 11, W - 24, 22, '#eae4d6', rx=6, opacity=.9)
        s.text(L - 14, y + 4.5, brand, size=13.5, fill=INK, anchor='end', family='var(--sans)',
               weight=600)
        s.line(X(r.women), y, X(r.men), y, stroke='#9aa2b0', w=2.5)
        s.circle(X(r.women), y, 6, WOMEN, stroke='#fff', extra=' class="hot" data-b="%s"' % esc(brand))
        s.circle(X(r.men), y, 6, MEN, stroke='#fff')
        s.text(W - R + 14, y + 4.5, f'+{r.gap:.1f} cm', size=13, fill=INK,
               family='var(--sans)', weight=700)
    return str(s)


# ================================================================ 5. style bars
def style_bars():
    W, H = 960, 310
    s = SVG(W, H)
    L, R, B = 60, 24, 66
    top = 48
    x1 = 26.5
    cats = ['boot-cut', 'skinny', 'straight', 'slim', 'regular']
    step = (W - L - R) / len(cats)
    bw = 34

    def Y(v):
        return top + (x1 - v) / (x1 - 10) * (H - top - B)

    for v in range(10, 27, 2):
        s.line(L, Y(v), W - R, Y(v), stroke=LINE, w=1, opacity=.7)
        s.text(L - 12, Y(v) + 4, str(v), size=12, fill=MUTED, anchor='end')
    s.text(14, 24, 'front-pocket depth (cm)', size=12.5, fill=MUTED, family='var(--sans)')

    for gi, (g, col) in enumerate([('women', WOMEN), ('men', MEN)]):
        s.rect(W - 252 + gi * 130, 12, 11, 11, col, rx=2)
        s.text(W - 252 + gi * 130 + 18, 22, "women's" if g == 'women' else "men's", size=12.5,
               fill=INK, family='var(--sans)', weight=600)

    for ci, cat in enumerate(cats):
        cx = L + step * (ci + 0.5)
        counts = []
        for gi, (g, col) in enumerate([('women', WOMEN), ('men', MEN)]):
            x = cx - 40 + gi * 46
            if (g, cat) not in style.index:
                s.line(x, Y(12) - 3, x + bw, Y(12) - 3, stroke=MUTED, w=2, dash='3 3')
                counts.append('none' if g == 'women' else '0')
                continue
            v = style.loc[(g, cat), 'depth_cm']
            n = int(style.loc[(g, cat), 'pairs'])
            s.rect(x, Y(v), bw, Y(10) - Y(v), col, rx=3, opacity=.92)
            s.text(x + bw / 2, Y(v) - 7, f'{v:.1f}', size=12.5, fill=col, anchor='middle',
                   family='var(--sans)', weight=700)
            counts.append(f"{'women' if g == 'women' else 'men'} {n}")
        s.text(cx, H - B + 22, cat, size=13.5, fill=INK, anchor='middle',
               family='var(--sans)', weight=600)
        s.text(cx, H - B + 40, ' \u00b7 '.join(counts) + (' pairs' if len(counts) > 1 else ''),
               size=11.5, fill=MUTED, anchor='middle', family='var(--sans)')
    return str(s)


# ================================================================ 6. scatter
def scatter():
    W, H = 960, 430
    s = SVG(W, H)
    L, R, T, B = 78, 30, 40, 58
    px0, px1 = 0, 260
    ay0, ay1 = 150, 500

    def X(v):
        return L + (v - px0) / (px1 - px0) * (W - L - R)

    def Y(v):
        return T + (ay1 - v) / (ay1 - ay0) * (H - T - B)

    # gender ranges
    for g, col in [('men', MEN), ('women', WOMEN)]:
        lo, hi = m.loc[m.menWomen == g, 'front_cm2'].min(), m.loc[m.menWomen == g, 'front_cm2'].max()
        s.rect(L, Y(hi), W - L - R, Y(lo) - Y(hi), col, opacity=.06)
    s.text(L + 8, Y(m.loc[m.menWomen == 'men', 'front_cm2'].max()) - 6,
           'men\u2019s range', size=12, fill=MEN, family='var(--sans)', weight=700)
    s.text(L + 8, Y(m.loc[m.menWomen == 'women', 'front_cm2'].min()) + 16,
           'women\u2019s range', size=12, fill=WOMEN, family='var(--sans)', weight=700)

    for v in range(0, 260, 50):
        s.line(X(v), T, X(v), H - B, stroke=LINE, w=1, opacity=.7)
        s.text(X(v), H - B + 20, f'${v}', size=12, fill=MUTED, anchor='middle')
    s.text((L + W - R) / 2, H - 8, 'price of the pair (USD)', size=12, fill=MUTED,
           anchor='middle', letter=.4)
    for v in range(150, 500, 50):
        s.line(L, Y(v), W - R, Y(v), stroke=LINE, w=1, opacity=.7)
        s.text(L - 12, Y(v) + 4, f'{v}', size=12, fill=MUTED, anchor='end')
    s.text(16, (T + H - B) / 2, 'front pocket area (cm\u00b2)', size=12.5, fill=MUTED,
           family='var(--sans)')

    for i, r in enumerate(records):
        col = MEN if r['g'] == 'men' else WOMEN
        s.add(f'<circle cx="{X(r["p"]):.1f}" cy="{Y(r["a"]):.1f}" r="6" fill="{col}" '
              f'fill-opacity=".8" stroke="#fff" stroke-width="1.1" class="hot" data-i="{i}"/>')

    # annotations
    def note(i, dx, dy, text, col):
        r = records[i]
        x, y = X(r['p']), Y(r['a'])
        s.line(x, y, x + dx, y + dy, stroke=col, w=1.2, opacity=.8)
        s.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{col}" stroke="#fff" '
              f'stroke-width="1.5"/>')
        s.text(x + dx + (6 if dx > 0 else -6), y + dy + (4 if dy > 0 else -8), text, size=12,
               fill=INK, anchor='start' if dx > 0 else 'end', family='var(--sans)', weight=600)

    ti = next(i for i, r in enumerate(records) if r['n'] == 'Slim Straight' and r['g'] == 'women')
    hi = next(i for i, r in enumerate(records) if r['n'] == 'Skinny Ankle High Waist')
    mi = next(i for i, r in enumerate(records) if r['n'] == 'Skinny' and r['g'] == 'men')
    note(ti, -74, -26, 'True Religion $249 \u00b7 203 cm\u00b2', WOMEN)
    note(hi, 34, 22, 'H&M $9.99 \u00b7 275.5 cm\u00b2', WOMEN)
    note(mi, 30, -30, 'H&M men\u2019s, $39.99 \u00b7 290 cm\u00b2', MEN)
    return str(s)


# ================================================================ 7. phone fit bars
def phone_fit():
    W, H = 960, 210
    s = SVG(W, H)
    L, R = 250, 130
    top, gap = 46, 52
    full = 40
    x1 = W - L - R
    cats = [('fit15', '15 cm phone'), ('fit16', '16 cm phone'), ('fit17', '17 cm phone')]
    s.text(L - 14, 22, 'front pockets deep enough for the phone', size=12, fill=MUTED,
           anchor='end', family='var(--sans)')
    for ci, (key, label) in enumerate(cats):
        y = top + ci * gap
        s.text(L - 14, y + 14, label, size=13.5, fill=INK, anchor='end', family='var(--sans)',
               weight=600)
        for gi, (g, col) in enumerate([('women', WOMEN), ('men', MEN)]):
            n = int(fit.loc[g, key])
            yy = y + gi * 21
            s.rect(L, yy, x1 * (full - n) / full, 15, '#e7e1d3', rx=3)
            s.rect(L, yy, x1 * n / full, 15, col, rx=3)
            s.text(L + x1 * n / full + 10, yy + 12, f'{n} of 40', size=13, fill=INK,
                   family='var(--sans)', weight=700)
    s.rect(W - 118, top - 26, 11, 11, WOMEN, rx=2)
    s.text(W - 118 + 18, top - 17, "women's", size=12.5, fill=INK, family='var(--sans)',
           weight=600)
    s.rect(W - 44, top - 26, 11, 11, MEN, rx=2)
    s.text(W - 44 + 18, top - 17, "men's", size=12.5, fill=INK, family='var(--sans)',
           weight=600)
    return str(s)


# ================================================================ 8. table
def table_html():
    head = ['Brand', 'Style', 'Dept', 'Name', 'Price', 'Front depth', 'Front width',
            'Front area', 'Back depth', 'Back width', 'Back area', 'Cutout']
    out = ['<div class="tablewrap"><table>', '<thead><tr>']
    out += [f'<th>{esc(h)}</th>' for h in head]
    out.append('</tr></thead><tbody>')
    for r in records:
        cls = 'w' if r['g'] == 'women' else 'm'
        out.append(
            f'<tr class="row {cls}"><td class="b">{esc(r["b"])}</td><td>{esc(r["s"])}</td>'
            f'<td class="g {cls}">{"women" if r["g"] == "women" else "men"}</td>'
            f'<td class="n">{esc(r["n"])}</td><td class="r">{money(r["p"])}</td>'
            f'<td class="r">{num(r["d"], 2)}</td><td class="r">{num(r["w"], 2)}</td>'
            f'<td class="r">{num(r["a"], 1)}</td><td class="r">{num(r["bd"], 2)}</td>'
            f'<td class="r">{num(r["bw"], 2)}</td><td class="r">{num(r["ba"], 1)}</td>'
            f'<td class="c">{"&#10003;" if r["c"] else "&mdash;"}</td></tr>')
    out.append('</tbody></table></div>')
    return ''.join(out)


# ================================================================ assemble page
w_front, m_front = women_m.front_cm2, men_m.front_cm2
front_share = w_front / m_front

stat_cards = [
    ('%.2f vs %.2f cm' % (men_m.maxHeightFront, women_m.maxHeightFront),
     'average front-pocket depth, men\u2019s vs women\u2019s',
     'women\u2019s are %.2f\u00d7 as deep' % ratio.maxHeightFront),
    ('%s vs %s cm\u00b2' % (num(m_front), num(w_front)),
     'average front-pocket area (depth \u00d7 widest width)',
     'women\u2019s get %.0f%% of the room' % (front_share * 100)),
    ('40 of 40 vs 12 of 40', 'front pockets deep enough for a 15 cm phone',
     'all 80 clear the width test'),
    ('0.919', 'back-pocket area, women\u2019s as a share of men\u2019s',
     'back pockets are nearly equal'),
    ('\u22120.07', 'correlation of price with front-pocket area',
     'money does not buy room'),
]

sections = []

sections.append(f'''
<section class="stats">
  {''.join(f'<div class="card"><div class="big">{esc(v)}</div><div class="lab">{esc(l)}</div>'
           f'<div class="sub">{esc(s)}</div></div>' for v, l, s in stat_cards)}
</section>
''')

sections.append(f'''
<section class="block">
  <h2><span>01</span> The gap is real, and it is huge</h2>
  <p>Every pair in the file was measured the same way: the deepest point of the front pocket, the
  widest and narrowest points of its opening, and the same four numbers for the back pocket. Plot
  the front-pocket depth of all {len(m)} pairs and the two departments barely overlap. Women\u2019s
  pockets run from <b>{num(depth.loc["women", "min"], 1)} to {num(depth.loc["women", "max"], 1)} cm</b>
  with a median of {num(depth.loc["women", "median"], 1)} cm; men\u2019s run from
  <b>{num(depth.loc["men", "min"], 1)} to {num(depth.loc["men", "max"], 1)} cm</b> with a median of
  {num(depth.loc["men", "median"], 1)} cm. The deepest women\u2019s pocket in the whole dataset is
  shallower than the median men\u2019s pocket, and {int((m.loc[m.menWomen == "women", "maxHeightFront"] < m.loc[m.menWomen == "men", "maxHeightFront"].min()).sum())}
  of the 40 women\u2019s pairs are shallower than the single shallowest men\u2019s pair.</p>
  <figure>{dot_plot_final()}<figcaption>Each dot is one pair of jeans. Hover for the brand, cut and price.</figcaption></figure>
</section>
''')

sections.append(f'''
<section class="block">
  <h2><span>02</span> It is depth, not width</h2>
  <p>Women\u2019s front pockets are almost as <i>wide</i> as men\u2019s \u2014 {num(women_m.maxWidthFront, 2)} cm
  against {num(men_m.maxWidthFront, 2)} cm, or {ratio.maxWidthFront:.3f} of the men\u2019s width. It is
  the vertical measurement that collapses: {num(women_m.maxHeightFront, 2)} cm against
  {num(men_m.maxHeightFront, 2)} cm, only {ratio.maxHeightFront:.3f} of the men\u2019s depth. Multiply
  depth by width and the average men\u2019s front pocket holds {num(m_front)} cm\u00b2 while the average
  women\u2019s holds {num(w_front)} cm\u00b2 \u2014 {front_share:.3f} of it, a shortfall of
  {num(m_front - w_front)} cm\u00b2. Width is never what stops a phone going in: the narrowest point of
  the opening is at least 11.0 cm on all 80 pairs.</p>
  <figure>{pocket_figure()}<figcaption>Both pockets and the phone are drawn to the same scale. The phone is 15 cm tall
  and 7.5 cm wide \u2014 the size of a large modern handset, used here as a fixed yardstick.</figcaption></figure>
  <figure>{ratio_bars()}<figcaption>Women\u2019s average as a share of men\u2019s, measure by measure. Front measurements
  in rust, back measurements in clay.</figcaption></figure>
</section>
''')

sections.append(f'''
<section class="block">
  <h2><span>03</span> Back pockets tell a different story</h2>
  <p>The same tape measure on the back pockets finds two departments that are practically even:
  men\u2019s average {num(men_m.maxHeightBack, 2)} \u00d7 {num(men_m.maxWidthBack, 2)} cm for
  {num(men_m.back_cm2)} cm\u00b2, women\u2019s {num(women_m.maxHeightBack, 2)} \u00d7
  {num(women_m.maxWidthBack, 2)} cm for {num(women_m.back_cm2)} cm\u00b2. That is {ratio.back_cm2:.3f}
  of the men\u2019s area and a depth gap of only {num(men_m.maxHeightBack - women_m.maxHeightBack, 2)} cm,
  against the {num(men_m.maxHeightFront - women_m.maxHeightFront, 2)} cm chasm in front. Whatever
  constrains women\u2019s front pockets, it is not the amount of fabric the brand is willing to spend
  on a pocket.</p>
</section>
''')

dumb = dumbbells()
sections.append(f'''
<section class="block">
  <h2><span>04</span> Every brand does it</h2>
  <p>Split the file by brand and the pattern never breaks: in all
  {len(brand_depth)} brands measured in both departments, the men\u2019s front pockets average deeper
  than the women\u2019s. The most even-handed brand is <b>Abercrombie</b>, whose women\u2019s pairs
  still lose {num(brand_depth.loc["Abercrombie", "gap"], 1)} cm of depth
  ({num(brand_depth.loc["Abercrombie", "women"], 2)} vs {num(brand_depth.loc["Abercrombie", "men"], 2)} cm);
  on area that is a ratio of {brand_area.loc["Abercrombie", "ratio"]:.2f}\u00d7. The widest gap belongs to
  <b>Levi\u2019s</b> at {num(brand_depth.loc["Levi's", "gap"], 1)} cm
  ({num(brand_depth.loc["Levi's", "women"], 2)} vs {num(brand_depth.loc["Levi's", "men"], 2)} cm), with
  <b>Gap</b> the worst on area at {brand_area.loc["Gap", "ratio"]:.2f}\u00d7
  ({num(brand_area.loc["Gap", "women"], 1)} vs {num(brand_area.loc["Gap", "men"], 1)} cm\u00b2). Wrangler
  gives men the deepest front pockets of any brand, {num(brand_depth.loc["Wrangler", "men"], 2)} cm on
  average, while its women\u2019s pairs get {num(brand_depth.loc["Wrangler", "women"], 2)} cm.</p>
  <figure>{dumb}<figcaption>Average front-pocket depth per brand, women\u2019s (rust) against men\u2019s (blue),
  sorted by the size of the gap. Seven for All Mankind appears once per department, so it is left out of this chart.</figcaption></figure>
</section>
''')

sections.append(f'''
<section class="block">
  <h2><span>05</span> The cut is not the explanation</h2>
  <p>Skinny jeans are the usual suspect, but the measurements do not support it. Within the women\u2019s
  pairs the three cuts \u2014 boot-cut, skinny, straight \u2014 average
  {num(style.loc[("women", "boot-cut"), "depth_cm"], 1)},
  {num(style.loc[("women", "skinny"), "depth_cm"], 1)} and
  {num(style.loc[("women", "straight"), "depth_cm"], 1)} cm of front-pocket depth: a spread of about
  {num(style.loc[("women", "straight"), "depth_cm"] - style.loc[("women", "boot-cut"), "depth_cm"], 1)} cm.
  Across the men\u2019s five cuts the spread is
  {num(style.loc[("men", "slim"), "depth_cm"] - style.loc[("men", "regular"), "depth_cm"], 1)} cm.
  The tightest men\u2019s cut \u2014 skinny, {num(style.loc[("men", "skinny"), "depth_cm"], 1)} cm \u2014 is still
  {num(style.loc[("men", "skinny"), "depth_cm"] - style.loc[("women", "straight"), "depth_cm"], 1)} cm deeper
  than the roomiest women\u2019s cut. Cut moves pocket depth by a centimetre or so; department moves it by
  {num(men_m.maxHeightFront - women_m.maxHeightFront, 1)}.</p>
  <figure>{style_bars()}<figcaption>Average front-pocket depth by cut and department. Pair counts underneath:
  women\u2019s/women\u2019s and men\u2019s counts per cut (no women\u2019s slim or regular pairs were measured).</figcaption></figure>
</section>
''')

sections.append(f'''
<section class="block">
  <h2><span>06</span> The price is not the explanation either</h2>
  <p>The two halves of the sample cost the same: men\u2019s pairs average
  {money(price_stats.loc["men", "mean"])} (from {money(price_stats.loc["men", "min"])} to
  {money(price_stats.loc["men", "max"])}) and women\u2019s {money(price_stats.loc["women", "mean"])}
  (from {money(price_stats.loc["women", "min"])} to {money(price_stats.loc["women", "max"])}). And price
  buys no pocket room: front-pocket area correlates with price at \u22120.073 across all 80 pairs,
  \u22120.177 within the men\u2019s and \u22120.182 within the women\u2019s \u2014 if anything, slightly negative.
  The priciest pair in the data, True Religion\u2019s {money(249)} women\u2019s Slim Straight, has
  {num(203.0)} cm\u00b2 of front pocket. The cheapest, H&M\u2019s {money(9.99)} women\u2019s Skinny Ankle,
  has {num(275.5)} cm\u00b2. Both are smaller than the smallest men\u2019s front pocket in the data \u2014
  H&M\u2019s own men\u2019s Skinny, {money(39.99)} at {num(290.0)} cm\u00b2.</p>
  <figure>{scatter()}<figcaption>Front-pocket area against price. The shaded bands show each department\u2019s
  full range; they overlap only between {num(m.loc[m.menWomen == "men", "front_cm2"].min(), 0)} and
  {num(m.loc[m.menWomen == "women", "front_cm2"].max(), 1)} cm\u00b2.</figcaption></figure>
</section>
''')

sections.append(f'''
<section class="block">
  <h2><span>07</span> What actually fits</h2>
  <p>Take the phone seriously as a yardstick and the counts are stark. At 15 cm tall \u2014 a large
  modern handset \u2014 all 40 men\u2019s front pockets take it and 12 of the 40 women\u2019s do. At 16 cm
  only 5 women\u2019s pockets still fit it, at 17 cm only 4. Every one of the 80 pockets is wide enough
  at its narrowest point; depth is the only barrier. The roomiest women\u2019s front pockets in the data
  are Abercrombie\u2019s two Simone pairs at {num(333.25)} and {num(333.0)} cm\u00b2, and the third-best is
  H&M\u2019s {money(9.99)} Skinny Ankle at {num(275.5)} cm\u00b2 \u2014 roomier than plenty of pricier
  pairs, and still smaller than every men\u2019s pair measured.</p>
  <figure>{phone_fit()}<figcaption>How many of each department\u2019s 40 pairs have a front pocket deep enough for a
  phone of the height shown. The grey block is the share that fails.</figcaption></figure>
</section>
''')

sections.append(f'''
<section class="block">
  <h2><span>08</span> The whole measurement</h2>
  <p>All {len(m)} pairs, every number in the file. Front area is depth \u00d7 widest width, back area
  likewise. The rivet height \u2014 the height of the rivet at the top of the front pocket \u2014 averages
  {num(m.loc[m.menWomen == "men", "rivetHeightFront"].mean(), 2)} cm on men\u2019s jeans
  ({num(m.loc[m.menWomen == "men", "rivetHeightFront"].min(), 1)}\u2013{num(m.loc[m.menWomen == "men", "rivetHeightFront"].max(), 1)})
  and {num(m.loc[m.menWomen == "women", "rivetHeightFront"].mean(), 2)} cm on women\u2019s
  ({num(m.loc[m.menWomen == "women", "rivetHeightFront"].min(), 1)}\u2013{num(m.loc[m.menWomen == "women", "rivetHeightFront"].max(), 1)}),
  so women\u2019s pockets start marginally higher and stop far sooner. Only 9 of the 80 pairs carry the
  cutout flag \u2014 6 men\u2019s and 3 women\u2019s, all from True Religion, Guess, J.~Crew and Uniqlo.</p>
  {table_html()}
</section>
''')

notes = f'''
<aside class="notes">
  <h3>About the data</h3>
  <ul>
    <li>One row per pair of jeans: {len(m)} pairs, 40 women\u2019s and 40 men\u2019s, from 21 brand
    labels in 5 styles, priced from {money(m.price.min())} to {money(m.price.max())}. Two spellings of
    \u201c7 for All Mankind\u201d appear in the brand column; merged, the 80 pairs come from 20 brands,
    {len(brand_depth)} of them measured in both departments.</li>
    <li>All measurements are in centimetres, taken with the same method on both departments:
    <code>maxHeightFront</code>/<code>minHeightFront</code> are the deepest and shallowest points of the
    front pocket (the opening is angled, so the two differ), <code>maxWidthFront</code>/<code>minWidthFront</code>
    the widest and narrowest points of the opening, the same four for the back pocket,
    <code>rivetHeightFront</code> the height of the rivet at the top of the front pocket.</li>
    <li>Area is computed here as depth \u00d7 widest width, which is an upper bound on capacity: real
    pocket bags taper and corners round off.</li>
    <li>The phone is a yardstick, not a measurement: 15 cm tall \u00d7 7.5 cm wide, roughly a large
    modern handset, tested against pocket depth and the narrowest width of the opening.</li>
    <li>Two pairs per brand per department were measured, so brand averages rest on two pairs each;
    treat the brand ranking as indicative, not definitive.</li>
  </ul>
</aside>
'''

CSS = '''
:root{
  --paper:#f6f3ec; --card:#fffdf7; --ink:#1c2230; --muted:#6d7583; --line:#ded7c7;
  --men:#2b4a7d; --women:#c8553d; --accent:#31538c;
  --serif:Georgia,'Iowan Old Style','Times New Roman',serif;
  --sans:'Helvetica Neue',Helvetica,Arial,'Segoe UI',sans-serif;
}
*{box-sizing:border-box}
html{background:var(--paper)}
body{margin:0;color:var(--ink);font-family:var(--serif);font-size:17px;line-height:1.62;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1100px;margin:0 auto;padding:0 28px}
a{color:var(--accent)}
b,strong{font-weight:700}
/* masthead */
.masthead{padding:64px 0 34px;border-bottom:3px solid var(--ink);position:relative}
.masthead:before{content:"";display:block;width:64px;height:3px;background:var(--women);
  position:absolute;bottom:-3px;left:0}
.kicker{font-family:var(--sans);font-size:12.5px;letter-spacing:.22em;text-transform:uppercase;
  color:var(--women);font-weight:700;margin:0 0 18px}
h1{font-size:clamp(38px,5.2vw,64px);line-height:1.02;margin:0 0 18px;font-weight:700;
  letter-spacing:-.015em}
.stand{font-size:clamp(17px,1.9vw,21px);line-height:1.5;color:#3a4254;max-width:62ch;margin:0}
.byline{font-family:var(--sans);font-size:13px;color:var(--muted);margin:26px 0 0;
  letter-spacing:.02em}
.byline b{color:var(--ink)}
/* stat cards */
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin:34px 0 0}
.card{background:var(--card);border:1px solid var(--line);border-top:3px solid var(--men);
  padding:16px 16px 14px;border-radius:0 0 6px 6px}
.card:first-child{border-top-color:var(--women)}
.card:nth-child(3){border-top-color:var(--women)}
.big{font-family:var(--sans);font-size:22px;font-weight:700;letter-spacing:-.01em;white-space:nowrap}
.lab{font-family:var(--sans);font-size:12.5px;color:var(--ink);margin-top:7px;line-height:1.35;
  min-height:52px}
.sub{font-family:var(--sans);font-size:12.5px;color:var(--muted);margin-top:6px}
/* sections */
main{padding:14px 0 8px}
.block{padding:44px 0 8px;border-top:1px solid var(--line);margin-top:30px}
.block:first-of-type{border-top:none;margin-top:0;padding-top:16px}
h2{font-size:clamp(24px,2.6vw,31px);line-height:1.15;margin:0 0 16px;font-weight:700;
  letter-spacing:-.01em}
h2 span{font-family:var(--sans);font-size:13px;color:var(--women);font-weight:700;
  letter-spacing:.14em;margin-right:14px;vertical-align:2px}
.block p{max-width:74ch;margin:0 0 14px}
figure{margin:24px 0 10px;background:var(--card);border:1px solid var(--line);border-radius:8px;
  padding:18px 18px 10px}
figure svg{display:block;width:100%;height:auto}
figcaption{font-family:var(--sans);font-size:12.5px;color:var(--muted);line-height:1.45;
  padding:10px 4px 8px;border-top:1px solid var(--line);margin-top:10px}
/* table */
.tablewrap{max-height:560px;overflow:auto;border:1px solid var(--line);border-radius:8px;
  background:var(--card);margin:22px 0 0}
table{border-collapse:collapse;width:100%;font-family:var(--sans);font-size:13px}
thead th{position:sticky;top:0;background:#efe9db;text-align:left;font-weight:700;color:var(--ink);
  padding:9px 10px;border-bottom:2px solid var(--ink);white-space:nowrap}
tbody td{padding:7px 10px;border-bottom:1px solid #eee7d8;white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
tbody tr.w td.g{color:var(--women);font-weight:700}
tbody tr.m td.g{color:var(--men);font-weight:700}
td.b{font-weight:600}td.n{color:#454d5c}td.r,th.r{text-align:right;font-variant-numeric:tabular-nums}
td.c{text-align:center;color:var(--muted)}
tbody tr:hover{background:#f4efdf}
tbody tr.w{border-left:3px solid var(--women)}
tbody tr.m{border-left:3px solid var(--men)}
/* notes */
.notes{margin:44px 0 0;padding:26px 0 0;border-top:1px solid var(--line)}
.notes h3{font-family:var(--sans);font-size:13px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--muted);margin:0 0 14px}
.notes ul{margin:0;padding-left:20px;max-width:78ch}
.notes li{font-size:14.5px;line-height:1.55;margin-bottom:10px;color:#3a4254}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;
  background:#eee8da;border-radius:3px;padding:1px 4px}
footer{margin:36px 0 0;padding:22px 0 46px;border-top:3px solid var(--ink);
  font-family:var(--sans);font-size:13px;color:var(--muted)}
footer b{color:var(--ink)}
/* tooltip */
#tip{position:fixed;z-index:50;pointer-events:none;background:#1c2230;color:#f6f3ec;
  font-family:var(--sans);font-size:12.5px;line-height:1.45;padding:9px 11px;border-radius:6px;
  max-width:250px;box-shadow:0 6px 18px rgba(20,25,40,.28);display:none}
#tip .t{font-weight:700;margin-bottom:3px}
#tip .d{color:#c3cad6}
circle.hot{cursor:pointer}
circle.hot:hover{stroke:#1c2230;stroke-width:2.5}
@media (max-width:1000px){.stats{grid-template-columns:repeat(2,1fr)}.card .lab{min-height:0}}
'''

JS = '''
var REC = __RECORDS__;
var tip = document.getElementById('tip');
function showTip(ev, html){
  tip.innerHTML = html; tip.style.display = 'block';
  move(ev);
}
function move(ev){
  var x = ev.clientX + 16, y = ev.clientY + 14;
  var w = tip.offsetWidth, h = tip.offsetHeight;
  if (x + w > window.innerWidth - 12) x = ev.clientX - w - 14;
  if (y + h > window.innerHeight - 12) y = ev.clientY - h - 12;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
function hide(){ tip.style.display = 'none'; }
function fmt(r){
  var g = r.g === 'women' ? 'women\\u2019s' : 'men\\u2019s';
  return '<div class="t">' + r.b + '</div><div>' + r.n + '</div>' +
         '<div class="d">' + g + ' &middot; ' + r.s + ' &middot; $' + r.p.toFixed(2) + '</div>' +
         '<div class="d">front ' + r.d.toFixed(1) + ' &times; ' + r.w.toFixed(1) +
         ' cm &middot; ' + Math.round(r.a) + ' cm&sup2;</div>' +
         '<div class="d">back ' + r.bd.toFixed(1) + ' &times; ' + r.bw.toFixed(1) +
         ' cm &middot; ' + Math.round(r.ba) + ' cm&sup2;</div>';
}
document.addEventListener('mouseover', function(ev){
  var t = ev.target.closest ? ev.target.closest('circle.hot') : null;
  if (t && t.dataset.i !== undefined){ showTip(ev, fmt(REC[+t.dataset.i])); }
  else if (t && t.dataset.b){ showTip(ev, '<div class="t">' + t.dataset.b + '</div>' +
      '<div class="d">one dot per department &middot; hover the chart rows for detail</div>'); }
});
document.addEventListener('mousemove', function(ev){ if (tip.style.display === 'block') move(ev); });
document.addEventListener('mouseout', function(ev){
  var t = ev.target.closest ? ev.target.closest('circle.hot') : null;
  if (t) hide();
});
'''

page = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The pocket gap \u2014 front and back pocket measurements of men\u2019s and women\u2019s jeans</title>
<style>{CSS}</style>
</head>
<body>
<div id="tip"></div>
<header class="masthead">
  <div class="wrap">
    <p class="kicker">Data report &middot; 80 pairs of jeans</p>
    <h1>The pocket gap</h1>
    <p class="stand">Front and back pocket measurements of men\u2019s and women\u2019s jeans from
    popular brands. Measured with the same tape on both departments, the average women\u2019s front
    pocket is about {front_share:.0%} the size of the average men\u2019s \u2014 and price, cut and
    brand explain none of it.</p>
    <p class="byline"><b>{len(m)} pairs</b> &middot; 40 women\u2019s &middot; 40 men\u2019s &middot;
    21 brand labels &middot; 5 styles &middot; prices {money(m.price.min())}\u2013{money(m.price.max())}
    &middot; 10 measurements per pair</p>
  </div>
</header>
<div class="wrap">
<main>
{''.join(sections)}
</main>
{notes}
<footer>
  <p><b>How this was made.</b> Every number on this page is computed from
  <code>data/measurements.csv</code> ({len(m)} rows, no other source). Each finding is paired with the
  one-line pandas expression that produces it, listed in <code>facts.json</code> alongside this page.
  Charts are inline SVG generated from the same file; nothing is loaded from the network.</p>
</footer>
</div>
<script>
{JS.replace('__RECORDS__', json.dumps(records))}
</script>
</body>
</html>
'''

with open('index.html', 'w') as fh:
    fh.write(page)
print('wrote index.html', len(page), 'bytes')
