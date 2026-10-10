"""复查已模拟的种子，记录策略失误的可观察迹象（不推断因果）。"""
from collections import Counter
import json
from pathlib import Path
from engine import Game
from ai import ATTACK

def analyze(left_ai='v1',right_ai='v1',games=1000,seed=20261010):
    counts=Counter(); examples={}
    for i in range(games):
        g=Game(seed+i//2,first=i%2,trace=True,left_ai=left_ai,right_ai=right_ai)
        r=g.run(check=True)
        if r['winner_side'] not in (0,1): continue
        loser=1-r['winner_side']; name=g.players[loser].name
        counts[name+'败局数']+=1
        flags=set()
        for j,e in enumerate(g.events):
            if e['text'].startswith(name+'发动锦帆') and j:
                previous=g.events[j-1]['state']['players'][loser]
                if any(c['name'] in ATTACK or c['name']=='易' for c in previous['hand']): flags.add('甘宁败局中洗掉杀或易')
            if e['text'].startswith(name+'转化') and j:
                previous=g.events[j-1]['state']['players'][loser]
                after=e['state']['players'][loser]
                before={c['id']:c for c in previous['hand']}
                for c in after['hand']:
                    if c['id'] in before and before[c['id']]['name'] in ATTACK and c['name'] not in ATTACK:
                        if sum(x['name'] in ATTACK for x in previous['hand'])==1: flags.add('王濬败局中转化最后一张杀')
            if e['text']==name+'回合开始':
                p=e['state']['players'][loser]
                if p['distance_to_other']>p['attack_range']: flags.add(name+'败局中曾超出攻击距离')
        if g.players[0].limit>1: flags.add(name+'败局中王濬技能次数增长')
        for flag in flags:
            counts[flag]+=1
            examples.setdefault(flag,dict(seed=seed+i//2,first=i%2,winner=r['winner']))
    return dict(left_ai=left_ai,right_ai=right_ai,games=games,seed=seed,counts=dict(counts),examples=examples)

if __name__=='__main__':
    result=analyze()
    Path(__file__).with_name('loss_analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
