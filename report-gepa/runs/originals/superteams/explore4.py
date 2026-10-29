import pandas as pd, numpy as np
w=pd.read_csv('data/web.csv')

def assign_tm(df):
    parts=df.tm.str.split(',')
    return df.assign(tm=[p[-1] if tc else p[0] for p,tc in zip(parts,df.team_change)])

a=assign_tm(w)

def teams(metric='rank_ws48', age=34, rank=15, yrs=3, superstar=True, agestrict='lt', rankstrict='lt'):
    out={}
    for Y in sorted(a.season_year.unique()):
        cur=a[a.season_year==Y]
        prev=a[(a.season_year>=Y-yrs)&(a.season_year<=Y-1)]
        for tm,grp in cur.groupby('tm'):
            stars=[]
            for _,p in grp.iterrows():
                ok_age = p.age<age if agestrict=='lt' else p.age<=age
                if not ok_age: continue
                pp=prev[prev.bbrID==p.bbrID]
                if metric=='allNBA':
                    hit=pp[pp.allNBA.notna()]
                else:
                    hit = pp[pp[metric]<rank] if rankstrict=='lt' else pp[pp[metric]<=rank]
                if len(hit)==0: continue
                stars.append((p['name'],bool(p.team_change)))
            if len(stars)<3 or not any(tc for _,tc in stars): continue
            if superstar:
                ok=False
                for n,_ in stars:
                    pid=grp[grp.name==n].bbrID.iloc[0]
                    sp=a[(a.bbrID==pid)&(a.season_year==Y-1)]
                    if metric=='allNBA':
                        cond=sp.allNBA.notna() & (sp.allNBA==1)
                    else:
                        cond=(sp[metric]<5) if rankstrict=='lt' else (sp[metric]<=5)
                    if cond.any(): ok=True
                if not ok: continue
            out[(int(Y)+1,tm)]=stars
    return out

if __name__=='__main__':
    for lab,kw in [('Andy',dict(metric='rank_ws48',age=34,rank=15,yrs=3)),
                   ('Ian',dict(metric='rank_vorp',age=32,rank=20,yrs=3)),
                   ('Todd',dict(metric='rank_ws48',age=40,rank=15,yrs=2)),
                   ('Nick',dict(metric='rank_vorp',age=40,rank=20,yrs=1))]:
        r=teams(**kw)
        print(lab,len(r))
        for k,v in sorted(r.items()): print('   ',k,[x[0] for x in v])
