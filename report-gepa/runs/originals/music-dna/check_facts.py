import json, pandas as pd, numpy as np
pd.set_option('display.width',300); pd.set_option('display.max_columns',50); pd.set_option('display.max_colwidth',100)
facts=json.load(open('facts.json'))
for f in facts:
    print('\n================',f['id'])
    print('SOURCE:',f['source'])
    print('CLAIM :',f['claim'])
    env={}
    for var,path in f['tables'].items():
        env[var]=pd.read_csv(path)
    try:
        val=eval(f['code'],{'pd':pd,'np':np},env)
        print(val)
    except Exception as ex:
        print('ERROR',type(ex).__name__,ex)
