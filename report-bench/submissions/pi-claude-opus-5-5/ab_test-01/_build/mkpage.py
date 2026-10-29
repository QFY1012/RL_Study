import pandas as pd, numpy as np, html
d=pd.read_csv('data/data.csv')
d['g']=d.group.str.strip().map({'实验组':'treatment','对照组':'control'})
d['date']=pd.to_datetime(d.enter_date.str.replace('/','-'))
DEP={'儿科':'Pediatrics','内科':'Internal medicine','皮肤科':'Dermatology','妇科':'Gynecology','五官科':'ENT & eye'}
d['dep']=d.department.map(DEP)
CT,TR='#9aa3ad','#d9480f'
FONT="font-family='system-ui,-apple-system,Segoe UI,Roboto,sans-serif'"

def daily_chart():
    t=d.groupby(['date','g']).first_response_seconds.median().unstack()
    W,H,L,R,T,B=880,320,52,110,20,40
    xs=lambda i: L+i*(W-L-R)/(len(t)-1); ys=lambda v: T+(H-T-B)*(1-v/160)
    o=[f"<svg viewBox='0 0 {W} {H}' {FONT} font-size='12' role='img' aria-label='Daily median first-response time by group'>"]
    for v in range(0,161,40):
        o.append(f"<line x1='{L}' x2='{W-R}' y1='{ys(v)}' y2='{ys(v)}' stroke='#e6e8eb'/><text x='{L-8}' y='{ys(v)+4}' text-anchor='end' fill='#666'>{v}s</text>")
    i9=list(t.index).index(pd.Timestamp('2024-12-09'))
    o.append(f"<rect x='{xs(i9)-3}' y='{T}' width='{W-R-xs(i9)+3}' height='{H-T-B}' fill='#f6f1ea'/>")
    o.append(f"<text x='{xs(i9)+6}' y='{T+14}' fill='#8a6d3b'>from 9 Dec: higher traffic, longer waits</text>")
    for v in range(0,161,40): o.append(f"<line x1='{L}' x2='{W-R}' y1='{ys(v)}' y2='{ys(v)}' stroke='#e6e8eb'/>")
    for i,dt in enumerate(t.index):
        if dt.day in (18,25) and dt.month==11 or dt.day in (2,9,16,23) and dt.month==12 or i==len(t)-1:
            o.append(f"<text x='{xs(i)}' y='{H-B+18}' text-anchor='middle' fill='#666'>{dt.strftime('%b %-d')}</text>")
    for col,c,w in (('control',CT,2),('treatment',TR,2.5)):
        pts=' '.join(f"{xs(i):.1f},{ys(v):.1f}" for i,v in enumerate(t[col]))
        o.append(f"<polyline points='{pts}' fill='none' stroke='{c}' stroke-width='{w}'/>")
        o.append(f"<text x='{xs(len(t)-1)+8}' y='{ys(t[col].iloc[-1])+4}' fill='{c}' font-weight='600'>{col} {t[col].iloc[-1]:.0f}s</text>")
    o.append("</svg>"); return ''.join(o)

def dept_chart():
    t=d.groupby(['dep','g']).lost_before_doctor.mean().mul(100).unstack().sort_values('treatment')
    W,rowh,L,T=880,46,170,28; H=T+rowh*len(t)+30
    xs=lambda v: L+v*(W-L-80)/14
    o=[f"<svg viewBox='0 0 {W} {H}' {FONT} font-size='13' role='img' aria-label='Share leaving before a doctor by department'>"]
    for v in range(0,15,2):
        o.append(f"<line x1='{xs(v)}' x2='{xs(v)}' y1='{T-6}' y2='{H-24}' stroke='#e6e8eb'/><text x='{xs(v)}' y='{H-8}' text-anchor='middle' fill='#666' font-size='12'>{v}%</text>")
    for i,(dep,r) in enumerate(t.iterrows()):
        y=T+i*rowh+rowh/2; bold=dep=='Dermatology'
        o.append(f"<text x='{L-14}' y='{y+4}' text-anchor='end' fill='#222' font-weight='{700 if bold else 400}'>{dep}</text>")
        o.append(f"<line x1='{xs(r.control)}' x2='{xs(r.treatment)}' y1='{y}' y2='{y}' stroke='{TR if bold else '#c8cdd2'}' stroke-width='3'/>")
        o.append(f"<circle cx='{xs(r.control)}' cy='{y}' r='7' fill='{CT}'/><circle cx='{xs(r.treatment)}' cy='{y}' r='7' fill='{TR}'/>")
        lo,hi=sorted([(r.control,'c'),(r.treatment,'t')])
        o.append(f"<text x='{xs(hi[0])+13}' y='{y+4}' fill='#333' font-size='12'>{r.control:.1f}% → {r.treatment:.1f}%</text>")
    o.append(f"<circle cx='{L}' cy='10' r='6' fill='{CT}'/><text x='{L+10}' y='14' fill='#444'>control</text><circle cx='{L+80}' cy='10' r='6' fill='{TR}'/><text x='{L+90}' y='14' fill='#444'>treatment</text>")
    o.append("</svg>"); return ''.join(o)

def derm_table():
    CN={'后背长了不少小红点':'Red spots on the back','手臂上起红疹,特别痒':'Itchy red rash on the arm','脚趾缝脱皮发痒':'Peeling, itchy skin between toes','脸上爆痘,下巴最严重':'Facial acne, worst on the chin','荨麻疹反反复复两个星期':'Hives coming back for two weeks'}
    s=d[d.department=='皮肤科']
    t=s.groupby(['chief_complaint','g']).lost_before_doctor.agg(['mean','size']).unstack()
    rows=[]
    for cc in t.index:
        c,tr=t.loc[cc,('mean','control')]*100,t.loc[cc,('mean','treatment')]*100
        n=int(t.loc[cc,('size','control')]+t.loc[cc,('size','treatment')])
        rows.append((tr-c,f"<tr><td>{CN[cc]}<span class='cn'>{html.escape(cc)}</span></td><td class='num'>{n:,}</td><td class='num'>{c:.1f}%</td><td class='num tr'>{tr:.1f}%</td><td><span class='bar' style='width:{(tr-c)*14:.0f}px'></span> +{tr-c:.1f} pts</td></tr>"))
    rows.sort(reverse=True)
    return "<table class='t'><thead><tr><th>Dermatology complaint</th><th class='num'>Users</th><th class='num'>Control</th><th class='num'>Treatment</th><th>Gap</th></tr></thead><tbody>"+''.join(r for _,r in rows)+"</tbody></table>"

def fu_chart():
    t=d.groupby([d.user_type.map({'新用户':'New users','老用户':'Returning users'}),'g']).followup_7d.mean().mul(100).unstack()
    W,H,L,B,T=420,260,40,40,24; ys=lambda v:T+(H-T-B)*(1-v/18)
    o=[f"<svg viewBox='0 0 {W} {H}' {FONT} font-size='12' role='img' aria-label='7-day follow-up by user type'>"]
    for v in range(0,19,6): o.append(f"<line x1='{L}' x2='{W-10}' y1='{ys(v)}' y2='{ys(v)}' stroke='#e6e8eb'/><text x='{L-6}' y='{ys(v)+4}' text-anchor='end' fill='#666'>{v}%</text>")
    for i,(ut,r) in enumerate(t.iterrows()):
        x0=L+30+i*180
        for j,(col,c) in enumerate((('control',CT),('treatment',TR))):
            x=x0+j*62; v=r[col]
            o.append(f"<rect x='{x}' y='{ys(v)}' width='52' height='{ys(0)-ys(v)}' fill='{c}'/><text x='{x+26}' y='{ys(v)-6}' text-anchor='middle' font-weight='600' fill='#222'>{v:.1f}%</text>")
        o.append(f"<text x='{x0+57}' y='{H-14}' text-anchor='middle' fill='#222' font-size='13'>{ut}</text>")
    o.append("</svg>"); return ''.join(o)

def funnel():
    lost=d.lost_before_doctor.sum(); nc=((d.lost_before_doctor==0)&(d.is_completed==0)).sum(); comp=d.is_completed.sum(); n=len(d)
    segs=[(comp,'#2f6f4f','Completed'),(nc,'#c9a227','Reached a doctor, not completed'),(lost,'#b23a3a','Left before a doctor')]
    o="<div class='funnel'>"+''.join(f"<div style='flex:{v};background:{c}' title='{l}'></div>" for v,c,l in segs)+"</div><div class='flegend'>"+''.join(f"<span><i style='background:{c}'></i>{l}: <b>{v:,}</b> ({v/n*100:.1f}%)</span>" for v,c,l in segs)+"</div>"
    return o

page=open('_build/template.html').read()
for k,f in {'DAILY':daily_chart,'DEPT':dept_chart,'DERM':derm_table,'FU':fu_chart,'FUNNEL':funnel}.items():
    page=page.replace('{{'+k+'}}',f())
open('index.html','w').write(page)
