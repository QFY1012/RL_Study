import json,pandas as pd,numpy as np
with open('facts.json',encoding='utf-8') as f: facts=json.load(f)
assert len({f['id'] for f in facts})==len(facts)
for i,fact in enumerate(facts,1):
    env={'pd':pd,'np':np}
    for var,path in fact['tables'].items(): env[var]=pd.read_csv(path)
    print('\n'+'='*100)
    print(i,fact['id'])
    print(fact['claim'])
    try:
        value=eval(fact['code'],env)
        print(value)
    except Exception as e:
        print(type(e).__name__,e)
        raise
