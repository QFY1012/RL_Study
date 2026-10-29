import pandas as pd, numpy as np
w=pd.read_csv('data/web.csv')
parts=w.tm.str.split(',')
w=w.assign(tm=[p[-1] if tc else p[0] for p,tc in zip(parts,w.team_change)])

def calc(metric='rank_ws48', age=34, rank=15, yrs=3, ss=True, agelt=True, ranklt=True, ssrank=5):
    # star qualification rows
    if metric=='allNBA':
        q=w[w.allNBA.notna()][['bbrID','season_year']]
    else:
        q=w[(w[metric]<rank) if ranklt else (w[metric]<=rank)][['bbrID','season_year']]
    pairs=w[['bbrID','season_year','age','team_change','tm']].merge(q,on='bbrID',suffixes=('','_q'))
    pairs=pairs[(pairs.season_year_q>=pairs.season_year-yrs)&(pairs.season_year_q<=pairs.season_year-1)]
    pairs=pairs[(pairs.age<age) if agelt else (pairs.age<=age)]
    stars=pairs.drop_duplicates(['bbrID','season_year'])
    # superstar
    if ss:
        if metric=='allNBA':
            sq=w[w.allNBA==1][['bbrID','season_year']]
        else:
            sq=w[(w[metric]<ssrank) if ranklt else (w[metric]<=ssrank)][['bbrID','season_year']]
        sq=sq.assign(season_year=sq.season_year+1, sup=True)
        stars=stars.merge(sq,on=['bbrID','season_year'],how='left')
    else:
        stars=stars.assign(sup=False)
    stars['sup']=stars.sup.fillna(False).astype(bool)
    g=stars.groupby(['season_year','tm']).agg(n=('bbrID','nunique'), acq=('team_change','any'), sup=('sup','any'))
    g=g[(g.n>=3)&g.acq]
    if ss: g=g[g.sup]
    return g

def labels(g):
    return sorted((int(y)+1,t) for y,t in g.index)

if __name__=='__main__':
    for lab,kw in [('Andy',dict(metric='rank_ws48',age=34,rank=15,yrs=3)),
                   ('Ian',dict(metric='rank_vorp',age=32,rank=20,yrs=3)),
                   ('Todd',dict(metric='rank_ws48',age=40,rank=15,yrs=2)),
                   ('Nick',dict(metric='rank_vorp',age=40,rank=20,yrs=1))]:
        g=calc(**kw)
        print(lab,len(g),labels(g))
