import json,pandas as pd,numpy as np
pd.set_option('display.width',200)
for f in json.load(open('facts.json')):
    env={k:pd.read_csv(v) for k,v in f['tables'].items()}; env.update(pd=pd,np=np)
    print('##',f['id'],'|',f['claim']); print(eval(f['code'],env)); print()
