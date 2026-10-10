"""批量运行：engine.py规则、characters.py技能、ai/各武将策略版本。"""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import mean
from deck import summary
from engine import Game, ROOT
from characters import REGISTRY, SKILL_VERSIONS
from ai import AI_REGISTRY, AI_LABELS

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", choices=REGISTRY, default="王濬")
    parser.add_argument("--right", choices=REGISTRY, default="甘宁")
    parser.add_argument("--left-ai", choices=AI_LABELS, default="v1")
    parser.add_argument("--right-ai", choices=AI_LABELS, default="v1")
    parser.add_argument("--left-version", choices=SKILL_VERSIONS, default="v1")
    parser.add_argument("--right-version", choices=SKILL_VERSIONS, default="v1")
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261010)
    parser.add_argument("--max-rounds", type=int, default=300)
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--save-details", action="store_true", help="保存全部逐局事件与可视化报告")
    parser.add_argument("--output", type=Path, default=ROOT / "diagnostic_result.json")
    args = parser.parse_args()
    rules = json.loads((ROOT / "rules.json").read_text(encoding="utf-8"))
    if args.audit:
        print(json.dumps({"deck": summary(), "rules": rules}, ensure_ascii=False, indent=2)); return
    if not args.diagnostic:
        parser.error("尚有待确认规则；正式胜率暂不开放。--diagnostic 只用于检验程序，--audit 查看数据。")
    if args.games <= 0 or args.max_rounds <= 0: parser.error("局数和回合上限必须大于0")
    if args.left_ai not in AI_REGISTRY.get(args.left, {'v1':None}) or args.right_ai not in AI_REGISTRY.get(args.right, {'v1':None}):
        parser.error("所选武将没有这个AI版本，请查看ai/对应武将目录")
    variants = dict(left_ai=args.left_ai, right_ai=args.right_ai, left_version=args.left_version, right_version=args.right_version)
    if args.save_details:
        from batch import run_batch
        result = run_batch(args.games, args.seed, args.max_rounds, args.left, args.right,
                           progress=lambda run, done, total: print(f"run={run} {done}/{total}", flush=True) if done % 1000 == 0 or done == total else None, **variants)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"run={result['run_id']} counts={result['counts']} mean_rounds={result['mean_rounds']:.4f}", flush=True)
        return
    outcomes = []
    log = None
    for i in range(args.games):
        game = Game(args.seed + i // 2, first=i % 2, trace=i == 0, left=args.left, right=args.right, **variants)
        outcomes.append(game.run(args.max_rounds, args.check))
        if i == 0: log = game.log
    result = {"status": "诊断试跑，不代表真实游戏胜率", "seed": args.seed,
              "games": args.games, "counts": dict(Counter(x["winner"] for x in outcomes)),
              "mean_rounds": mean(x["rounds"] for x in outcomes),
              "by_first": {name: dict(Counter(x["winner"] for x in outcomes if x["first"] == name)) for name in dict.fromkeys((args.left, args.right))},
              "rules": rules, "versions": variants, "sample_log": log}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成{args.games}局诊断试跑：{args.output}。此结果不代表真实胜率。")

if __name__ == "__main__": main()
