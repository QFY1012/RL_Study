import pandas as pd, numpy as np, json
pd.set_option('display.width', 300); pd.set_option('display.max_rows', 600)
facts = json.load(open('facts.json'))
bad = 0
for f in facts:
    ns = {}
    for var, path in f['tables'].items():
        ns[var] = pd.read_csv(path)
    print('='*78); print('[' + f['id'] + ']')
    try:
        v = eval(f['code'], {'pd': pd, 'np': np}, ns)
        print(v)
    except Exception as e:
        print('ERROR:', repr(e)); bad += 1; continue
    print('-'*78); print('CLAIM: ' + f['claim'])
print('\n\nFAILED:', bad, 'of', len(facts))
