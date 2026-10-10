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
        self.auto_equips = role.name != "甘宁"

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

class EquipAI(BaselineAI):
    """甘宁允许择机装备，王濬维持基线。只使用己方手牌和公共状态。"""
    version = "v2"

    def __init__(self, role):
        super().__init__(role)
        self.auto_equips = True

    def choose_equipment(self, g, p):
        c = super().choose_equipment(g, p)
        if not c or p.name != "甘宁": return c
        q = g.other(p)
        projected = len(p.equipment) + (len(p.equipment) < g.slots(p))
        safe = projected <= len(q.equipment)
        emergency = p.hp <= 2 and c.name in {"银狮盔", "飒露紫", "藤甲", "八卦盾", "玄武盾"}
        # 即时收益可以接受一轮技能成长；不盲目堆积低收益装备。
        immediate = c.name in {"盗骊", "丈八蛇矛"} or (c.name == "银狮盔" and p.hp < p.max_hp)
        return c if safe or emergency or immediate else None


class TacticalAI(EquipAI):
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


class ConservativeAI(BaselineAI):
    version = "v4"

    def choose_equipment(self, g, p):
        if p.name != "甘宁": return super().choose_equipment(g,p)
        # 只为立即回血或濒死保险承受成长代价，其余装备继续洗牌。
        for c in p.hand:
            if c.name == "银狮盔" and p.hp <= 3: return c
            if c.name == "飒露紫" and p.hp <= 1 and not p.has("飒露紫"): return c
        return None


class AttackFirstAI(ConservativeAI):
    version = "v5"
    defer_wash = TacticalAI.defer_wash


class PreserveAI(AttackFirstAI):
    version = "v6"

    def transform_card(self, g, p, eligible):
        c = TacticalAI.transform_card(self,g,p,eligible)
        if c.name in ATTACK and sum(x.name in ATTACK or x.name=='易' for x in p.hand)==1 and g.can_attack(p,g.other(p)) and g.used<g.budget:
            return None
        if c.name in {'怒气','易','蟠桃'} and p.hp<=2: return None
        return c

    def transform_option(self,g,p,options):
        return TacticalAI.transform_option(self,g,p,options)


class DistanceAI(ConservativeAI):
    version = "v7"

    def choose_removal(self, g, target):
        p = g.other(target)
        if not target.equipment: return super().choose_removal(g,target)
        def score(c):
            value = self.equipment_value(c)
            if c.name in {'爪黄飞电','的卢','飒露紫','绝影'} and g.distance(p,target)>g.attack_range(p): value += 25
            if c.name == '云锦袍' and len(target.equipment)>target.character.equipment_slots: value += 22
            if c.name == '藤甲' and not p.has('轩辕剑'): value += 10
            return value
        return max(target.equipment,key=score)


AI_REGISTRY = {"v1": BaselineAI, "v2": EquipAI, "v3": TacticalAI,
               "v4": ConservativeAI, "v5": AttackFirstAI, "v6": PreserveAI, "v7": DistanceAI}
AI_LABELS = {"v1": "基线 v1", "v2": "择机装备 v2", "v3": "出牌优化 v3",
             "v4": "保命装备 v4", "v5": "先杀后洗 v5", "v6": "保留关键牌 v6", "v7": "距离拆牌 v7"}

def create_ai(version, role):
    return AI_REGISTRY[version](role)
