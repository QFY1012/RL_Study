import json,pandas as pd,numpy as np
for f in json.load(open('facts.json')):
    env={'pd':pd,'np':np}
    for k,v in f['tables'].items(): env[k]=pd.read_csv(v)
    print('==',f['id'],'\n',f['claim']); print(eval(f['code'],env)); print()
