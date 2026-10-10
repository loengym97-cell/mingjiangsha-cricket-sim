"""武将配置与技能；策略在 ai.py，通用规则在 engine.py。"""
from deck import EQUIPMENT, records

from ai import create_ai


class Character:
    """每位玩家拥有独立实例；技能状态不能在不同玩家之间共享。"""
    name = "白板"
    max_hp = 4
    base_hand_limit = 4
    equipment_slots = 3
    auto_equips = True





    skill_version = "v1"

    def __init__(self, ai_version="v1"):
        self.ai = create_ai(ai_version, self)

    def equipment_value(self, card): return self.ai.equipment_value(card)
    def choose_removal(self, g, target): return self.ai.choose_removal(g, target)
    def choose_equipment(self, g, p): return self.ai.choose_equipment(g, p)
    def hand_value(self, c, p): return self.ai.hand_value(c, p)
    def play_phase(self, g, p): return self.ai.play_phase(g, p)

    def on_gain(self, game, player, cards):
        pass

    def on_round_end(self, game, player):
        pass

    def phase_start(self):
        pass

    def skill_action(self, game, player):
        return False



    def after_tactics(self, game, player):
        return False


class WangJun(Character):
    name = "王濬"
    max_hp = 6
    base_hand_limit = 3

    def phase_start(self):
        self.transformed = 0
        self.burned = False

    def skill_action(self, g, p):
        if self.transformed < p.limit:
            self.transformed += 1
            if self.transform(g, p): return True
        q = g.other(p)
        if not self.burned and not p.frozen and len(p.equipment) > len(q.equipment):
            self.burned = True
            count = 0
            for c in list(q.hand + q.equipment + q.delayed):
                if c.suit == "♦" and c in q.hand + q.equipment + q.delayed:
                    g.drop(q, c, True); count += 1
            g.budget += count
            g.stats["王濬烧毁方片"] += count
            g.note(f"{p.name}发动熔金断索，烧毁{count}张方片，本回合出杀次数增加{count}")
            return True
        return False

    def transform(self, g, p):
        rows = records()
        eligible = [c for c in p.hand if any(r["suit"] == c.suit and r["name"] in EQUIPMENT for r in rows)]
        if not eligible: return False
        c = self.ai.transform_card(g, p, eligible)
        if c is None: return False
        pool = sorted({r["name"] for r in rows if r["suit"] == c.suit and r["name"] in EQUIPMENT})
        options = g.rng.sample(pool, min(3, len(pool)))
        c.name = self.ai.transform_option(g, p, options)
        g.note(f"{p.name}转化{c.suit}{c.name}，候选{options}；留在手牌")
        g.stats["王濬转化"] += 1
        choices = [x for x in g.deck if x.suit == c.suit]
        if choices:
            card = g.rng.choice(choices)
            g.deck.remove(card)
            g.gain(p, [card])
        return True

    def on_round_end(self, g, p):
        if len(g.other(p).equipment) > len(p.equipment): p.limit += 1


class GanNing(Character):
    name = "甘宁"
    max_hp = 6
    base_hand_limit = 3
    auto_equips = False

    def phase_start(self):
        self.washed = False

    def on_gain(self, g, p, cards):
        if any(c.suit == "♠" for c in cards) and not p.frozen:
            g.stats["甘宁拆牌触发"] += 1
            g.strip(g.other(p))

    def after_tactics(self, g, p):
        if self.washed or not p.hand: return False
        self.washed = True
        cards, p.hand = p.hand, []
        for c in cards: c.suit = "♠"
        g.deck.extend(cards)
        g.rng.shuffle(g.deck)
        g.stats["甘宁洗牌"] += 1
        g.note(f"{p.name}发动锦帆游侠，{len(cards)}张手牌永久改为黑桃，洗回牌堆")
        g.draw(p, len(cards))
        return True


REGISTRY = {cls.name: cls for cls in (Character, WangJun, GanNing)}


SKILL_VERSIONS = {"v1": "标准技能 v1"}

def create_character(name, ai_version="v1", skill_version="v1"):
    if skill_version not in SKILL_VERSIONS: raise ValueError("未知技能版本")
    return REGISTRY[name](ai_version)
