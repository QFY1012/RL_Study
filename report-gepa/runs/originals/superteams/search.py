import pandas as pd, numpy as np, itertools
w=pd.read_csv('data/web.csv')
e=w.assign(tm=w.tm.str.split(',')).explode('tm').reset_index(drop=True)

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
                    sp=w[(w.bbrID==pid)&(w.season_abbr==Y-1)]
                    if metric=='allNBA':
                        cond=sp.allNBA.notna() & (sp.allNBA==1)
                    else:
                        cond=(sp[metric]<5) if rankstrict=='lt' else (sp[metric]<=5)
                    if cond.any(): ok=True
                if not ok: continue
            out[(int(Y),tm)]=stars
    return out

T={(15,'CLE'),(11,'MIA'),(8,'BOS'),(1,'ORL'),(89,'HOU'),(89,'ATL'),(83,'PHI'),(81,'BOS'),(81,'MIL'),(80,'PHO'),(79,'DEN')}
print('target',len(T))
metrs=['rank_ws48','rank_vorp','rank_per','rank_pie','allNBA']
best=[]
for m in metrs:
 for age in [29,30,31,32,33,34,39,40]:
  for rank in [10,15,20,25,30]:
   for yrs in [1,2,3]:
    for ss in [True,False]:
     for ag in ['lt','le']:
      for rk in ['lt','le']:
       r=teams(metric=m,age=age,rank=rank,yrs=yrs,superstar=ss,agestrict=ag,rankstrict=rk)
       s=set(r)
       inter=len(s&T); j=inter/len(s|T) if s|T else 0
       best.append((j,inter,len(s),m,age,rank,yrs,ss,ag,rk))
best.sort(reverse=True)
for b in best[:20]: print(b)
