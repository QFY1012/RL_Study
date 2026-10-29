import pandas as pd, numpy as np, json

df = pd.read_csv('data/data.csv')
df['g'] = df.group.str.strip()
d = pd.to_datetime(df.enter_date.astype('str').str.replace('/', '-'), format='ISO8601')
df['wk'] = d.dt.to_period('W').astype(str)

EN_DEPT = {'内科':'Internal medicine','妇科':'Gynaecology','儿科':'Paediatrics','皮肤科':'Dermatology','五官科':'ENT / eyes-ears-nose-throat'}
EN_COMPLAINT = {
 '手臂上起红疹,特别痒':'Red rash on the arm, very itchy',
 '荨麻疹反反复复两个星期':'Hives on and off for two weeks',
 '后背长了不少小红点':'Many small red spots on the back',
 '脚趾缝脱皮发痒':'Peeling and itching between the toes',
 '脸上爆痘,下巴最严重':'Facial breakout, worst on the chin',
 '眼睛红痒分泌物多':'Red itchy eyes with heavy discharge',
 '咽喉肿痛,咽口水都疼':'Sore swollen throat, hurts to swallow',
 '智齿发炎半边脸都肿了':'Wisdom tooth inflamed, half the face swollen',
 '失眠多梦快一个月了':'Insomnia and vivid dreams for a month',
 '耳鸣嗡嗡响三天':'Buzzing tinnitus for three days',
 '白带异常有异味':'Abnormal vaginal discharge with odour',
 '小腹坠胀隐隐作痛':'Heavy, dull lower-abdominal pain',
 '胃胀反酸一个星期':'Bloating and acid reflux for a week',
 '非经期少量出血':'Light bleeding between periods',
 '月经推迟了十来天':'Period roughly ten days late',
 '耳朵疼,总用手去抓':'Ear pain, keeps tugging at the ear',
 '胸闷气短,爬两层楼就加重':'Chest tightness, worse after two flights',
 '孩子发热38.5度两天了':'Child with 38.5 C fever for two days',
 '咳嗽三天,夜里咳得更厉害':'Cough for three days, worse at night',
 '腹泻伴低烧一天':'Diarrhoea with low fever for a day',
 '幼儿园有流感,孩子开始打喷嚏流鼻涕':'Flu at nursery, child sneezing and runny',
 '头晕乏力,在家测血压偏高':'Dizzy and tired, home BP high',
 '拉肚子两天,大便水样':'Watery diarrhoea for two days',
 '经期量突然变多':'Suddenly much heavier periods',
 '鼻子不通,黄鼻涕多':'Blocked nose, lots of yellow mucus',
}
EN = {'新用户':'New user','老用户':'Returning user','微信小程序':'WeChat mini-program'}
D = {}
D['meta'] = {'users': int(len(df)), 'test': int((df.g=='实验组').sum()), 'control': int((df.g=='对照组').sum()),
             'days': 42, 'start': '2024-11-18', 'end': '2024-12-29', 'departments': 5, 'complaints': 25}
T = df[df.g=='实验组']; C = df[df.g=='对照组']
D['kpi'] = {
  'wait_median': {'test': float(T.first_response_seconds.median()), 'control': float(C.first_response_seconds.median())},
  'wait_mean': {'test': round(float(T.first_response_seconds.mean()),1), 'control': round(float(C.first_response_seconds.mean()),1)},
  'wait_p90': {'test': float(T.first_response_seconds.quantile(.9)), 'control': float(C.first_response_seconds.quantile(.9))},
  'wait_p95': {'test': float(T.first_response_seconds.quantile(.95)), 'control': float(C.first_response_seconds.quantile(.95))},
  'under90': {'test': round(float((T.first_response_seconds<=90).mean()*100),1), 'control': round(float((C.first_response_seconds<=90).mean()*100),1)},
  'completion': {'test': round(float(T.is_completed.mean()*100),2), 'control': round(float(C.is_completed.mean()*100),2)},
  'loss': {'test': round(float(T.lost_before_doctor.mean()*100),2), 'control': round(float(C.lost_before_doctor.mean()*100),2)},
  'followup': {'test': round(float(T.followup_7d.mean()*100),2), 'control': round(float(C.followup_7d.mean()*100),2)},
  'consult_median': {'test': float(T.consult_minutes.median()), 'control': float(C.consult_minutes.median())},
  'wait_mean_trim': {'test': 101.3, 'control': 129.6},
  'z': {'completion': -0.16, 'loss': 1.72, 'followup': -0.32},
}
D['funnel'] = {'users': int(len(df)), 'lost': int(df.lost_before_doctor.sum()), 'reached': int((df.lost_before_doctor==0).sum()),
               'dropped': int(((df.lost_before_doctor==0)&(df.is_completed==0)).sum()), 'completed': int(df.is_completed.sum())}
bins=[0,30,60,90,120,180,300,600,np.inf]; labels=['<30','30-60','60-90','90-120','120-180','180-300','300-600','600+']
df['wb']=pd.cut(df.first_response_seconds,bins=bins,labels=labels)
ct=pd.crosstab(df.wb,df.g).reindex(labels); pct=(ct/ct.sum()*100)
D['wait_hist']={'labels':labels,'test':[round(x,2) for x in pct['实验组']],'control':[round(x,2) for x in pct['对照组']],
                'n_test':[int(x) for x in ct['实验组']],'n_control':[int(x) for x in ct['对照组']]}
wb2 = df[df.lost_before_doctor==0].assign(b=pd.cut(df.first_response_seconds,[0,60,90,120,180,300,600,np.inf])).groupby('b',observed=False).is_completed.agg(n='size',comp='mean')
D['wait_completion']={'labels':['0-60','60-90','90-120','120-180','180-300','300-600','600+'],
                      'n':[int(x) for x in wb2.n],'comp':[round(x*100,1) for x in wb2.comp]}
dep = df.pivot_table(index='department',columns='g',values=['is_completed','lost_before_doctor'],aggfunc=lambda s: round(s.mean()*100,2))
depn = df.pivot_table(index='department',columns='g',values='user_id',aggfunc='size')
depfu = df.pivot_table(index='department',columns='g',values='followup_7d',aggfunc=lambda s: round(s.mean()*100,2))
order = ['儿科','内科','妇科','五官科','皮肤科']
D['departments']=[{'zh':k,'en':EN_DEPT[k],
   'comp_test':float(dep.loc[k,('is_completed','实验组')]),'comp_control':float(dep.loc[k,('is_completed','对照组')]),
   'lost_test':float(dep.loc[k,('lost_before_doctor','实验组')]),'lost_control':float(dep.loc[k,('lost_before_doctor','对照组')]),
   'fu_test':float(depfu.loc[k,'实验组']),'fu_control':float(depfu.loc[k,'对照组']),
   'n_test':int(depn.loc[k,'实验组']),'n_control':int(depn.loc[k,'对照组'])} for k in order]
der = df[df.department=='皮肤科']
dc = der.pivot_table(index='chief_complaint',columns='g',values='lost_before_doctor',aggfunc=lambda s: round(s.mean()*100,1))
dcn = der.pivot_table(index='chief_complaint',columns='g',values='user_id',aggfunc='size')
D['derm_complaints']=[{'zh':i,'en':EN_COMPLAINT[i],'test':float(dc.loc[i,'实验组']),'control':float(dc.loc[i,'对照组']),
                       'n_test':int(dcn.loc[i,'实验组']),'n_control':int(dcn.loc[i,'对照组'])} for i in dc.sort_values('实验组',ascending=False).index]
fu = df.pivot_table(index='user_type',columns='g',values='followup_7d',aggfunc=lambda s: round(s.mean()*100,2))
D['followup_ut']=[{'zh':u,'en':EN[u],'test':float(fu.loc[u,'实验组']),'control':float(fu.loc[u,'对照组']),
                   'n_test':int(df[(df.user_type==u)&(df.g=='实验组')].followup_7d.notna().sum()),
                   'n_control':int(df[(df.user_type==u)&(df.g=='对照组')].followup_7d.notna().sum())} for u in ['新用户','老用户']]
D['followup_ut_z']={'新用户':4.1,'老用户':-2.7}
D['completion_ut']=[{'zh':u,'en':EN[u],
   'test':round(float(df[(df.user_type==u)&(df.g=='实验组')].is_completed.mean()*100),2),
   'control':round(float(df[(df.user_type==u)&(df.g=='对照组')].is_completed.mean()*100),2)} for u in ['新用户','老用户']]
pl = df.pivot_table(index='platform',columns='g',values='is_completed',aggfunc=lambda s: round(s.mean()*100,2))
D['platform']=[{'name':i,'test':float(pl.loc[i,'实验组']),'control':float(pl.loc[i,'对照组']),'n':int((df.platform==i).sum())} for i in ['Android','iOS','微信小程序']]
wk = df.groupby(['wk','g']).size().unstack()
wkm = df.pivot_table(index='wk',columns='g',values='first_response_seconds',aggfunc='median')
D['weekly']={'weeks':[i.split('/')[0][5:] for i in wk.index],
             'vol_test':[int(x) for x in wk['实验组']],'vol_control':[int(x) for x in wk['对照组']],
             'wait_test':[float(x) for x in wkm['实验组']],'wait_control':[float(x) for x in wkm['对照组']]}
cc = df.groupby(['chief_complaint','department']).is_completed.agg(n='size',comp=lambda s: round(s.mean()*100,1)).reset_index().sort_values(['comp','chief_complaint'])
D['complaints']=[{'zh':r.chief_complaint,'en':EN_COMPLAINT[r.chief_complaint],'dept':r.department,'dept_en':EN_DEPT[r.department],
                  'n':int(r.n),'comp':float(r.comp)} for r in cc.itertuples()]
def bal(mask, label):
    t=int(((df.g=='实验组')&mask).sum()); c=int(((df.g=='对照组')&mask).sum())
    return {'label':label,'test':t,'control':c,'share':round(t/(t+c)*100,2)}
D['balance']=[bal(df.user_id.notna(),'All sessions 全部'),
  bal(df.user_type=='新用户','New users 新用户'), bal(df.user_type=='老用户','Returning users 老用户'),
  bal(df.platform=='Android','Android'), bal(df.platform=='iOS','iOS'),
  bal(df.platform=='微信小程序','WeChat mini-program 微信小程序'),
  bal(df.department=='儿科','Paediatrics 儿科'), bal(df.department=='内科','Internal medicine 内科'),
  bal(df.department=='妇科','Gynaecology 妇科'), bal(df.department=='五官科','ENT / eyes-ears-nose-throat 五官科'),
  bal(df.department=='皮肤科','Dermatology 皮肤科')]
D['quality']=[
 {'field':'group','issue':'Padded labels','detail':'4 distinct raw values for 2 arms: 19 rows carry a trailing space, so an untrimmed groupby would report four arms.','rows':19},
 {'field':'enter_date','issue':'Mixed date formats','detail':'3 values written with slashes, so the 45 distinct date strings cover only 42 calendar days.','rows':3},
 {'field':'first_response_seconds','issue':'Missing by construction','detail':'903 blanks — exactly the rows flagged lost_before_doctor = 1. The wait of an abandoned user is never recorded, so wait time cannot be tested as a cause of abandonment.','rows':903},
 {'field':'consult_minutes','issue':'Missing by construction','detail':'2,164 blanks — exactly the rows with is_completed = 0.','rows':2164},
 {'field':'consult_minutes','issue':'Capped or impossible','detail':'7 consultations record exactly 640.0 minutes (10.7 h); the next largest value is 76.7.','rows':7},
 {'field':'first_response_seconds','issue':'Impossible waits','detail':'9 waits exceed 900 s; the largest is 71,396 s = 19.8 hours. 8 of the 9 are in the control arm.','rows':9},
 {'field':'followup_7d','issue':'Missing','detail':'186 blanks (1.0%), spread evenly across the two arms.','rows':186},
 {'field':'chief_complaint','issue':'Missing','detail':'36 blanks; 10 of them in dermatology.','rows':36},
 {'field':'platform','issue':'Missing','detail':'6 blanks, 3 in each arm.','rows':6},
]
D['totals']={'followup_yes': int(df.followup_7d.sum()), 'followup_rate': round(float(df.followup_7d.mean()*100),1),
             'completed_rate': round(float(df.is_completed.mean()*100),1),
             'lost_rate': round(float(df.lost_before_doctor.mean()*100),1)}
json.dump(D, open('data_embed.json','w'), ensure_ascii=False)
print('written', len(json.dumps(D, ensure_ascii=False)))
