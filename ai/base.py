"""可替换的出牌策略；不定义武将技能或修改游戏规则。"""
from deck import EQUIPMENT

WEIGHTS = {"诸葛连弩": 12, "轩辕剑": 11, "惊羽弓": 10, "银狮盔": 9,
           "藤甲": 8, "开山斧": 8, "凤羽盔": 8, "飒露紫": 8,
           "云锦袍": 7, "盗骊": 7, "丈八蛇矛": 7, "乌骓": 7,
           "爪黄飞电": 7, "鸣鸿刀": 6, "羽扇": 6, "八卦盾": 6,
           "玄武盾": 6, "青龙偃月刀": 6, "赤兔": 6, "绝影": 6, "龙舌弓": 5}
ATTACK = {"杀", "雷杀", "火杀"}

class BaselineAI:
    version = "v1"
    def __init__(self, role):
        self.role = role
        self.auto_equips = True

    def equipment_value(self, card):
        return WEIGHTS.get(card.name, 2)

    def choose_removal(self, g, target):
        if target.equipment:
            return max(target.equipment, key=self.equipment_value)
        if target.delayed: return target.delayed[0]
        return g.rng.choice(target.hand) if target.hand else None

    def choose_equipment(self, g, p):
        if not self.auto_equips: return None
        cards = sorted((c for c in p.hand if c.name in EQUIPMENT), key=self.equipment_value, reverse=True)
        for c in cards:
            if len(p.equipment) < g.slots(p): return c
            if self.equipment_value(c) > min(map(self.equipment_value, p.equipment)): return c
        return None

    def hand_value(self, c, p):
        if c.name == "易": return 12
        if c.name == "蟠桃": return 10 if p.hp <= p.max_hp / 2 else 7
        if c.name == "闪避": return 9
        if c.name in ATTACK: return 8
        if c.name == "怒气": return 9 if p.hp <= p.max_hp / 3 else 6
        if c.name in EQUIPMENT: return WEIGHTS.get(c.name, 2) if self.auto_equips else 0
        return 3

    def should_use_tactic(self, g, p, card):
        if not g.can_use_tactic(p, card.name): return False
        if card.name == "调兵遣将":
            q = g.other(p)
            defended = g.find(p, {"闪避"}) is not None or p.has("八卦盾") or p.has("玄武盾")
            return len(q.hand) <= 1 or (len(q.hand) <= 2 and defended)
        return True

    def play_phase(self, g, p):
        """通用启发式AI；子类可覆盖整段策略，也可只插入技能动作。"""
        q = g.other(p)
        self.role.phase_start()
        recast_ids = set()
        for _ in range(1000):
            if p.hp <= 0 or q.hp <= 0: return
            chain = next((c for c in p.hand if c.name == "连环" and c.uid not in recast_ids), None)
            if chain:
                recast_ids.add(chain.uid)
                g.recast(p, chain)
                continue
            peach = g.find(p, {"蟠桃"}, yi=False)
            if peach and p.hp < p.max_hp:
                g.drop(p, peach); g.heal(p); g.actions += 1
                continue
            if g.equip(p): continue
            if not p.silenced and self.role.skill_action(g, p): continue
            tactic = next((c for c in p.hand if c.name in g.supported_tactics and self.should_use_tactic(g, p, c)), None)
            if tactic:
                g.tactic(p, tactic)
                continue
            defer = hasattr(self, "defer_wash") and self.defer_wash(g, p)
            if not p.silenced and not defer and self.role.after_tactics(g, p): continue
            attack = g.find(p, ATTACK)
            if attack and q.has("藤甲") and not p.has("轩辕剑") and not (attack.suit == "♥" or attack.rank == 4):
                attack = next((c for c in p.hand if c.name in ATTACK and (c.suit == "♥" or c.rank == 4)), None)
            if attack and g.can_attack(p, q) and (g.used < g.budget or p.has("诸葛连弩")):
                rage = g.find(p, {"怒气"}, yi=False)
                if rage and (not g.rage_uses or len(p.hand + p.equipment) > 2):
                    g.play_rage(p, rage)
                    continue
                bonus, g.rage = g.rage, 0
                first = g.actions == 0
                g.actions += 1; g.used += 1
                g.attack(p, attack, bonus, first)
                continue
            break
        else:
            g.stats["AI行动上限结束阶段"] += 1
            g.note(f"{p.name}的AI达到单阶段1000次决策上限，结束出牌阶段")

    def transform_card(self, g, p, eligible):
        return min(eligible, key=lambda c: self.hand_value(c, p))

    def transform_option(self, g, p, options):
        return max(options, key=lambda name: WEIGHTS.get(name, 2))
