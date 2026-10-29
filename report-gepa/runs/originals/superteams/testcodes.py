import pandas as pd, numpy as np

def make(metric, age, rank, yrs, ss):
    ssmerge = ('.merge(d.loc[d.%s < 5, ["bbrID","season_year"]].assign(season_year=lambda x: x.season_year + 1, sup=True), on=["bbrID","season_year"], how="left")\n        .assign(sup=lambda x: x.sup.fillna(False))' % metric) if ss else '.assign(sup=False)'
    ssquery = ' and superstar' if ss else ''
    return f'''(pd.read_csv("data/web.csv")
 .assign(tm=lambda d: np.where(d.team_change, d.tm.str.split(",").str[-1], d.tm.str.split(",").str[0]))
 .pipe(lambda d: d[["bbrID","season_year","age","team_change","tm"]]
        .merge(d.loc[d.{metric} < {rank}, ["bbrID","season_year"]], on="bbrID", suffixes=("","_q"))
        .query("season_year_q >= season_year - {yrs} and season_year_q <= season_year - 1 and age < {age}")
        .drop_duplicates(["bbrID","season_year"])
        {ssmerge}
        .groupby(["season_year","tm"])
        .agg(n=("bbrID","nunique"), acquired=("team_change","any"), superstar=("sup","any"))
        .query("n >= 3 and acquired{ssquery}")
        .reset_index()
        .assign(year=lambda x: x.season_year + 1, total=lambda x: len(x))
        .set_index(["year","tm"])[["n","total"]]
        .sort_index(ascending=False)))'''

specs={'andy':('rank_ws48',34,15,3,True),'ian':('rank_vorp',32,20,3,True),'todd':('rank_ws48',40,15,2,True),'nick':('rank_vorp',40,20,1,True),'default':('rank_per',34,25,1,False)}
for k,(m,a,r,y,s) in specs.items():
    code=make(m,a,r,y,s)
    res=eval(code)
    print('====',k)
    print(res)
    print('rows',len(res))
    open(f'code_{k}.txt','w').write(code)
