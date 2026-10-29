import json

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

facts = [
 {"id":"andy-larsen-criteria-seven-teams",
  "source":"7 teams meet this criteria",
  "claim":"The Andy Larsen criteria produce 7 superteams: 2017 GSW, 2011 MIA, 2005 SAS, 1999 SAS, 1987 MIL, 1987 DET and 1983 PHI.",
  "tables":{"web":"data/web.csv"},
  "code":make("rank_ws48",34,15,3,True)},
 {"id":"ian-levy-criteria-seventeen-teams",
  "source":"17 teams meet this criteria",
  "claim":"The Ian Levy criteria produce 17 superteams: 2017 GSW, 2011 ORL, 2011 MIA, 2003 LAC, 1995 ORL, 1994 CHH, 1993 PHO, 1991 POR, 1987 PHI, 1987 MIL, 1986 NJN, 1985 WSB, 1985 BOS, 1983 PHI, 1980 BOS, 1979 NYK and 1978 DEN.",
  "tables":{"web":"data/web.csv"},
  "code":make("rank_vorp",32,20,3,True)},
 {"id":"todd-whitehead-criteria-seven-teams",
  "source":"7 teams meet this criteria",
  "claim":"The Todd Whitehead criteria produce 7 superteams: 2017 SAS, 2017 GSW, 2011 MIA, 2004 LAL, 2002 SAS, 1987 MIL and 1983 PHI.",
  "tables":{"web":"data/web.csv"},
  "code":make("rank_ws48",40,15,2,True)},
 {"id":"nick-sciria-criteria-eight-teams",
  "source":"8 teams meet this criteria",
  "claim":"The Nick Sciria criteria produce 8 superteams: 2017 GSW, 2004 LAL, 1995 ORL, 1994 CHH, 1987 MIL, 1983 PHI, 1979 NYK and 1978 DEN.",
  "tables":{"web":"data/web.csv"},
  "code":make("rank_vorp",40,20,1,True)},
 {"id":"default-settings-eleven-teams",
  "source":"11 teams meet this criteria",
  "claim":"The default settings produce 11 superteams: 2015 CLE, 2011 MIA, 2008 BOS, 2001 ORL, 1989 HOU, 1989 ATL, 1983 PHI, 1981 BOS, 1981 MIL, 1980 PHO and 1979 DEN.",
  "tables":{"web":"data/web.csv"},
  "code":make("rank_per",34,25,1,False)},
]
with open('facts.json','w') as f:
    json.dump(facts,f,indent=2,ensure_ascii=False)
print(json.dumps(facts,indent=2)[:2000])
