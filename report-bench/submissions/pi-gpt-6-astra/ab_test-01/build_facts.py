import json
import pandas as pd
import numpy as np
from pathlib import Path
facts=[]
base="d.assign(group=d.group.str.strip().map({'对照组':'Control','实验组':'Test'}))"
dep=".assign(department=d.department.map({'儿科':'Pediatrics','内科':'Internal medicine','皮肤科':'Dermatology','妇科':'Gynecology','五官科':'ENT / eye / oral'}))"
def add(id,claim,code):
 facts.append(dict(id=id,claim=claim,tables={'d':'data/data.csv'},code=code))
add('study-scope','The data contains 18,000 users with unique IDs, entering from November 18 to December 29, 2024; there are 9,013 control users and 8,987 test users.',"pd.concat([d.agg(rows=('user_id','size'),unique_users=('user_id','nunique')).user_id, pd.to_datetime(d.enter_date,format='mixed').agg(['min','max']), "+base+".groupby('group').size()])")
add('completion-flat','Completion is 88.02% in control (7,933 of 9,013 users) and 87.94% in test (7,903 of 8,987 users).',base+".groupby('group').agg(users=('user_id','size'),completed=('is_completed','sum'),completion_pct=('is_completed',lambda s: s.mean()*100)).round(2)")
add('response-faster','Among recorded responses, the median is 110 seconds in control and 88 seconds in test; the 90th percentile is 234 versus 177 seconds, based on 8,586 and 8,511 responses respectively.',base+".groupby('group').first_response_seconds.agg(recorded='count',median_seconds='median',p90_seconds=lambda s:s.quantile(.9))")
add('early-loss','Before-doctor loss is 4.74% in control (427 users) and 5.30% in test (476 users).',base+".groupby('group').lost_before_doctor.agg(users_lost='sum',loss_pct=lambda s:s.mean()*100).round(2)")
add('department-completion','Test versus control completion is 80.51% versus 85.04% in Dermatology, 88.07% versus 87.54% in ENT / eye / oral, 89.28% versus 89.04% in Gynecology, 89.12% versus 88.64% in Internal medicine, and 90.37% versus 88.94% in Pediatrics.',base+dep+".groupby(['department','group']).is_completed.mean().mul(100).unstack().round(2)")
add('department-differences','The test-minus-control completion gap is −4.54 percentage points in Dermatology, +0.53 in ENT / eye / oral, +0.24 in Gynecology, +0.47 in Internal medicine and +1.44 in Pediatrics.',base+dep+".groupby(['department','group']).is_completed.mean().unstack().eval('(Test - Control)*100').round(2)")
add('dermatology-loss','Dermatology has 1,618 control users and 1,503 test users; before-doctor loss rises from 7.66% (124 users) in control to 12.71% (191 users) in test.',base+".loc[d.department.eq('皮肤科')].groupby('group').lost_before_doctor.agg(users='size',lost='sum',loss_pct=lambda s:s.mean()*100).round(2)")
add('department-mix','Pediatrics accounts for 5,246 users (29.14%) and Internal medicine for 5,083 (28.24%), followed by Dermatology with 3,121 (17.34%), Gynecology with 2,490 (13.83%), and ENT / eye / oral with 2,060 (11.44%).',base+dep+".groupby('department').size().sort_values(ascending=False).to_frame('users').assign(share_pct=lambda t:t.users/t.users.sum()*100).round(2)")
add('other-outcomes','Mean consultation duration among completed consultations is 13.09 minutes in control and 11.67 in test; recorded seven-day follow-up is 12.31% of 8,923 control users and 12.15% of 8,891 test users.',base+".groupby('group').agg(mean_consult_minutes=('consult_minutes','mean'),followup_observed=('followup_7d','count'),followup_pct=('followup_7d',lambda s:s.mean()*100)).round(2)")
add('data-quality','There are 19 group labels with surrounding whitespace, 903 missing response times, 2,164 missing consultation durations, 186 missing follow-up values, 36 missing complaints and 6 missing platform values.',"pd.concat([pd.Series({'group_labels_with_whitespace':d.group.ne(d.group.str.strip()).sum()}),d[['first_response_seconds','consult_minutes','followup_7d','chief_complaint','platform']].isna().sum()])")
add('timing-coverage','All 903 missing response times belong to users lost before a doctor, and all 2,164 missing consultation durations belong to users who did not complete.',"pd.Series({'missing_response':d.first_response_seconds.isna().sum(),'missing_response_and_lost':(d.first_response_seconds.isna() & d.lost_before_doctor.eq(1)).sum(),'missing_duration':d.consult_minutes.isna().sum(),'missing_duration_and_incomplete':(d.consult_minutes.isna() & d.is_completed.eq(0)).sum()})")
add('common-complaints','The three most frequent recorded complaints are ear pain with repeated touching (1,082 users), a three-day cough that worsens at night (1,072), and diarrhea with a low fever for one day (1,048).',"d.chief_complaint.value_counts().head(3).rename(index={'耳朵疼,总用手去抓':'Ear pain with repeated touching','咳嗽三天,夜里咳得更厉害':'Three-day cough, worse at night','腹泻伴低烧一天':'Diarrhea with low fever for one day'})")
with open('facts.json','w') as f:
 f.write('[\n')
 for i,fact in enumerate(facts):
  f.write((',' if i else '')+json.dumps(fact,ensure_ascii=False,indent=2)+'\n')
 f.write(']\n')
for fact in facts:
 env={k:pd.read_csv(v) for k,v in fact['tables'].items()}
 result=eval(fact['code'],{'pd':pd,'np':np},env)
 print('\n'+fact['id']+'\n'+fact['claim']);print(result)
