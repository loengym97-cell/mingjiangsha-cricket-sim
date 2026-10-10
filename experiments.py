"""不保存逐步状态的策略比较；固定种子、交换先手，输出可复查的统计。"""
import argparse
from collections import Counter
import json
from pathlib import Path
from engine import Game

def compare(left_ai, right_ai, games, seed):
    wins, stats, endings = Counter(), Counter(), Counter()
    rounds = 0
    for i in range(games):
        g = Game(seed+i//2, first=i%2, left_ai=left_ai, right_ai=right_ai, trace=i<100)
        try: r = g.run(check=True)
        except Exception:
            print(f"FAILED seed={seed+i//2} first={i%2} ai={left_ai}:{right_ai}",flush=True)
            raise
        wins[r['winner_side']] += 1
        stats.update(r['stats'])
        rounds += r['rounds']
        if g.events:
            loser = 1-r['winner_side'] if r['winner_side'] in (0,1) else 0
            p = g.players[loser]
            damage = [e['text'] for e in g.events if '受到' in e['text'] and e['text'].startswith(p.name)]
            endings[(p.name, damage[-1].split('伤害')[0] if damage else '其他')] += 1
    result = dict(left_ai=left_ai, right_ai=right_ai, games=games, seed=seed, wins=dict(wins), mean_rounds=rounds/games, stats=dict(stats), sampled_loss_damage={str(k):v for k,v in endings.items()})
    print(json.dumps({k:v for k,v in result.items() if k not in {'stats','sampled_loss_damage'}},ensure_ascii=False), flush=True)
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--games',type=int,default=10000)
    parser.add_argument('--seed',type=int,default=20261010)
    parser.add_argument('--output',default='experiments.json')
    parser.add_argument('--pairs',default='v1:v1,v1:v2,v1:v3,v3:v1,v3:v3')
    args = parser.parse_args()
    results=[]
    for pair in args.pairs.split(','):
        results.append(compare(*pair.split(':'),args.games,args.seed))
        Path(__file__).with_name(args.output).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
