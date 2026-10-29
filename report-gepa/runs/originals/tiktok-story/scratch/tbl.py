# name, signed, A, B, C, D, E, F, G  (from rendered story table)
rows = """
CJ major Y Y Y T T T T
24kGoldn major Y Y Y T T T T
Sleepy Hallow major Y Y Y T T T T
Ir Sais major Y Y Y T T T T
Spotemgottem major Y Y Y F T T T
Tai Verdes major Y Y Y T T T T
Arizona Zervas major Y Y Y T T T T
Audrey Mika major Y Y Y F T T T
Cochise major Y Y Y T T T T
JVKE indie Y Y Y T T T T
Masked Wolf major Y Y Y T T F T
ppcocaine major Y Y Y F F T T
Ricky Montgomery major Y Y Y T T F T
S1mba major Y N N T T T T
salem ilese indie Y Y Y F T T T
Fousheé major Y Y Y T T T T
Ritt Momney major Y N N T T T T
Shuba major N Y Y F T T T
Tay Money major Y Y Y T T F T
2KBABY major Y Y Y F T F T
347aidan major Y N Y F T T T
BRELAND major Y Y Y T T F T
carolesdaughter major Y Y Y T T F T
CORPSE notsigned Y Y Y F F T T
Erica Banks major Y Y Y T T F T
Harry Nach notsigned Y Y Y T T T T
Juanfran notsigned Y Y Y F T T T
LLusion major Y Y N F T F T
Surf Mesa major Y Y Y T T F T
WHOKILLEDXIX major Y N N F T T T
Joy Again major Y N N T T F T
BRS Kash major Y Y Y F T F T
Claire Rosinkranz major Y Y Y F T F T
Cookiee Kawaii indie Y N Y F T F T
DripReport major Y Y Y F F F T
Harm Franklin indie Y N N F F T T
Jawsh 685 major Y Y N F F T T
Kenndog major Y N N F F T T
Lil Xxel major Y Y Y F T F T
LPB Poody major Y Y Y F F T T
REI AMI major Y Y N F T F T
StaySolidRocky major Y Y Y F F F T
Tesher major Y N Y F F T T
BeatKing major N N Y T T F T
Frances Forever indie Y N N F T F T
Powfu major Y Y Y F F F T
TisaKorean indie Y Y Y F T F T
Bianca major N Y Y F T F T
CMTEN major N N N F T F T
KAIBA major N N N F T F T
KillBunk indie Y N Y F F F T
Locura Mix notsigned Y N N F F T T
MarMar Oso indie Y Y N F F F T
MASN major Y N N F F F T
Sofia Mills notsigned Y N N F T F T
Tiagz major N Y Y F F T T
Curtis Roach notsigned N N N F T T T
DTG notsigned Y Y Y T F F T
5ive major N Y N F F F T
645AR major N Y N F F F T
Ander Huang major N N N F F F T
Ayzha Nyree major N Y N F F F T
BLVKSHP indie N N N F F F T
Curtis Waters notsigned Y Y N F F F T
David Shawty notsigned N N N F T F T
Dixson Waz major N Y Y F F F T
Edith Whiskers notsigned Y N N F F F T
Eduardo Luzquiños notsigned Y Y N F F F T
Glitch Gum notsigned N N N F T F T
JoeVille major N N N F F F T
Juan Caoile indie N Y N F F F T
KBFR major N N N F F F T
King Critical indie N N Y F F F T
KINGMOSTWANTED indie N N N F F F T
Kreepa notsigned N N N F T F T
Kris Yute major N N N F F F T
L.Dre notsigned Y Y N F F F T
Loui major N N Y F F F T
Millie B major N N N F F F T
NextYoungin indie N N Y F F F T
Popp Hunna notsigned Y Y Y F F F T
Reyanna Maria major N N N F F F T
Cassidi notsigned N N N F T F T
Likybo notsigned N N Y F T F T
Queendome Come notsigned N N N F T F T
$wave notsigned N N N F F F T
8-Bit Arcade notsigned N N N F F F T
Ajay Stephens notsigned N N N F F F T
Apollo Fresh notsigned N Y N F F F T
BLIND.SEE notsigned N N N F F F T
BMW KENNY notsigned N N Y F F F T
Castion notsigned N N N F F F T
Championxiii notsigned N N N F F F T
Disco Lines notsigned N N N F T F F
Emilee notsigned N Y Y F F F T
Grant Averill indie N N N F F F F
Huncho Da Rockstar notsigned N N N F F F T
Kblast notsigned N N N F F F T
Lil Jay notsigned N N Y F F F T
Marv Allen indie N N Y F F F F
Mighty Bay notsigned N N N F F F T
Nolo Flows Yo indie N N N F F F F
Number9ok notsigned N N N F F F T
Prod by Rose notsigned N N N F F F T
Rontae Don't Play indie N N N F F F F
SkinBone notsigned N N Y F F F F
Ted Fresco major N N N F F F F
VL4S notsigned N N N F F F T
Vytinho NG notsigned N N Y F F F T
WhoHeem major N Y N F F F F
Yungster Jack notsigned N N N F F F T
Dathan notsigned N N N F F F T
iMarkkeyz indie N N Y F F F F
Karetta el Gucci notsigned N N N F F F T
Kenyi notsigned N N N F F F T
Adam Tahere notsigned N N N F F F F
BRYOZA notsigned N N N F F F F
Carol Kay notsigned N N N F F F F
Devonte Mayo notsigned N N N F F F F
Domknowz notsigned N N N F F F F
Frankieredhots notsigned N N N F F F F
iamjuampi notsigned N N N F F F F
Jack Be notsigned N N N F F F F
Nish notsigned N N N F F F F
ThemBrothers notsigned N N N F F F F
"""
import pandas as pd
rl=[l.split() for l in rows.strip().split("\n")]
# handle names with spaces: name is everything before signed token, but signed tokens vary; use fixed: name up to ' major/indie/notsigned'
data=[]
for l in rows.strip().split("\n"):
    parts=l.split()
    # find index of signed token
    for i,p in enumerate(parts):
        if p in ('major','indie','notsigned'):
            name=' '.join(parts[:i]); rest=parts[i:]; break
    data.append([name]+rest)
t=pd.DataFrame(data, columns=['name','signed','A','B','C','D','E','F','G'])
print(len(t), t.name.nunique())
