import pandas as pd, numpy as np
w=pd.read_csv('data/web.csv')

def teams(metric='rank_ws48', age=34, rank=15, yrs=3, superstar=True, agestrict='lt', rankstrict='lt'):
    out={}
    for Y in sorted(w.season_abbr.unique()):
        cur=w[w.season_abbr==Y]
        prev=w[(w.season_abbr>=Y-yrs)&(w.season_abbr<=Y-1)]
        for tm,grp in cur.groupby('tm'):
            stars=[]
            for _,p in grp.iterrows():
                ok_age = p.age<age if agestrict=='lt' else p.age<=age
                if not ok_age: continue
                pp=prev[prev.bbrID==p.bbrID]
                hit = pp[pp[metric]<rank] if rankstrict=='lt' else pp[pp[metric]<=rank]
                if len(hit)==0: continue
                stars.append((p['name'],bool(p.team_change)))
            if len(stars)<3 or not any(tc for _,tc in stars): continue
            if superstar:
                ok=False
                for n,_ in stars:
                    pid=cur[cur.name==n].bbrID.iloc[0]
                    sp=w[(w.bbrID==pid)&(w.season_abbr==Y-1)]
                    if ((sp[metric]<5) if rankstrict=='lt' else (sp[metric]<=5)).any(): ok=True
                if not ok: continue
            out[(int(Y),tm)]=stars
    return out

metricmap={'ws48':'rank_ws48','vorp':'rank_vorp','per':'rank_per','allNBA':'allNBA'}

def show(label,**kw):
    r=teams(**kw)
    print(label, len(r))
    print(sorted(r.keys()))

if __name__=='__main__':
    show('Andy 34 ws top15 3', metric='rank_ws48',age=34,rank=15,yrs=3)
    show('Ian 32 vorp top20 3', metric='rank_vorp',age=32,rank=20,yrs=3)
    show('Todd 40 ws top15 2', metric='rank_ws48',age=40,rank=15,yrs=2)
    show('Nick 40 vorp top20 1', metric='rank_vorp',age=40,rank=20,yrs=1)
