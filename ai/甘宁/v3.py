from .v2 import AI as Parent
from ..base import ATTACK, WEIGHTS
from deck import EQUIPMENT

class AI(Parent):
    """先兑现可用的杀，再洗牌；转化保留关键输出、防御。"""
    version = "v3"

    def should_use_tactic(self, g, p, card):
        if not super().should_use_tactic(g, p, card): return False
        q = g.other(p)
        if card.name == "休养生息": return p.hp < p.max_hp and (q.hp == q.max_hp or p.hp <= 2)
        if card.name == "阵前对决":
            return sum(c.name in ATTACK or c.name == "易" for c in p.hand) >= max(1, len(q.hand) // 2)
        return True

    def play_phase(self, g, p):
        self.game = g
        try: return super().play_phase(g, p)
        finally: self.game = None

    def defer_wash(self, g, p):
        q = g.other(p)
        attacks = [c for c in p.hand if c.name in ATTACK or c.name == "易"]
        useful = any(not q.has("藤甲") or p.has("轩辕剑") or (c.name != "易" and (c.suit == "♥" or c.rank == 4)) for c in attacks)
        return g.can_attack(p, q) and (g.used < g.budget or p.has("诸葛连弩")) and useful

    def transform_card(self, g, p, eligible):
        attacks = sum(c.name in ATTACK or c.name == "易" for c in p.hand)
        def cost(c):
            value = self.hand_value(c, p)
            if c.name in ATTACK and attacks == 1 and g.can_attack(p, g.other(p)) and g.used < g.budget: value += 15
            if c.name in {"蟠桃", "怒气", "易"} and p.hp <= 2: value += 12
            if c.name == "闪避" and p.hp <= 3 and sum(x.name == "闪避" for x in p.hand) == 1: value += 8
            if c.name in EQUIPMENT and len(p.equipment) >= g.slots(p): value = 1
            return value
        return min(eligible, key=cost)

    def transform_option(self, g, p, options):
        def score(name):
            value = WEIGHTS.get(name, 2)
            if name == "云锦袍": value += 6 if len(p.equipment) >= g.slots(p)-1 else -3
            if name == "盗骊": value += 5
            if name in {"银狮盔", "飒露紫"} and p.hp <= 3: value += 9
            if name == "诸葛连弩" and not any(c.name in ATTACK for c in p.hand): value -= 6
            if name == "轩辕剑": value += 4
            if name == "凤羽盔": value += 3
            if name in {"云锦袍", "诸葛连弩", "轩辕剑", "惊羽弓", "藤甲"} and p.has(name): value -= 5
            return value
        return max(options, key=score)
