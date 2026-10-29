import json

S = "data/songs.csv"
E = "data/samples.csv"
T = {"s": S, "e": E}

def merge_both(expr):
    return expr

facts = []

def add(id, source, claim, code):
    facts.append({"id": id, "source": source, "claim": claim, "tables": T, "code": code})

# 1
add(
"monk-higgins-covers-ray-charles",
"A vertical chain begins with I Believe to My Soul by Ray Charles and continues to I Believe to My Soul by Monk Higgins.",
"Monk Higgins's 1968 recording of I Believe to My Soul samples Ray Charles's 1961 recording.",
"""e[(e.tree=='open') & (e.S_NAME=='I Believe to My Soul') & (e.E_NAME=='I Believe to My Soul')].merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','release_date_child','E_NAME','primary_artist_parent','release_date_parent']]"""
)

# 2
add(
"not-like-us-samples-i-believe",
"The vertical chain connects I Believe to My Soul by Monk Higgins to Not Like Us by Kendrick Lamar.",
"Kendrick Lamar's 2024 Not Like Us samples Monk Higgins's 1968 I Believe to My Soul.",
"""e[(e.tree=='open') & (e.S_NAME=='Not Like Us')].merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','release_date_child','E_NAME','primary_artist_parent','release_date_parent']]"""
)

# 3
add(
"inspector-gadget-samples-in-the-hall",
"The vertical chain connects In the Hall of the Mountain King by Edvard Grieg to Inspector Gadget by Haim Saban.",
"Haim Saban's Inspector Gadget samples Edvard Grieg's In the Hall of the Mountain King.",
"""e[(e.tree=='king') & (e.S_NAME=='Inspector Gadget') & (e.E_NAME=='In the Hall of the Mountain King')].merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','release_date_child','E_NAME','primary_artist_parent','release_date_parent']]"""
)

# 4
add(
"hit-em-up-orchestral-lineage",
"Finally, in 1996, over 120 years after “In the Hall of the Mountain King,” 2pac released the song at the end of this musical lineage, “Hit ’Em Up”“Hit ’Em Up”.",
"Hit 'Em Up's lineage reaches In the Hall of the Mountain King through Player's Anthem, Big Poppa, Bad Boys, and Inspector Gadget, five sample links in all.",
"""e[(e.tree=='king') & e.S_NAME.isin(['Hit ’Em Up','Player’s Anthem','Big Poppa','Bad Boys','Inspector Gadget']) & e.E_NAME.isin(['Player’s Anthem','Big Poppa','Bad Boys','Inspector Gadget','In the Hall of the Mountain King'])][['S_NAME','E_NAME']].assign(links=lambda d: len(d))"""
)

# 5
add(
"isaac-hayes-samples-dionne-warwick",
"The view zooms to another lineage, beginning with Walk on By by Dionne Warwick and continuing to Walk on By by Isaac Hayes.",
"Isaac Hayes's 1969 Walk on By samples Dionne Warwick's 1964 Walk on By.",
"""e[(e.tree=='hit') & (e.S_NAME=='Walk on By') & (e.E_NAME=='Walk on By')].merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','release_date_child','E_NAME','primary_artist_parent','release_date_parent']]"""
)

# 6
add(
"warning-samples-isaac-hayes",
"This catches the ear of Biggie Smalls and forms the basis of his track “Warning”...",
"Warning samples Isaac Hayes's 1969 Walk on By.",
"""e[(e.tree=='hit') & (e.S_NAME=='Warning') & (e.E_NAME=='Walk on By')].merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','release_date_child','E_NAME','primary_artist_parent','release_date_parent']]"""
)

# 7
add(
"hit-em-up-descends-from-warning",
"…and just a few more generations below “Warning” is once again, “Hit ’Em Up.”",
"Hit 'Em Up descends from Warning through Gettin' Money (Get Money Remix) and Get Money, three sample links.",
"""e[(e.tree=='hit') & e['remove'].isna() & e.S_NAME.isin(['Hit ’Em Up','Gettin’ Money (Get Money Remix)','Get Money']) & e.E_NAME.isin(['Gettin’ Money (Get Money Remix)','Get Money','Warning'])].merge(s.drop_duplicates('id')[['id','primary_artist']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','E_NAME','primary_artist_parent']].assign(links=lambda d: len(d))"""
)

# 8
add(
"hit-em-up-hiphop-lineage",
"Stetsasonic’s iconic line “Go Brooklyn” sets out a chain of beats, and lyrics set to those beats, that leads again to “Hit ’Em Up.”",
"Hit 'Em Up descends from Looking Out My Window through 10% Dis, Top Billin', and Go Stetsa I, four sample links.",
"""e[(e.tree=='hit') & e['remove'].isna() & e.S_NAME.isin(['Hit ’Em Up','10% Dis','Top Billin’','Go Stetsa I']) & e.E_NAME.isin(['10% Dis','Top Billin’','Go Stetsa I','Looking Out My Window'])].merge(s.drop_duplicates('id')[['id','primary_artist']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','E_NAME','primary_artist_parent']].assign(links=lambda d: len(d))"""
)

# 9
add(
"hit-em-up-funk-lineage",
"This iconic bass riff is a clear influence on the bassline of Dennis Edwards and Siedah Garrett’s “Don’t Look Any Further.” “Hit ’Em Up” then samples “Don’t Look Any Further’s” bassline.",
"Hit 'Em Up samples Don't Look Any Further, which samples James Brown's Blind Man Can See It, two sample links.",
"""e[(e.tree=='hit') & e.S_NAME.isin(['Hit ’Em Up','Don’t Look Any Further']) & e.E_NAME.isin(['Don’t Look Any Further','Blind Man Can See It'])].merge(s.drop_duplicates('id')[['id','primary_artist']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','E_NAME','primary_artist_parent']].assign(links=lambda d: len(d))"""
)

# 10
add(
"hit-em-up-released-120-years-later",
"Finally, in 1996, over 120 years after “In the Hall of the Mountain King,” 2pac released the song at the end of this musical lineage, “Hit ’Em Up”“Hit ’Em Up”.",
"Hit 'Em Up was released 120.27 years after In the Hall of the Mountain King.",
"""(pd.to_datetime(s.loc[s.title.eq('Hit ’Em Up'),'release_date'].iloc[0])-pd.to_datetime(s.loc[s.title.eq('In the Hall of the Mountain King'),'release_date'].sort_values().iloc[0])).days/365.25"""
)

# 11
add(
"in-the-hall-tree-has-833-songs",
"If we zoom out, we can see them all, and how “In The Hall of the Mountain King” affects music across 5 generations and 833 songs.",
"The In the Hall of the Mountain King tree contains 833 distinct songs with plotted coordinates.",
"""s[s.id.isin(pd.unique(pd.concat([e[e.tree=='king_2'].start_node_id,e[e.tree=='king_2'].end_node_id]))) & s.x.notna()].id.nunique()"""
)

# 12
add(
"in-the-hall-tree-spans-five-generations",
"If we zoom out, we can see them all, and how “In The Hall of the Mountain King” affects music across 5 generations and 833 songs.",
"The descendants of In the Hall of the Mountain King span five generations.",
"""(lambda k, r: __import__('functools').reduce(lambda d,_: pd.concat([d, d.merge(k, left_on='id', right_on='end_node_id')[['start_node_id','gen']].rename(columns={'start_node_id':'id'}).assign(gen=lambda x: x.gen+1)]).drop_duplicates('id', keep='first'), range(10), s[s.id.eq(r)][['id']].assign(gen=0)).gen.max())(e[e.tree=='king_2'][['start_node_id','end_node_id']], s[s.title.eq('In the Hall of the Mountain King')].sort_values('release_date').id.iloc[0])"""
)

# 13
add(
"the-worst-great-great-great-grandchild",
"The descendants of “In the Hall of the Mountain King” include Jhene Aiko’s The Worst The Worst, a great-great-great grandchild of “In the Hall of the Mountain King” due to a shared lineage with “Big Poppa.”",
"The Worst is five sample links below In the Hall of the Mountain King, through Excuse Me Miss, Big Poppa, Bad Boys, and Inspector Gadget.",
"""e[(e.tree=='the worst') & e.S_NAME.isin(['The Worst','Excuse Me Miss','Big Poppa','Bad Boys','Inspector Gadget']) & e.E_NAME.isin(['Excuse Me Miss','Big Poppa','Bad Boys','Inspector Gadget','In the Hall of the Mountain King'])][['S_NAME','E_NAME']].assign(links=lambda d: len(d))"""
)

# 14
add(
"what-if-reaches-in-the-hall",
"But if we take a different route through the family tree, we can even see “In the Hall of the Mountain King” make its way to Korean rap in J-Hope’s song “What if…”",
"What if… reaches In the Hall of the Mountain King through Shimmy Shimmy Ya, Show & Prove, The Show, and Inspector Gadget, five sample links.",
"""e[(e.tree=='king') & e.S_NAME.isin(['What if…','Shimmy Shimmy Ya','Show & Prove','The Show','Inspector Gadget']) & e.E_NAME.isin(['Shimmy Shimmy Ya','Show & Prove','The Show','Inspector Gadget','In the Hall of the Mountain King'])][['S_NAME','E_NAME']].assign(links=lambda d: len(d))"""
)

# 15
add(
"funky-drummer-second-generation",
"“Jenny From the Block” is only one of a whole second generation of songs that originate from Clyde Stubblefield’s improvised drum break 5 minutes and 35 seconds into “Funky Drummer.” There’s also Will Smith’s Wild Wild West Wild Wild West, The Power The Power by SNAP!, Rub You The Right Way Rub You The Right Way by Johnny Gill.",
"Jenny from the Block samples South Bronx, Wild Wild West samples Mama Said Knock You Out, The Power samples Let the Words Flow, and Rub You The Right Way samples Pump Up the Bass; each parent directly samples Funky Drummer.",
"""e[(e.tree=='funky_3') & (((e.S_NAME.isin(['Jenny from the Block','Wild Wild West','The Power','Rub You The Right Way'])) & e.E_NAME.isin(['South Bronx','Mama Said Knock You Out','Let the Words Flow','Pump Up the Bass'])) | (e.S_NAME.isin(['South Bronx','Mama Said Knock You Out','Let the Words Flow','Pump Up the Bass']) & e.E_NAME.eq('Funky Drummer')))][['S_NAME','E_NAME']]"""
)

# 16
add(
"murder-she-wrote-sources-four-modern-songs",
"For example, where does this international selection of hits get their sound? The immediate answer is the 1992 classic “Murder She Wrote” by Chaka Demus and Pliers.",
"Shaky Shaky (2016), Freaks (2013), Post to Be (2014), and Labios Mordidos (2023) all sample Murder She Wrote.",
"""e[(e.tree=='murder') & (e.E_NAME=='Murder She Wrote')].merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='start_node_id', right_on='id')[['S_NAME','primary_artist','release_date']].assign(songs=lambda d: len(d))"""
)

# 17
add(
"stalag-17-sources-murder-she-wrote-and-bam-bam",
"The “Stalag Riddim” and its descendants form the basis for countless Jamaican hits, including “Murder She Wrote” and Sister Nancy’s “Bam Bam.”",
"Both Murder She Wrote (1992) and Bam Bam (1982) directly sample Stalag 17 (1973).",
"""e[(e.tree=='murder') & (e.E_NAME=='Stalag 17')].merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','release_date_child','E_NAME','primary_artist_parent','release_date_parent']]"""
)

# 18
add(
"bam-bam-sources-three-songs",
"Descendants of “Bam Bam” include songs like Do to Me Do to Me by H.E.R., Lost Ones Lost Ones by Lauryn Hill, and Bam Bam by Jay-Z and Damian Marley.",
"Do to Me (2020), Bam (2017), and Lost Ones (1998) directly sample Sister Nancy's 1982 Bam Bam.",
"""e[(e.tree=='murder') & (e.E_NAME=='Bam Bam')].merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','release_date_child','E_NAME','primary_artist_parent','release_date_parent']].assign(songs=lambda d: len(d))"""
)

# 19
add(
"shake-it-three-source-tracks",
"A visual tree that traces the musical influences behind Shake It by Kay Flock, Cardi B & Dougie B (2022), dividing them into three source tracks: melody from Temperature by Sean Paul, lyrics from Bananza (Belly Dancer) by Akon, and bass from Is Ya Ready by Kay Flock.",
"Shake It directly samples Temperature by Sean Paul, Bananza (Belly Dancer) by Akon, and Is Ya Ready by Kay Flock, three source tracks.",
"""e[(e.tree=='shake') & (e.S_NAME=='Shake It') & e.E_NAME.isin(['Temperature','Bananza (Belly Dancer)','Is Ya Ready'])].merge(s.drop_duplicates('id')[['id','primary_artist']], left_on='end_node_id', right_on='id')[['S_NAME','E_NAME','primary_artist']].assign(sources=lambda d: len(d))"""
)

# 20
add(
"shake-it-also-samples-buffalo-springfield-and-fun-boy-three",
"In just this segment, there’s a tune from Buffalo Springfield Buffalo Springfield and Fun Boy Three Fun Boy Three, background vocals from Akon’s Bananza Bananza, a clap beat from Sean Paul’s Temperature Temperature and an earlier riddim, and a bass line from a previous Kay Flock song Is Ya Ready Is Ya Ready, all combined together.",
"Shake It also samples Buffalo Springfield's For What It's Worth and Fun Boy Three's The Lunatics.",
"""e[(e.tree=='shake') & (e.S_NAME=='Shake It') & e.E_NAME.isin(["For What It's Worth",'The Lunatics'])].merge(s.drop_duplicates('id')[['id','primary_artist']], left_on='end_node_id', right_on='id')[['S_NAME','E_NAME','primary_artist']]"""
)

# 21
add(
"cool-for-the-summer-and-cheers-sample-gin-and-juice-and-gotta-get-mine",
"Demi Lovato’s “Cool for the Summer” (2015) plays with that line, but shifts the focus in a different direction… While Rihanna’s “Cheers (Drink to That)” from 2010, in addition to heavily sampling Avril Lavigne’s “I’m With You,” abandons the parallel format entirely…",
"Both Cool for the Summer (2015) and Cheers (Drink to That) (2010) sample both Gin and Juice and Gotta Get Mine.",
"""e[e.tree=='mind'].merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='start_node_id', right_on='id')[['S_NAME','primary_artist','release_date','E_NAME']]"""
)

# 22
add(
"bops-goin-brazy-samples-ice-ice-baby",
"A vertical chain connects Ice Ice Baby by Vanilla Ice to Bops Goin Brazy by Tyga.",
"Bops Goin Brazy (2023) samples Ice Ice Baby (1990).",
"""e[e.tree=='conclusion'].merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','release_date_child','E_NAME','primary_artist_parent','release_date_parent']]"""
)

# 23
add(
"solar-power-samples-rock-dj",
"In 2021, Lorde picked up the line from Robbie Williams— not A Tribe Called Quest—but she takes on both parts.",
"Solar Power (2021) samples Rock DJ (2000), which samples Can I Kick It? (1990).",
"""e[e.tree=='kick'].merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','release_date_child','E_NAME','primary_artist_parent','release_date_parent']]"""
)

# 24
add(
"how-low-can-you-go-chain",
"Ludacris then samples Chuck D’s voice from “Bring the Noise” and alters the tempo and quality to kick off his 2010 song “How Low,” where he’s talking about “booty.”",
"How Low Can You Go samples How Low, which samples Bring the Noise, which samples Limbo Rock, three sample links.",
"""e[(e.tree=='low') & e.S_NAME.isin(['How Low Can You Go','How Low','Bring the Noise']) & e.E_NAME.isin(['How Low','Bring the Noise','Limbo Rock'])].merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','release_date_child','E_NAME','primary_artist_parent','release_date_parent']].assign(links=lambda d: len(d))"""
)

# 25
add(
"chubby-checker-limbo-rock-samples-the-champs",
"Chubby Checker popularized the phrase “How low can you go” when he added vocals to The Champs’ song “Limbo Rock.”",
"Chubby Checker's 1962 Limbo Rock samples The Champs' 1961 Limbo Rock.",
"""e[(e.tree=='low') & (e.S_NAME=='Limbo Rock') & (e.E_NAME=='Limbo Rock')].merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='start_node_id', right_on='id').merge(s.drop_duplicates('id')[['id','primary_artist','release_date']], left_on='end_node_id', right_on='id', suffixes=('_child','_parent'))[['S_NAME','primary_artist_child','release_date_child','E_NAME','primary_artist_parent','release_date_parent']]"""
)

with open('facts.json','w') as f:
    json.dump(facts, f, ensure_ascii=False, indent=2)
print(len(facts))
