import json
T={"d":"data/data.csv"}
G="d.group.str.strip().map({'实验组':'treatment','对照组':'control'})"
DEP="{'儿科':'Pediatrics','内科':'Internal medicine','皮肤科':'Dermatology','妇科':'Gynecology','五官科':'ENT & eye'}"
UT="{'新用户':'new','老用户':'returning'}"
DATE="pd.to_datetime(d.enter_date.str.replace('/','-'))"
PER=f"np.where({DATE} >= '2024-12-09', 'b: Dec 9-29', 'a: Nov 18-Dec 8')"
F=[
("groups-balanced","The 18,000 users split almost evenly: 9,013 in the control group and 8,987 in the treatment group.",
 f"{G}.value_counts()"),
("group-label-spaces","19 rows carry a group label with a trailing space and must be trimmed before grouping.",
 "d.group.str.endswith(' ').sum()"),
("date-format-mixed","3 rows write the entry date with slashes (2024/12/02, 2024/12/19, 2024/12/27) instead of dashes.",
 "d.enter_date[d.enter_date.str.contains('/')].tolist()"),
("funnel","Of 18,000 users, 903 left before reaching a doctor, 1,261 reached a doctor but did not complete, and 15,836 completed the consultation.",
 "pd.Series({'left before doctor': d.lost_before_doctor.sum(), 'reached doctor, not completed': ((d.lost_before_doctor == 0) & (d.is_completed == 0)).sum(), 'completed': d.is_completed.sum()})"),
("dept-sizes","Pediatrics (5,246 users) and internal medicine (5,083) are the largest departments, ahead of dermatology (3,121), gynecology (2,490) and ENT & eye (2,060).",
 f"d.department.map({DEP}).value_counts()"),
("median-response","The treatment group got a first doctor response in a median of 88 seconds, against 110 seconds in the control group.",
 f"d.groupby({G}).first_response_seconds.median()"),
("daily-response","The treatment group had the lower median first-response time on 39 of the 42 days.",
 f"d.groupby([{DATE}, {G}]).first_response_seconds.median().unstack().pipe(lambda t: pd.Series({{'days': len(t), 'treatment lower': (t.treatment < t.control).sum()}}))"),
("response-by-period","From 9 December waits rose in both groups: the control median went from 86 to 132 seconds, the treatment median from 77 to 96, so the gap widened from 9 to 36 seconds.",
 f"d.groupby([{PER}, {G}]).first_response_seconds.median().unstack()"),
("volume-by-period","Traffic grew: 9,909 users entered in the 21 days from 9 December against 8,091 in the 21 days before.",
 f"d.groupby({PER}).agg(users=('user_id', 'size'), days=('enter_date', lambda s: s.str.replace('/', '-').nunique()))"),
("overall-outcomes","Overall the test barely moved outcomes: 5.3% of treatment users left before a doctor versus 4.7% of control, and 87.9% versus 88.0% completed.",
 f"d.groupby({G})[['lost_before_doctor', 'is_completed']].mean().mul(100).round(1)"),
("dept-lost","Dermatology is the outlier: 12.7% of treatment users left before reaching a doctor versus 7.7% in control, while in every other department the two groups are within 1 point (e.g. pediatrics 2.5% vs 3.1%).",
 f"d.groupby([d.department.map({DEP}), {G}]).lost_before_doctor.mean().mul(100).round(1).unstack()"),
("derm-completion","In dermatology, completion fell to 80.5% in the treatment group from 85.0% in control; in every other department treatment completed at least as often as control.",
 f"d.groupby([d.department.map({DEP}), {G}]).is_completed.mean().mul(100).round(1).unstack()"),
("derm-all-complaints","All 5 dermatology complaints show a higher pre-doctor loss rate in the treatment group than in control, from 11.7% vs 6.0% (toe-web peeling) to 13.9% vs 6.9% (red spots on the back).",
 f"d[d.department == '皮肤科'].groupby([d.chief_complaint.map({{'后背长了不少小红点':'red spots on the back','手臂上起红疹,特别痒':'itchy red rash on arm','脚趾缝脱皮发痒':'toe-web peeling','脸上爆痘,下巴最严重':'facial acne','荨麻疹反反复复两个星期':'recurring hives'}}), {G}]).lost_before_doctor.mean().unstack().mul(100).round(1).assign(treatment_higher=lambda t: t.treatment > t.control)"),
("derm-z","The dermatology loss gap has a z-score of 4.65, while the overall loss gap across all departments has a z-score of 1.72.",
 f"pd.Series({{k: (lambda a, b: (a.mean() - b.mean()) / np.sqrt(a.var() / len(a) + b.var() / len(b)))(s[s.group.str.strip() == '实验组'].lost_before_doctor, s[s.group.str.strip() == '对照组'].lost_before_doctor) for k, s in {{'dermatology': d[d.department == '皮肤科'], 'all departments': d}}.items()}}).round(2)"),
("non-derm-outcomes","Outside dermatology, treatment users did slightly better: 3.8% left before a doctor versus 4.1% in control, and 89.4% completed versus 88.7%.",
 f"d.groupby([np.where(d.department == '皮肤科', 'dermatology', 'all other departments'), {G}])[['lost_before_doctor', 'is_completed']].mean().mul(100).round(1)"),
("consult-length","Completed consultations were slightly shorter in the treatment group, a median of 10.4 minutes against 11.2 in control.",
 f"d.groupby({G}).consult_minutes.median()"),
("followup-by-usertype","The 7-day follow-up rate rose for new users, 9.8% in treatment versus 6.8% in control, but fell for returning users, 13.2% versus 14.9%.",
 f"d.groupby([d.user_type.map({UT}), {G}]).followup_7d.mean().mul(100).round(1).unstack()"),
("followup-overall","Across all users, 7-day follow-up was essentially unchanged: 12.1% in treatment versus 12.3% in control.",
 f"d.groupby({G}).followup_7d.mean().mul(100).round(1)"),
("consult-640","7 consultations record a length of exactly 640 minutes, far above the next-longest value of 76.7 minutes.",
 "d.consult_minutes.value_counts().sort_index(ascending=False).head(3)"),
("response-outliers","7 users have a first-response time over one hour, all between 15,543 and 71,396 seconds, while the next-largest value is 922 seconds.",
 "d.first_response_seconds.sort_values(ascending=False).head(8).tolist()"),
]
json.dump([{"id":i,"claim":c,"tables":T,"code":k} for i,c,k in F],open('facts.json','w'),ensure_ascii=False,indent=1)
