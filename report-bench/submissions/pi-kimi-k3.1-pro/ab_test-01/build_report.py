from string import Template
from pathlib import Path
from html import escape
import pandas as pd
import numpy as np

D = pd.read_csv('data/data.csv')
D['arm'] = D.group.str.strip().map({'对照组':'Control','实验组':'Treatment'})
D['dept'] = D.department.map({'内科':'Internal medicine','儿科':'Pediatrics','皮肤科':'Dermatology','妇科':'Gynecology','五官科':'ENT & ophthalmology'})
D['kind'] = D.user_type.map({'新用户':'New users','老用户':'Returning users'})
D['date'] = pd.to_datetime(D.enter_date, format='mixed')

CONTROL = '#7a8791'
TREATMENT = '#118578'
CORAL = '#d56455'

def pct(x, digits=2):
    return f'{100*x:.{digits}f}%'

def pp(x, digits=2, sign=True):
    v = 100*x
    return f'{v:+.{digits}f} pp' if sign else f'{v:.{digits}f} pp'

def signed(x, digits=2, suffix=''):
    return f'{x:+.{digits}f}{suffix}'

def rate_summary(frame, value):
    g = frame.groupby('arm')[value].agg(['count','sum','mean'])
    diff = g.loc['Treatment','mean'] - g.loc['Control','mean']
    se = np.sqrt(g.loc['Control','mean']*(1-g.loc['Control','mean'])/g.loc['Control','count'] + g.loc['Treatment','mean']*(1-g.loc['Treatment','mean'])/g.loc['Treatment','count'])
    return g, diff, 1.96*se

# Core metrics
control_n = int(D.arm.eq('Control').sum())
treatment_n = int(D.arm.eq('Treatment').sum())
response = D.groupby('arm').first_response_seconds.agg(n='count', median='median', p90=lambda s:s.quantile(.9))
response_saved = response.loc['Control','median'] - response.loc['Treatment','median']
response_reduction = response_saved / response.loc['Control','median']
within_120 = D.groupby('arm').first_response_seconds.apply(lambda s:s.dropna().le(120).mean())
completion, completion_diff, completion_moe = rate_summary(D, 'is_completed')
loss, loss_diff, loss_moe = rate_summary(D, 'lost_before_doctor')
consult = D.groupby('arm').consult_minutes.agg(n='count', median='median', p90=lambda s:s.quantile(.9))
consult_saved = consult.loc['Control','median'] - consult.loc['Treatment','median']

# Daily median response SVG
daily = D.groupby(['date','arm']).first_response_seconds.median().unstack('arm').sort_index()
daily_faster = int(daily.Treatment.lt(daily.Control).sum())

def daily_chart(frame):
    W, H = 860, 330
    left, right, top, bottom = 56, 824, 24, 268
    ymin, ymax = 60, 150
    xs = np.linspace(left, right, len(frame))
    def y(v): return bottom - (v-ymin)/(ymax-ymin)*(bottom-top)
    parts = [f'<svg class="daily-svg" viewBox="0 0 {W} {H}" role="img" aria-label="Daily median first response in seconds for Control and Treatment over 42 days">']
    for tick in [60,90,120,150]:
        yy = y(tick)
        parts.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" class="grid"/>')
        parts.append(f'<text x="{left-13}" y="{yy+4:.1f}" text-anchor="end" class="axis">{tick}</text>')
    parts.append(f'<text x="14" y="15" class="axis-title">seconds</text>')
    # A neutral date marker, not a claim about the cause of the visible level shift.
    marker_date = pd.Timestamp('2024-12-09')
    marker_idx = frame.index.get_loc(marker_date)
    mx = xs[marker_idx]
    parts.append(f'<line x1="{mx:.1f}" y1="{top}" x2="{mx:.1f}" y2="{bottom}" class="date-marker"/>')
    parts.append(f'<text x="{mx+8:.1f}" y="{top+14}" class="marker-label">Dec 9</text>')
    for col, cls, color in [('Control','line-control',CONTROL),('Treatment','line-treatment',TREATMENT)]:
        vals = frame[col].to_numpy()
        points = ' '.join(f'{x:.1f},{y(v):.1f}' for x,v in zip(xs,vals))
        parts.append(f'<polyline points="{points}" class="{cls}"/>')
        parts.append(f'<circle cx="{xs[0]:.1f}" cy="{y(vals[0]):.1f}" r="4" fill="{color}"/>')
        parts.append(f'<circle cx="{xs[-1]:.1f}" cy="{y(vals[-1]):.1f}" r="4.5" fill="{color}"/>')
        parts.append(f'<text x="{xs[-1]-2:.1f}" y="{y(vals[-1])-11:.1f}" text-anchor="end" class="endpoint" fill="{color}">{vals[-1]:.0f}s</text>')
    tick_dates = [frame.index[0], pd.Timestamp('2024-12-01'), pd.Timestamp('2024-12-15'), frame.index[-1]]
    for dt in tick_dates:
        idx = frame.index.get_loc(dt)
        parts.append(f'<text x="{xs[idx]:.1f}" y="{bottom+34}" text-anchor="middle" class="axis">{dt.strftime("%b %d")}</text>')
    parts.append(f'<text x="{left}" y="{H-5}" class="axis-note">Daily median · users with an observed response</text>')
    parts.append('</svg>')
    return ''.join(parts)

# Department frames
dept_group = D.groupby(['dept','arm']).agg(n=('user_id','size'), completion=('is_completed','mean'), loss=('lost_before_doctor','mean'), response=('first_response_seconds','median')).unstack('arm')
dept_order = ['Pediatrics','Internal medicine','Gynecology','ENT & ophthalmology','Dermatology']

def department_response_rows():
    out=[]
    for dept in dept_order:
        c=dept_group.loc[dept,('response','Control')]
        t=dept_group.loc[dept,('response','Treatment')]
        out.append(f'''<div class="dept-response-row">
          <div class="dept-response-head"><span>{escape(dept)}</span><strong>−{c-t:.0f}s</strong></div>
          <div class="mini-compare"><span class="mini-num control-text">{c:.0f}s</span><div class="mini-bars"><i style="width:{c/120*100:.2f}%;background:{CONTROL}"></i><i style="width:{t/120*100:.2f}%;background:{TREATMENT}"></i></div><span class="mini-num treatment-text">{t:.0f}s</span></div>
        </div>''')
    return ''.join(out)

def delta_rows(metric):
    out=[]
    for dept in dept_order:
        v=100*(dept_group.loc[dept,(metric,'Treatment')]-dept_group.loc[dept,(metric,'Control')])
        good = v>0 if metric=='completion' else v<0
        cls='good' if good else 'bad'
        width=min(abs(v)/5.5*50,50)
        left=50 if v>=0 else 50-width
        out.append(f'''<div class="delta-row">
          <div class="delta-name">{escape(dept)}</div>
          <div class="delta-track"><span class="zero"></span><i class="delta-bar {cls}" style="left:{left:.2f}%;width:{width:.2f}%"></i></div>
          <strong class="delta-value {cls}">{v:+.2f}</strong>
        </div>''')
    return ''.join(out)

# Dermatology confidence intervals
derm = D[D.dept.eq('Dermatology')]
derm_loss, derm_loss_diff, derm_loss_moe = rate_summary(derm, 'lost_before_doctor')
derm_completion, derm_completion_diff, derm_completion_moe = rate_summary(derm, 'is_completed')

# Top complaints
complaint_map = {
 '耳朵疼,总用手去抓':'Ear pain; frequent ear pulling',
 '咳嗽三天,夜里咳得更厉害':'Cough for 3 days; worse at night',
 '腹泻伴低烧一天':'Diarrhea with low-grade fever',
 '胃胀反酸一个星期':'Bloating and reflux for a week',
 '拉肚子两天,大便水样':'Watery diarrhea for 2 days'
}
complaint_dept = {
 'Ear pain; frequent ear pulling':'Pediatrics',
 'Cough for 3 days; worse at night':'Pediatrics',
 'Diarrhea with low-grade fever':'Internal medicine',
 'Bloating and reflux for a week':'Internal medicine',
 'Watery diarrhea for 2 days':'Pediatrics'
}
top_complaints = D.chief_complaint.replace(complaint_map).value_counts().head(5)

def top_complaint_rows():
    out=[]; maxv=top_complaints.max()
    for i,(name,count) in enumerate(top_complaints.items(),1):
        out.append(f'''<div class="complaint-row">
          <div class="complaint-rank">0{i}</div>
          <div class="complaint-body"><div class="complaint-label"><span>{escape(name)}<small>{complaint_dept[name]}</small></span><strong>{count:,}</strong></div><div class="volume-track"><i style="width:{count/maxv*100:.2f}%"></i></div></div>
        </div>''')
    return ''.join(out)

# Dermatology complaint-level loss
derm_complaint_map = {
 '后背长了不少小红点':'Small red spots on back',
 '手臂上起红疹,特别痒':'Itchy red rash on arm',
 '脚趾缝脱皮发痒':'Peeling, itchy toe webs',
 '脸上爆痘,下巴最严重':'Acne; worst on chin',
 '荨麻疹反反复复两个星期':'Recurrent urticaria for 2 weeks'
}
derm_complaints = derm.assign(complaint=derm.chief_complaint.map(derm_complaint_map)).groupby(['complaint','arm']).lost_before_doctor.mean().unstack('arm')
derm_complaints['delta'] = derm_complaints.Treatment-derm_complaints.Control
derm_complaints = derm_complaints.sort_values('delta',ascending=False)

def derm_complaint_rows():
    out=[]
    for name,row in derm_complaints.iterrows():
        out.append(f'''<div class="skin-row">
          <div class="skin-head"><span>{escape(name)}</span><strong>{100*row.delta:+.2f} pp</strong></div>
          <div class="skin-compare"><span>C</span><div class="skin-track"><i style="width:{100*row.Control/15*100:.2f}%;background:{CONTROL}"></i></div><b>{100*row.Control:.2f}%</b></div>
          <div class="skin-compare"><span>T</span><div class="skin-track"><i style="width:{100*row.Treatment/15*100:.2f}%;background:{CORAL}"></i></div><b>{100*row.Treatment:.2f}%</b></div>
        </div>''')
    return ''.join(out)

# Follow-up by user tenure
follow = D.groupby(['kind','arm']).followup_7d.agg(n='count',rate='mean').unstack('arm')

def follow_panel(kind, badge_class):
    c=follow.loc[kind,('rate','Control')]; t=follow.loc[kind,('rate','Treatment')]
    diff=t-c
    cn=int(follow.loc[kind,('n','Control')]); tn=int(follow.loc[kind,('n','Treatment')])
    se=np.sqrt(c*(1-c)/cn+t*(1-t)/tn)
    title='New users' if kind=='New users' else 'Returning users'
    kicker='More likely to return' if diff>0 else 'Less likely to return'
    return f'''<article class="follow-panel">
      <div class="follow-title"><div><span class="eyebrow">{title}</span><h3>{kicker}</h3></div><span class="delta-badge {badge_class}">{100*diff:+.2f} pp</span></div>
      <div class="follow-bars">
        <div class="follow-bar-row"><span>Control</span><div class="follow-track"><i style="width:{100*c/16*100:.2f}%;background:{CONTROL}"></i></div><strong>{100*c:.2f}%</strong></div>
        <div class="follow-bar-row"><span>Treatment</span><div class="follow-track"><i style="width:{100*t/16*100:.2f}%;background:{TREATMENT if diff>0 else CORAL}"></i></div><strong>{100*t:.2f}%</strong></div>
      </div>
      <div class="ci-line"><span>95% CI for difference</span><strong>{100*(diff-1.96*se):+.2f} to {100*(diff+1.96*se):+.2f} pp</strong></div>
      <p>Observed follow-up values: {cn:,} Control · {tn:,} Treatment.</p>
    </article>'''

# KPI cards
kpi_cards = f'''
<article class="kpi-card">
  <div class="kpi-top"><span class="kpi-icon speed-icon"></span><span class="kpi-label">Response ≤ 2 min</span></div>
  <div class="kpi-main">{100*within_120['Treatment']:.2f}% <span class="delta-badge good-bg">+{100*(within_120['Treatment']-within_120['Control']):.2f} pp</span></div>
  <div class="kpi-baseline">Treatment <b>·</b> Control {100*within_120['Control']:.2f}%</div>
  <p>Among users with an observed first response.</p>
</article>
<article class="kpi-card">
  <div class="kpi-top"><span class="kpi-icon complete-icon"></span><span class="kpi-label">Consult completion</span></div>
  <div class="kpi-main">{100*completion.loc['Treatment','mean']:.2f}% <span class="delta-badge neutral-bg">{100*completion_diff:+.2f} pp</span></div>
  <div class="kpi-baseline">Treatment <b>·</b> Control {100*completion.loc['Control','mean']:.2f}%</div>
  <p>95% CI {100*(completion_diff-completion_moe):+.2f} to {100*(completion_diff+completion_moe):+.2f} pp.</p>
</article>
<article class="kpi-card warning-card">
  <div class="kpi-top"><span class="kpi-icon loss-icon"></span><span class="kpi-label">Lost before doctor</span></div>
  <div class="kpi-main">{100*loss.loc['Treatment','mean']:.2f}% <span class="delta-badge bad-bg">{100*loss_diff:+.2f} pp</span></div>
  <div class="kpi-baseline">Treatment <b>·</b> Control {100*loss.loc['Control','mean']:.2f}%</div>
  <p>95% CI {100*(loss_diff-loss_moe):+.2f} to {100*(loss_diff+loss_moe):+.2f} pp.</p>
</article>
<article class="kpi-card">
  <div class="kpi-top"><span class="kpi-icon duration-icon"></span><span class="kpi-label">Median consult</span></div>
  <div class="kpi-main">{consult.loc['Treatment','median']:.1f}<small> min</small> <span class="delta-badge good-bg">−{consult_saved:.1f} min</span></div>
  <div class="kpi-baseline">Treatment <b>·</b> Control {consult.loc['Control','median']:.1f} min</div>
  <p>Completed consultations with observed duration.</p>
</article>'''

page = Template(r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="An offline A/B report on response waiting, consultation completion, departments, complaints and follow-up for 18,000 online medical consultation users.">
<title>Online Care A/B Readout — Waiting, Completion &amp; Follow-up</title>
<style>
:root{--ink:#132f2e;--muted:#657672;--paper:#f3f6f3;--card:#ffffff;--line:#dce5df;--teal:#118578;--teal-dark:#0b6159;--teal-soft:#e1f2ed;--control:#7a8791;--coral:#d56455;--coral-soft:#fbeae6;--amber:#d6a34c;--navy:#0c2d2b}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:82px}body{margin:0;background:var(--paper);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}a{color:inherit;text-decoration:none}svg{display:block}.shell{width:min(1280px,calc(100% - 80px));margin:0 auto}.topbar{height:76px;display:flex;align-items:center;justify-content:space-between}.brand{display:flex;align-items:center;gap:12px;font-weight:750;letter-spacing:-.3px}.brand-mark{width:30px;height:30px;border-radius:9px;background:var(--ink);position:relative}.brand-mark:before,.brand-mark:after{content:"";position:absolute;background:#a9e3d2;border-radius:2px;left:8px;right:8px;top:13px;height:4px}.brand-mark:after{top:8px;bottom:8px;left:13px;width:4px;height:auto}.brand small{display:block;color:var(--muted);font-size:10px;letter-spacing:1.5px;font-weight:650;margin-top:1px}.nav{display:flex;align-items:center;gap:28px;color:#536763;font-size:13px;font-weight:600}.nav a:hover{color:var(--teal)}.nav .nav-meta{border-left:1px solid #cdd9d2;padding-left:26px;color:var(--ink);font-variant-numeric:tabular-nums}
.hero{background:var(--navy);border-radius:26px;color:white;position:relative;overflow:hidden;min-height:500px;display:grid;grid-template-columns:1.35fr .85fr;gap:64px;padding:62px 64px}.hero:before{content:"";position:absolute;inset:0;background:radial-gradient(circle at 83% 18%,rgba(62,175,151,.20),transparent 35%),linear-gradient(120deg,transparent 55%,rgba(255,255,255,.025) 55%);pointer-events:none}.hero-copy,.hero-visual{position:relative;z-index:1}.eyebrow{display:block;font-size:10px;font-weight:800;letter-spacing:1.7px;text-transform:uppercase;color:var(--teal)}.hero .eyebrow{color:#91d8c4;margin-bottom:22px}.hero h1{font-size:62px;line-height:1.04;letter-spacing:-3.2px;font-weight:680;margin:0 0 25px;max-width:690px}.hero-deck{font-size:18px;line-height:1.65;color:#c7d8d3;max-width:650px;margin:0}.hero-deck strong{color:#fff;font-weight:650}.hero-meta{display:flex;align-items:center;gap:12px;margin-top:34px;flex-wrap:wrap}.hero-meta span{border:1px solid rgba(193,226,216,.22);border-radius:100px;padding:7px 12px;font-size:11px;color:#c9ddd6;letter-spacing:.2px}.hero-visual{align-self:center;background:rgba(255,255,255,.065);border:1px solid rgba(255,255,255,.12);border-radius:20px;padding:30px 30px 26px;box-shadow:0 22px 70px rgba(0,0,0,.12)}.hero-visual .eyebrow{margin:0 0 9px;font-size:9px}.big-saving{font-size:82px;line-height:1;font-weight:650;letter-spacing:-5px;margin:6px 0 10px;font-variant-numeric:tabular-nums}.big-saving small{font-size:26px;letter-spacing:-1px;margin-left:6px;color:#a9d8cb}.hero-visual h2{font-size:16px;font-weight:550;margin:0 0 28px;color:#d9e7e2}.wait-compare{margin:18px 0}.wait-label{display:flex;justify-content:space-between;font-size:12px;margin-bottom:7px;color:#d5e1dd}.wait-label strong{font-size:13px;color:white;font-variant-numeric:tabular-nums}.hero-wait-track{height:8px;background:rgba(255,255,255,.08);border-radius:20px;overflow:hidden}.hero-wait-track i{display:block;height:100%;border-radius:20px}.reduction-line{display:flex;justify-content:space-between;border-top:1px solid rgba(255,255,255,.12);padding-top:20px;margin-top:25px;font-size:12px;color:#bcd1ca}.reduction-line strong{color:#8ee0c7;font-size:14px}.hero-source{font-size:10px;color:#91aaa3;margin:18px 0 0;line-height:1.5}
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:18px}.kpi-card{background:var(--card);border:1px solid var(--line);border-radius:17px;padding:22px 23px 18px;min-width:0}.kpi-card.warning-card{border-color:#ead8d2}.kpi-top{display:flex;align-items:center;gap:9px}.kpi-label{font-size:11px;font-weight:750;letter-spacing:.45px;text-transform:uppercase;color:#596d67}.kpi-icon{width:18px;height:18px;border:1.5px solid #94aaa2;border-radius:50%;position:relative;flex:none}.speed-icon:after{content:"";position:absolute;width:5px;height:1.5px;background:var(--teal);left:8px;top:5px;transform:rotate(40deg);transform-origin:left}.complete-icon{border-radius:5px}.complete-icon:after{content:"";position:absolute;width:7px;height:4px;border-left:1.5px solid var(--teal);border-bottom:1.5px solid var(--teal);transform:rotate(-45deg);left:4px;top:4px}.loss-icon{border-color:#d79285}.loss-icon:after{content:"";position:absolute;width:7px;height:1.5px;background:var(--coral);left:4px;top:7px}.duration-icon{border-radius:5px}.duration-icon:after{content:"";position:absolute;left:4px;right:4px;top:7px;height:1.5px;background:var(--teal)}.kpi-main{font-size:31px;font-weight:690;letter-spacing:-1px;margin:16px 0 2px;display:flex;align-items:center;gap:10px;white-space:nowrap;font-variant-numeric:tabular-nums}.kpi-main small{font-size:17px;font-weight:550;letter-spacing:0;margin-left:-7px}.delta-badge{display:inline-flex;align-items:center;justify-content:center;border-radius:100px;padding:5px 9px;font-size:11px;line-height:1;font-weight:750;letter-spacing:0;white-space:nowrap}.good-bg{background:var(--teal-soft);color:var(--teal-dark)}.bad-bg{background:var(--coral-soft);color:#a84b3f}.neutral-bg{background:#edf0ef;color:#5c6b67}.kpi-baseline{font-size:12px;color:#5f736c}.kpi-baseline b{color:#b3c1ba;margin:0 4px}.kpi-card p{font-size:11px;color:#81918b;margin:13px 0 0;border-top:1px solid #edf1ee;padding-top:11px}
.section{padding-top:84px}.section-heading{display:grid;grid-template-columns:80px 1fr 1fr;gap:20px;align-items:start;margin-bottom:28px}.section-no{font-size:12px;color:#8a9a94;font-weight:700;letter-spacing:1px;padding-top:8px}.section-heading h2{font-size:36px;line-height:1.16;letter-spacing:-1.4px;margin:0;font-weight:660}.section-heading p{margin:5px 0 0;color:var(--muted);font-size:15px;max-width:500px}.card{background:var(--card);border:1px solid var(--line);border-radius:20px}.speed-grid{display:grid;grid-template-columns:1.65fr .85fr;gap:18px}.chart-card{padding:28px 30px 22px}.card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:18px}.card-head h3{font-size:18px;line-height:1.35;margin:4px 0 0;letter-spacing:-.35px}.card-head p{font-size:12px;color:var(--muted);margin:5px 0 0}.legend{display:flex;gap:17px;font-size:11px;color:#5d716b;white-space:nowrap;padding-top:7px}.legend span{display:flex;align-items:center;gap:7px}.legend i{display:inline-block;width:18px;height:3px;border-radius:3px}.evidence-pill{border-radius:100px;background:var(--teal-soft);color:var(--teal-dark);font-weight:750;font-size:11px;padding:7px 11px;white-space:nowrap}.daily-svg{width:100%;height:auto;margin-top:5px}.daily-svg .grid{stroke:#e6ece8;stroke-width:1}.daily-svg .axis{fill:#84958f;font-size:11px}.daily-svg .axis-title{fill:#84958f;font-size:9px;letter-spacing:.8px}.daily-svg .axis-note{fill:#98a69f;font-size:9px}.daily-svg .line-control{fill:none;stroke:var(--control);stroke-width:2.4;stroke-linejoin:round;stroke-linecap:round}.daily-svg .line-treatment{fill:none;stroke:var(--teal);stroke-width:2.7;stroke-linejoin:round;stroke-linecap:round}.daily-svg .endpoint{font-size:11px;font-weight:750}.daily-svg .date-marker{stroke:#d9c7aa;stroke-dasharray:4 5;stroke-width:1}.daily-svg .marker-label{fill:#a08864;font-size:9px}.response-dept-card{padding:28px 26px}.control-text{color:var(--control)}.treatment-text{color:var(--teal)}.dept-response-row{padding:13px 0 12px;border-bottom:1px solid #edf1ee}.dept-response-row:last-child{border-bottom:0}.dept-response-head{display:flex;justify-content:space-between;align-items:center;font-size:12px;font-weight:650}.dept-response-head strong{color:var(--teal);font-size:12px}.mini-compare{display:grid;grid-template-columns:36px 1fr 36px;align-items:center;gap:9px;margin-top:9px}.mini-num{font-size:10px;font-weight:700;font-variant-numeric:tabular-nums}.mini-num:last-child{text-align:right}.mini-bars{display:flex;flex-direction:column;gap:3px}.mini-bars i{height:3px;display:block;border-radius:3px;min-width:2px}.response-foot{margin-top:17px;padding:14px 15px;background:#f3f7f4;border-radius:11px;font-size:11px;color:#62766f}.response-foot strong{color:var(--ink)}
.department-grid{display:grid;grid-template-columns:1fr 1fr .9fr;gap:18px}.delta-card{padding:27px 25px}.delta-explain{font-size:10px;color:#8a9994;margin:-7px 0 23px}.delta-row{display:grid;grid-template-columns:112px 1fr 48px;gap:10px;align-items:center;padding:13px 0;border-bottom:1px solid #edf1ee}.delta-row:last-child{border-bottom:0}.delta-name{font-size:11px;font-weight:620;line-height:1.3}.delta-track{height:12px;position:relative;background:linear-gradient(to right,#f5f7f5,#fafbfa);border-radius:2px}.delta-track .zero{position:absolute;left:50%;top:-4px;bottom:-4px;width:1px;background:#b7c4be}.delta-bar{position:absolute;top:3px;height:6px;border-radius:4px;min-width:2px}.delta-bar.good{background:var(--teal)}.delta-bar.bad{background:var(--coral)}.delta-value{font-size:11px;text-align:right;font-variant-numeric:tabular-nums}.delta-value.good{color:var(--teal-dark)}.delta-value.bad{color:#b45346}.delta-axis{display:flex;justify-content:space-between;color:#96a49f;font-size:9px;margin:14px 0 0 122px}.derm-card{background:#193b38;color:white;border-radius:20px;padding:29px 28px;position:relative;overflow:hidden}.derm-card:after{content:"";position:absolute;width:170px;height:170px;border:40px solid rgba(255,255,255,.025);border-radius:50%;right:-90px;top:-90px}.derm-card .eyebrow{color:#edb3a7}.derm-card h3{font-size:23px;line-height:1.2;letter-spacing:-.6px;margin:9px 0 10px}.derm-card>p{font-size:12px;color:#c3d5d0;margin:0 0 24px}.derm-big{font-size:48px;font-weight:670;letter-spacing:-2px;line-height:1;color:#ffb6a8}.derm-big-label{font-size:11px;color:#d5e0dc;margin:8px 0 21px}.derm-rates{display:flex;justify-content:space-between;align-items:center;border-top:1px solid rgba(255,255,255,.13);border-bottom:1px solid rgba(255,255,255,.13);padding:16px 0;font-size:11px;color:#bfd2cc}.derm-rates strong{color:white;font-size:13px}.derm-stats{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:19px}.derm-stat{background:rgba(255,255,255,.055);padding:12px;border-radius:10px}.derm-stat span{display:block;font-size:9px;color:#aac3bb;text-transform:uppercase;letter-spacing:.7px}.derm-stat strong{display:block;font-size:13px;margin-top:5px}.derm-stat small{display:block;font-size:9px;color:#b8cdc6;margin-top:3px}.derm-note{font-size:10px!important;margin:19px 0 0!important;color:#a9c2ba!important}
.complaint-grid{display:grid;grid-template-columns:1fr 1.12fr;gap:18px}.complaint-card{padding:28px 29px}.complaint-row{display:grid;grid-template-columns:30px 1fr;gap:12px;padding:13px 0;border-bottom:1px solid #edf1ee}.complaint-row:last-child{border-bottom:0}.complaint-rank{font-size:10px;color:#99a8a2;font-weight:700;padding-top:3px}.complaint-label{display:flex;justify-content:space-between;align-items:flex-start;gap:15px;font-size:12px;font-weight:620}.complaint-label small{display:block;font-size:9px;color:#8a9a94;font-weight:500;margin-top:2px}.complaint-label strong{font-size:13px;font-variant-numeric:tabular-nums}.volume-track{height:5px;background:#eef2ef;border-radius:4px;margin-top:9px;overflow:hidden}.volume-track i{height:100%;display:block;background:linear-gradient(90deg,#75b9a8,var(--teal));border-radius:4px}.complaint-foot{font-size:10px;color:#8a9a94;margin:18px 0 0}.skin-row{padding:10px 0 11px;border-bottom:1px solid #edf1ee}.skin-row:last-child{border-bottom:0}.skin-head{display:flex;justify-content:space-between;gap:16px;font-size:11px;font-weight:620;margin-bottom:7px}.skin-head strong{color:#b45447;font-size:11px}.skin-compare{display:grid;grid-template-columns:14px 1fr 46px;align-items:center;gap:7px;margin:4px 0}.skin-compare>span{font-size:9px;color:#8a9a94;font-weight:700}.skin-compare>b{font-size:9px;text-align:right;color:#64766f;font-variant-numeric:tabular-nums}.skin-track{height:4px;background:#f0f2f0;border-radius:3px;overflow:hidden}.skin-track i{height:100%;display:block;border-radius:3px}.skin-legend{display:flex;gap:14px;font-size:9px;color:#8a9994;margin-top:15px}.skin-legend b{color:#5e716a}
.follow-shell{background:#e8efea;border:1px solid #d8e3dc;border-radius:24px;padding:36px}.follow-intro{display:flex;justify-content:space-between;align-items:end;gap:40px;margin-bottom:25px}.follow-intro h3{font-size:25px;letter-spacing:-.8px;margin:5px 0 0}.follow-intro p{font-size:12px;color:#62756e;max-width:440px;margin:0}.follow-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.follow-panel{background:white;border:1px solid #d8e2dc;border-radius:16px;padding:25px 27px}.follow-title{display:flex;justify-content:space-between;align-items:center;gap:15px}.follow-title h3{font-size:18px;margin:5px 0 0;letter-spacing:-.3px}.follow-title .delta-badge.good{color:var(--teal-dark);background:var(--teal-soft)}.follow-title .delta-badge.bad{color:#a84b3f;background:var(--coral-soft)}.follow-bars{margin:25px 0 20px}.follow-bar-row{display:grid;grid-template-columns:70px 1fr 54px;gap:12px;align-items:center;margin:13px 0;font-size:11px;color:#63766f}.follow-bar-row strong{text-align:right;color:var(--ink);font-size:12px;font-variant-numeric:tabular-nums}.follow-track{height:10px;background:#edf1ee;border-radius:10px;overflow:hidden}.follow-track i{height:100%;display:block;border-radius:10px}.ci-line{display:flex;justify-content:space-between;border-top:1px solid #e8eeea;padding-top:14px;font-size:10px;color:#82918b}.ci-line strong{color:#52665f;font-size:11px}.follow-panel p{font-size:10px;color:#8a9993;margin:8px 0 0}
.readout{margin-top:84px;background:var(--navy);color:white;border-radius:25px;padding:45px 48px;display:grid;grid-template-columns:.85fr 1.6fr;gap:55px}.readout .eyebrow{color:#90d6c2}.readout h2{font-size:35px;line-height:1.17;letter-spacing:-1.2px;margin:12px 0 17px}.readout-copy>p{font-size:13px;color:#b6cdc5;max-width:380px}.readout-tag{display:inline-flex;margin-top:17px;padding:7px 11px;border:1px solid rgba(255,255,255,.17);border-radius:100px;color:#c7dbd4;font-size:10px}.action-list{display:grid;gap:12px}.action{display:grid;grid-template-columns:32px 1fr;gap:14px;padding:17px 18px;background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.09);border-radius:13px}.action-no{width:28px;height:28px;border-radius:8px;background:rgba(139,216,192,.12);color:#9bdfca;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:750}.action h3{font-size:14px;margin:1px 0 4px}.action p{font-size:11px;color:#b5cac3;margin:0;line-height:1.55}.action.warning .action-no{background:rgba(238,150,134,.12);color:#f0a496}
.method-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:25px}.method-block{border-top:2px solid #cddad3;padding-top:17px}.method-block span{font-size:9px;color:#8c9c96;letter-spacing:1px;font-weight:750}.method-block h3{font-size:14px;margin:7px 0 9px}.method-block p{font-size:11px;line-height:1.65;color:#6d7e78;margin:0}.method-note{margin-top:28px;padding:16px 19px;background:#eaf0eb;border-radius:12px;color:#64766f;font-size:11px;display:flex;gap:14px}.method-note strong{color:var(--ink);white-space:nowrap}.footer{margin-top:70px;border-top:1px solid #d5dfd8;padding:25px 0 34px;display:flex;justify-content:space-between;color:#82918b;font-size:10px}.footer strong{color:#536861}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
@media(max-width:1100px){.shell{width:calc(100% - 40px)}.hero{padding:45px;grid-template-columns:1.2fr .8fr;gap:35px}.hero h1{font-size:50px}.kpi-grid{grid-template-columns:1fr 1fr}.speed-grid,.department-grid,.complaint-grid{grid-template-columns:1fr}.section-heading{grid-template-columns:55px 1fr}.section-heading p{grid-column:2}.readout{grid-template-columns:1fr}.method-grid{grid-template-columns:1fr 1fr}.nav{gap:16px}}
@media(max-width:700px){.nav a{display:none}.nav .nav-meta{border:0;padding:0}.hero{grid-template-columns:1fr;padding:34px 27px}.hero h1{font-size:43px}.big-saving{font-size:65px}.kpi-grid,.follow-grid,.method-grid{grid-template-columns:1fr}.section{padding-top:60px}.section-heading{grid-template-columns:1fr}.section-no,.section-heading p{grid-column:1}.section-heading h2{font-size:30px}.follow-shell{padding:22px}.readout{padding:32px 26px}.delta-row{grid-template-columns:100px 1fr 44px}.footer{gap:20px;flex-direction:column}.card-head{flex-direction:column}.legend{padding-top:0}}
</style>
</head>
<body>
<header class="shell topbar">
  <a class="brand" href="#top" aria-label="Care Experiment Readout home"><span class="brand-mark" aria-hidden="true"></span><span>CARE / READOUT<small>EXPERIMENT 01 · ONLINE CONSULTATION</small></span></a>
  <nav class="nav" aria-label="Report sections"><a href="#speed">Speed</a><a href="#departments">Departments</a><a href="#complaints">Complaints</a><a href="#followup">Follow-up</a><a href="#method">Method</a><span class="nav-meta">18,000 users</span></nav>
</header>
<main id="top" class="shell">
  <section class="hero" aria-labelledby="hero-title">
    <div class="hero-copy">
      <span class="eyebrow">A/B experiment · 18 Nov–29 Dec 2024</span>
      <h1 id="hero-title">Faster replies.<br>The same finish line.</h1>
      <p class="hero-deck">Treatment cut median first response by <strong>$response_saved seconds</strong>. Yet completion stayed flat overall—and <strong>Dermatology shows a clear abandonment warning</strong> beneath the average.</p>
      <div class="hero-meta"><span>$control_n_label Control</span><span>$treatment_n_label Treatment</span><span>42 days</span><span>5 departments</span></div>
    </div>
    <div class="hero-visual">
      <span class="eyebrow">Primary speed outcome</span>
      <div class="big-saving">−$response_saved<small>sec</small></div>
      <h2>median time to first response</h2>
      <div class="wait-compare"><div class="wait-label"><span>Control</span><strong>$control_response_median s</strong></div><div class="hero-wait-track"><i style="width:$control_wait_width%;background:#7a8791"></i></div></div>
      <div class="wait-compare"><div class="wait-label"><span>Treatment</span><strong>$treatment_response_median s</strong></div><div class="hero-wait-track"><i style="width:$treatment_wait_width%;background:#36b99d"></i></div></div>
      <div class="reduction-line"><span>Relative reduction</span><strong>$response_reduction_pct%</strong></div>
      <p class="hero-source">Median of observed first_response_seconds. The p90 also improves: $control_p90 s → $treatment_p90 s.</p>
    </div>
  </section>
  <section class="kpi-grid" aria-label="Headline experiment metrics">$kpi_cards</section>

  <section id="speed" class="section">
    <div class="section-heading"><span class="section-no">01 / SPEED</span><h2>The speed advantage is persistent.</h2><p>Treatment responds faster across days and departments. The gain is visible in the typical wait and at the slower tail—not just in an average distorted by outliers.</p></div>
    <div class="speed-grid">
      <article class="card chart-card">
        <div class="card-head"><div><span class="eyebrow">42-day view</span><h3>Daily median first response</h3><p>Lower is better · seconds</p></div><div class="legend"><span><i style="background:var(--control)"></i>Control</span><span><i style="background:var(--teal)"></i>Treatment</span></div></div>
        $daily_chart
      </article>
      <article class="card response-dept-card">
        <div class="card-head"><div><span class="eyebrow">Department check</span><h3>Every department waits less</h3><p>Median Control → Treatment</p></div><span class="evidence-pill">$daily_faster / 42 days</span></div>
        $department_response_rows
        <div class="response-foot">Savings range from <strong>20 to 26 seconds</strong>. The overall 90th percentile falls <strong>57 seconds</strong>.</div>
      </article>
    </div>
  </section>

  <section id="departments" class="section">
    <div class="section-heading"><span class="section-no">02 / OUTCOMES</span><h2>The average hides a Dermatology warning.</h2><p>Overall completion moves just $completion_diff_pp pp. Department deltas show why a single top-line rate is not enough: most movement is small, but skin consultations break away.</p></div>
    <div class="department-grid">
      <article class="card delta-card"><div class="card-head"><div><span class="eyebrow">Outcome 01</span><h3>Completion difference</h3><p>Treatment − Control</p></div></div><div class="delta-explain">Percentage points · positive is better</div>$completion_delta_rows<div class="delta-axis"><span>−5 pp</span><span>0</span><span>+5 pp</span></div></article>
      <article class="card delta-card"><div class="card-head"><div><span class="eyebrow">Outcome 02</span><h3>Pre-doctor loss difference</h3><p>Treatment − Control</p></div></div><div class="delta-explain">Percentage points · negative is better</div>$loss_delta_rows<div class="delta-axis"><span>−5 pp</span><span>0</span><span>+5 pp</span></div></article>
      <aside class="derm-card">
        <span class="eyebrow">Priority segment · Dermatology</span><h3>Faster replies,<br>more early exits.</h3><p>The largest department-level reversal appears despite a 21-second faster median response.</p>
        <div class="derm-big">$derm_loss_diff_pp pp</div><div class="derm-big-label">increase in lost before doctor</div>
        <div class="derm-rates"><span>Control <strong>$derm_control_loss%</strong></span><span>→</span><span>Treatment <strong>$derm_treatment_loss%</strong></span></div>
        <div class="derm-stats"><div class="derm-stat"><span>Loss Δ · 95% CI</span><strong>$derm_loss_ci</strong><small>percentage points</small></div><div class="derm-stat"><span>Completion Δ</span><strong>$derm_completion_diff_pp pp</strong><small>95% CI $derm_completion_ci</small></div></div>
        <p class="derm-note">Dermatology sample: $derm_control_n Control · $derm_treatment_n Treatment.</p>
      </aside>
    </div>
  </section>

  <section id="complaints" class="section">
    <div class="section-heading"><span class="section-no">03 / COMPLAINTS</span><h2>The skin signal is broad, not isolated.</h2><p>Pediatric and internal-medicine complaints dominate volume. Within Dermatology, however, all five complaint groups show higher pre-doctor loss under Treatment.</p></div>
    <div class="complaint-grid">
      <article class="card complaint-card"><div class="card-head"><div><span class="eyebrow">Demand mix</span><h3>Five most frequent complaints</h3><p>Users · both arms combined</p></div></div>$top_complaint_rows<p class="complaint-foot">Complaint names translated from the source field; 36 missing values are not ranked.</p></article>
      <article class="card complaint-card"><div class="card-head"><div><span class="eyebrow">Dermatology drill-down</span><h3>Pre-doctor loss by complaint</h3><p>Control and Treatment · observed rates</p></div><span class="evidence-pill" style="background:var(--coral-soft);color:#a84b3f">5 / 5 increase</span></div>$derm_complaint_rows<div class="skin-legend"><span><b>C</b> Control</span><span><b>T</b> Treatment</span><span>Bar scale: 0–15%</span></div></article>
    </div>
  </section>

  <section id="followup" class="section">
    <div class="section-heading"><span class="section-no">04 / RETENTION</span><h2>Follow-up tells two different stories.</h2><p>New and returning users move in opposite directions. Report these segments separately rather than treating 7-day follow-up as one uniform win or loss.</p></div>
    <div class="follow-shell"><div class="follow-intro"><div><span class="eyebrow">7-day follow-up</span><h3>Tenure changes the direction.</h3></div><p>Rates use non-missing follow-up values only. Confidence intervals are for Treatment − Control, in percentage points.</p></div><div class="follow-grid">$follow_new$follow_returning</div></div>
  </section>

  <section class="readout" aria-labelledby="readout-title">
    <div class="readout-copy"><span class="eyebrow">Decision readout</span><h2 id="readout-title">Roll forward on speed. Gate the rollout on Dermatology.</h2><p>The operational improvement is credible in the descriptive data. A completion or retention claim is not.</p><span class="readout-tag">Speed ≠ completed care</span></div>
    <div class="action-list">
      <article class="action"><span class="action-no">01</span><div><h3>Keep measuring the response-time win.</h3><p>Treatment is faster on $daily_faster of 42 days and in all five departments; the within-two-minute share rises $within_120_diff_pp pp.</p></div></article>
      <article class="action"><span class="action-no">02</span><div><h3>Do not call overall completion a win.</h3><p>The observed difference is $completion_diff_pp pp, with a 95% CI from $completion_ci_low to $completion_ci_high pp. Investigate whether shorter consults affect any downstream quality measure.</p></div></article>
      <article class="action warning"><span class="action-no">03</span><div><h3>Audit Dermatology routing and the pre-doctor queue.</h3><p>Early loss rises $derm_loss_diff_pp pp, and every Dermatology complaint group moves in the wrong direction. Review this segment before a broad rollout.</p></div></article>
    </div>
  </section>

  <section id="method" class="section">
    <div class="section-heading"><span class="section-no">05 / METHOD</span><h2>What was cleaned—and what was not assumed.</h2><p>The page is a descriptive readout of the supplied user-level table. All metrics are reproducible with the expressions in <span class="mono">facts.json</span>.</p></div>
    <div class="method-grid">
      <article class="method-block"><span>01 · COHORT</span><h3>One row per unique user</h3><p>18,000 rows and user IDs. Group labels are trimmed before comparison, consolidating 19 labels with trailing whitespace. Mixed date formats are parsed into 42 daily periods.</p></article>
      <article class="method-block"><span>02 · DENOMINATORS</span><h3>Missing is not zero</h3><p>Response and duration summaries skip missing values. All 903 missing responses align with pre-doctor loss; all 2,164 missing durations align with incomplete consultations. Follow-up excludes 186 missing values.</p></article>
      <article class="method-block"><span>03 · ROBUSTNESS</span><h3>Medians lead the time readout</h3><p>Seven response times exceed one hour and seven consultation durations equal 640 minutes. Medians and p90s are emphasized so these extremes do not define the headline.</p></article>
      <article class="method-block"><span>04 · UNCERTAINTY</span><h3>Intervals, not causal proof</h3><p>Rate intervals use a two-proportion normal approximation with a 1.96 critical value, unadjusted for multiple comparisons. Assignment and randomization details are not supplied.</p></article>
    </div>
    <div class="method-note"><strong>Interpretation guardrail</strong><span>“Control” and “Treatment” are English labels for the two cleaned source groups. Complaint and department names are translated for readability. No missing outcome is imputed, and no outlier is deleted.</span></div>
  </section>
</main>
<footer class="shell footer"><span><strong>CARE / READOUT</strong> · Online medical consultation experiment</span><span>Source: <span class="mono">data/data.csv</span> · 14 executable findings in <span class="mono">facts.json</span></span></footer>
</body>
</html>
''')

values = {
 'response_saved': f'{response_saved:.0f}',
 'control_n_label': f'{control_n:,}', 'treatment_n_label': f'{treatment_n:,}',
 'control_response_median': f'{response.loc["Control","median"]:.0f}', 'treatment_response_median': f'{response.loc["Treatment","median"]:.0f}',
 'control_wait_width': f'{response.loc["Control","median"]/120*100:.2f}', 'treatment_wait_width': f'{response.loc["Treatment","median"]/120*100:.2f}',
 'response_reduction_pct': f'{100*response_reduction:.1f}%', 'control_p90': f'{response.loc["Control","p90"]:.0f}', 'treatment_p90': f'{response.loc["Treatment","p90"]:.0f}',
 'kpi_cards': kpi_cards, 'daily_chart': daily_chart(daily), 'daily_faster': str(daily_faster), 'department_response_rows': department_response_rows(),
 'completion_delta_rows': delta_rows('completion'), 'loss_delta_rows': delta_rows('loss'),
 'completion_diff_pp': f'{100*completion_diff:+.2f}', 'completion_ci_low': f'{100*(completion_diff-completion_moe):+.2f}', 'completion_ci_high': f'{100*(completion_diff+completion_moe):+.2f}',
 'derm_loss_diff_pp': f'{100*derm_loss_diff:+.2f}', 'derm_control_loss': f'{100*derm_loss.loc["Control","mean"]:.2f}', 'derm_treatment_loss': f'{100*derm_loss.loc["Treatment","mean"]:.2f}',
 'derm_loss_ci': f'{100*(derm_loss_diff-derm_loss_moe):+.2f} to {100*(derm_loss_diff+derm_loss_moe):+.2f}',
 'derm_completion_diff_pp': f'{100*derm_completion_diff:+.2f}', 'derm_completion_ci': f'{100*(derm_completion_diff-derm_completion_moe):+.2f} to {100*(derm_completion_diff+derm_completion_moe):+.2f}',
 'derm_control_n': f'{int(derm_loss.loc["Control","count"]):,}', 'derm_treatment_n': f'{int(derm_loss.loc["Treatment","count"]):,}',
 'top_complaint_rows': top_complaint_rows(), 'derm_complaint_rows': derm_complaint_rows(),
 'follow_new': follow_panel('New users','good'), 'follow_returning': follow_panel('Returning users','bad'),
 'within_120_diff_pp': f'{100*(within_120["Treatment"]-within_120["Control"]):+.2f}'
}
html = page.substitute(values)
Path('index.html').write_text(html, encoding='utf-8')
print(f'Wrote index.html ({len(html):,} characters)')
