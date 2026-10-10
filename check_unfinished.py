from engine import Game
for i in range(10000):
    seed=30300000+i//2
    g=Game(seed,first=i%2,left_ai='v3',right_ai='v7')
    r=g.run(check=True)
    if r['winner_side']==-2:
        print(dict(game=i+1,seed=seed,first=i%2),flush=True)
        h=Game(seed,first=i%2,left_ai='v3',right_ai='v7')
        print(h.run(1000,check=True),flush=True)
