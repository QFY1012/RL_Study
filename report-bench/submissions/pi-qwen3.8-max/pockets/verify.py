import json, sys
import pandas as pd, numpy as np

pd.set_option('display.width', 200)
pd.set_option('display.max_columns', 60)
pd.set_option('display.max_rows', 400)

facts = json.load(open('facts.json'))
ids = [f['id'] for f in facts]
assert len(ids) == len(set(ids)), 'duplicate ids'

for f in facts:
    ns = {'pd': pd, 'np': np}
    for var, path in f['tables'].items():
        ns[var] = pd.read_csv(path)
    try:
        val = eval(f['code'], ns)
    except Exception as e:
        print('!! ERROR', f['id'], type(e).__name__, e)
        continue
    print('=' * 100)
    print('ID:', f['id'])
    print('CLAIM:', f['claim'])
    print('CODE:', f['code'])
    print('--- PRINTOUT ---')
    print(val)
print('=' * 100)
print('facts:', len(facts))
