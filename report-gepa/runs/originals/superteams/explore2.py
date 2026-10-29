import pandas as pd, numpy as np
w=pd.read_csv('data/web.csv')
# explode multi-team rows
e=w.assign(tm=w.tm.str.split(',')).explode('tm')
e=e.reset_index(drop=True)

def teams(metric='rank_ws48', age=34, rank=15, yrs=3, superstar=True, agestrict='lt', rankstrict='lt'):
    out={}
    for Y in sorted(e.season_abbr.unique()):
        cur=e[e.season_abbr==Y]
        prev=e[(e.season_abbr>=Y-yrs)&(e.season_abbr<=Y-1)]
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
                    pid=grp[grp.name==n].bbrID.iloc[0]
                    sp=w[(w.bbrID==pid)&(w.season_abbr==Y-1)]
                    if ((sp[metric]<5) if rankstrict=='lt' else (sp[metric]<=5)).any(): ok=True
                if not ok: continue
            out[(int(Y),tm)]=stars
    return out

if __name__=='__main__':
    for lab,kw in [('Andy',dict(metric='rank_ws48',age=34,rank=15,yrs=3)),
                   ('Ian',dict(metric='rank_vorp',age=32,rank=20,yrs=3)),
                   ('Todd',dict(metric='rank_ws48',age=40,rank=15,yrs=2)),
                   ('Nick',dict(metric='rank_vorp',age=40,rank=20,yrs=1))]:
        r=teams(**kw)
        print(lab,len(r))
        for k,v in sorted(r.items()): print('   ',k,[x[0] for x in v])
