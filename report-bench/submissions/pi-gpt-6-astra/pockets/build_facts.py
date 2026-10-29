import pandas as pd
import numpy as np
import json
facts=[]
def add(id,claim,code):
    facts.append(dict(id=id,claim=claim,tables={'jeans':'data/measurements.csv'},code=code))
add('sample-coverage','The sample contains 80 jeans entries across 20 brands after trimming spaces and ignoring brand-name capitalization, with 40 entries for men and 40 for women.',"pd.Series({'Total entries': len(jeans), 'Normalized brands': jeans.brand.str.strip().str.lower().nunique(), 'Men entries': jeans.menWomen.eq('men').sum(), 'Women entries': jeans.menWomen.eq('women').sum()})")
add('average-dimensions','Mean maximum front height is 14.33 for women versus 23.13 for men, front width is 15.18 versus 16.37, back height is 15.12 versus 16.01, and back width is 13.34 versus 13.70, in recorded units.',"jeans.groupby('menWomen')[['maxHeightFront','maxWidthFront','maxHeightBack','maxWidthBack']].mean().round(2)")
add('relative-dimension-gaps','Compared with men, women have 38.1% lower mean maximum front height, 7.2% lower front width, 5.5% lower back height and 2.6% lower back width.',"jeans.groupby('menWomen')[['maxHeightFront','maxWidthFront','maxHeightBack','maxWidthBack']].mean().pipe(lambda m: (100 * (1 - m.loc['women'] / m.loc['men'])).round(1))")
brand="jeans.assign(brand=jeans.brand.str.strip().str.lower()).groupby(['brand','menWomen']).maxHeightFront.mean().unstack().assign(gap=lambda d: d['men']-d['women'])"
add('brand-means','The largest brand-level gap in mean maximum front height is at Levi’s, with men at 25.75 and women at 12.35 (a gap of 13.40); the smallest is at Abercrombie, with men at 22.25 and women at 19.75 (a gap of 2.50).',brand+".sort_values('gap', ascending=False).round(2)")
add('every-brand-gap','All 20 normalized brands have a higher mean maximum front height for men than for women, and every brand has two entries per gender.',"jeans.assign(brand=jeans.brand.str.strip().str.lower()).groupby(['brand','menWomen']).agg(height=('maxHeightFront','mean'), entries=('brand','size')).unstack().pipe(lambda d: pd.Series({'Brands with men higher': (d['height']['men'] > d['height']['women']).sum(), 'Total brands': len(d), 'Minimum entries per brand and gender': d['entries'].min().min(), 'Maximum entries per brand and gender': d['entries'].max().max()}))")
add('skinny-comparison','Among entries labeled skinny after trimming spaces, mean maximum front height is 14.27 for 20 women’s entries versus 22.71 for 12 men’s entries.',"jeans[jeans['style'].str.strip().eq('skinny')].groupby('menWomen').agg(entries=('brand','size'),mean_front_height=('maxHeightFront','mean')).round(2)")
with open('facts.json','w') as f:
    json.dump(facts,f,indent=2,ensure_ascii=False)
for fact in facts:
    scope={k:pd.read_csv(v) for k,v in fact['tables'].items()}
    print('\n'+fact['id']+'\n'+fact['claim'])
    print(eval(fact['code'],{'pd':pd,'np':np},scope))
