"""Verify every fact in facts.json the same way the grader would."""
import json, sys
import pandas as pd
import numpy as np

facts = json.load(open('facts.json'))
ok = True
for f in facts:
    env = {}
    for var, path in f['tables'].items():
        env[var] = pd.read_csv(path)
    env.update({'pd': pd, 'np': np})
    try:
        value = eval(f['code'], {'pd': pd, 'np': np}, env)
    except Exception as e:
        print(f"### {f['id']}: ERROR {type(e).__name__}: {e}")
        ok = False
        continue
    print(f"### {f['id']}")
    print(value)
    print()
print('ids unique:', len({f['id'] for f in facts}) == len(facts), len(facts), 'facts')
