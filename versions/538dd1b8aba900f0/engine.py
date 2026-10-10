"""离线斗蛐蛐：可复现的规则模型。未确认规则见 rules.json。"""
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import random
from deck import EQUIPMENT, records

ROOT = Path(__file__).resolve().parent
ATTACK = {"杀", "火杀", "雷杀"}
DEFENSIVE_MOUNTS = {"爪黄飞电", "的卢", "飒露紫", "绝影"}
OFFENSIVE_MOUNTS = {"盗骊", "白蹄乌", "乌骓", "赤兔"}
WEAPON_RANGE = {"诸葛连弩": 1, "轩辕剑": 2, "干将莫邪": 2, "鸣鸿刀": 2,
                "开山斧": 3, "亮银枪": 3, "青龙偃月刀": 3, "丈八蛇矛": 3,
                "方天画戟": 4, "惊羽弓": 5, "龙舌弓": 5, "羽扇": 4}
from characters import create_character


class GameFinished(Exception):
    """濒死救援失败后的第一个死亡立即终止全部待结算效果。"""
    pass

@dataclass
class Card:
    uid: int
    suit: str
    rank: int
    name: str

@dataclass
class Player:
    name: str
    hp: int
    max_hp: int
    base_hand_limit: int
    hand: list = field(default_factory=list)
    equipment: list = field(default_factory=list)
    delayed: list = field(default_factory=list)
    limit: int = 1
    frozen: bool = False
    silenced: bool = False
    chained: bool = False
    character: object = None
    def count(self, name):
        return sum(c.name == name for c in self.equipment)

    def has(self, name):
        return self.count(name) > 0

class Game:
    self_tactics = {"多多益善", "先拔头筹", "休养生息"}
    supported_tactics = self_tactics | {"夺粮劫营", "破阵卸甲", "箭雨齐射", "烽火狼烟", "阵前对决", "烈火焚城", "天雷", "久旱", "霜冻", "地火", "连环", "调兵遣将"}
    def __init__(self, seed=0, first=None, trace=False, left="王濬", right="甘宁",
                 left_ai="v1", right_ai="v1", left_version="v1", right_version="v1"):
        self.rng = random.Random(seed)
        self.deck = [Card(i, **r) for i, r in enumerate(records())]
        self.rng.shuffle(self.deck)
        self.discard, self.burned = [], []
        self.players = []
        for name, ai_version, skill_version in ((left, left_ai, left_version), (right, right_ai, right_version)):
            character = create_character(name, ai_version, skill_version)
            self.players.append(Player(name, character.max_hp, character.max_hp, character.base_hand_limit, character=character))
        self.first = self.rng.randrange(2) if first is None else first
        self.active = self.first
        self.next_id = 162
        self.turn_id = 0
        self.log = [] if trace else None
        self.events = [] if trace else None
        self.stats = Counter()
        self.actions = 0
        self.used = 0
        self.budget = 1
        self.rage = 0
        self.rage_uses = 0
        self.rescued = set()
        self.depth = 0

    def note(self, msg):
        if self.log is not None:
            self.log.append(f"{self.turn_id}: {msg}")
            self.events.append({"turn": self.turn_id, "text": msg, "state": self.snapshot()})

    def snapshot(self):
        def cards(zone):
            return [{"id": c.uid, "name": c.name, "suit": c.suit, "rank": c.rank} for c in zone]
        return {"deck": len(self.deck), "discard": len(self.discard), "burned": len(self.burned),
                "active": self.active, "players": [
                    {"name": p.name, "hp": p.hp, "max_hp": p.max_hp, "hand_limit": self.hand_limit(p),
                     "attack_range": self.attack_range(p), "distance_to_other": self.distance(p, self.other(p)),
                     "hand": cards(p.hand), "equipment": cards(p.equipment),
                     "delayed": cards(p.delayed), "chained": p.chained, "silenced": p.silenced,
                     "frozen": p.frozen, "skill_limit": p.limit} for p in self.players]}

    def other(self, p):
        return self.players[1] if p is self.players[0] else self.players[0]

    def take(self):
        if not self.deck and self.discard:
            self.deck, self.discard = self.discard, []
            self.rng.shuffle(self.deck)
        return self.deck.pop() if self.deck else None

    def gain(self, p, cards):
        cards = [c for c in cards if c is not None]
        p.hand.extend(cards)
        self.note(f"{p.name}获得" + ",".join(f"{c.suit}{c.rank}{c.name}" for c in cards))
        if not p.silenced:
            p.character.on_gain(self, p, cards)

    def draw(self, p, n):
        self.gain(p, [self.take() for _ in range(n)])

    def slots(self, p):
        return p.character.equipment_slots + 2 * p.count("云锦袍")

    def distance(self, source, target):
        return max(1, 1 + sum(c.name in DEFENSIVE_MOUNTS for c in target.equipment)
                   - sum(c.name in OFFENSIVE_MOUNTS for c in source.equipment))

    def attack_range(self, p):
        return max((WEAPON_RANGE.get(c.name, 1) for c in p.equipment), default=1)

    def can_attack(self, p, q):
        return not p.frozen and self.distance(p, q) <= self.attack_range(p)

    def can_use_tactic(self, p, name):
        q = self.other(p)
        if p.frozen and name not in self.self_tactics: return False
        if name == "夺粮劫营": return self.distance(p, q) <= 1
        if name == "调兵遣将": return self.can_attack(p, q) and self.can_attack(q, p)
        return True

    def drop(self, p, c, burn=False):
        for zone in (p.hand, p.equipment, p.delayed):
            if c in zone:
                zone.remove(c)
                (self.burned if burn else self.discard).append(c)
                self.note(f"{p.name}的{c.suit}{c.rank}{c.name}从{'手牌' if zone is p.hand else '装备区' if zone is p.equipment else '卜卦区'}进入{'移出游戏区' if burn else '弃牌堆'}")
                break
        else:
            raise AssertionError("牌不属于该玩家")
        while len(p.equipment) > self.slots(p):
            extra = self.rng.choice(p.equipment)
            p.equipment.remove(extra)
            self.discard.append(extra)
            self.note(f"装备栏缩减：{p.name}随机弃置{extra.name}")

    def strip(self, p, burn=False, random_pick=False):
        cards = p.equipment + p.delayed + p.hand
        if not cards:
            return
        c = self.rng.choice(cards) if random_pick else self.other(p).character.choose_removal(self, p)
        self.note(f"移除{p.name}的{c.name}{'（烧毁）' if burn else ''}")
        self.drop(p, c, burn)

    def value(self, c, p):
        return p.character.hand_value(c, p)

    def find(self, p, names, yi=True):
        return next((c for c in p.hand if c.name in names), None) or (
            next((c for c in p.hand if c.name == "易"), None) if yi else None)

    def heal(self, p, n=1):
        before = p.hp
        p.hp = min(p.max_hp, p.hp + n)
        self.note(f"{p.name}回复{p.hp-before}点体力，体力{p.hp}")

    def rescue(self, p):
        while p.hp <= 0:
            c = self.find(p, {"蟠桃", "怒气"})
            if c:
                self.drop(p, c)
                p.hp += 1
                self.note(f"{p.name}用{c.name}濒死自救，体力{p.hp}")
            elif any(c.name == "飒露紫" and c.uid not in self.rescued for c in p.equipment):
                mount = next(c for c in p.equipment if c.name == "飒露紫" and c.uid not in self.rescued)
                self.rescued.add(mount.uid)
                self.drop(p, mount, True)
                p.hp = 1
                self.note(f"{p.name}触发飒露紫自救，体力1")
                self.draw(p, 3)
            else:
                break

    def divine(self):
        c = self.take()
        if c:
            self.discard.append(c)
            self.note(f"卜卦{c.suit}{c.rank}")
        return c

    def damage(self, source, p, n, element="normal", ignore_armor=False, transferred=False):
        if source and element == "fire" and not transferred: n += source.count("羽扇")
        if p.has("藤甲") and not ignore_armor:
            if element == "normal":
                self.note(f"{p.name}的藤甲免疫无属性伤害")
                return
            if element == "fire":
                armor = [c for c in p.equipment if c.name == "藤甲"]
                n += len(armor)
                for c in armor: self.drop(p, c, True)
        if p.has("银狮盔") and not ignore_armor and n > 1:
            n = 1
            self.drop(p, next(c for c in p.equipment if c.name == "银狮盔"), True)
        p.hp -= n
        self.stats["伤害"] += n
        self.note(f"{p.name}受到{n}点{element}伤害，体力{p.hp}")
        linked = []
        if p.chained and element != "normal" and not transferred:
            linked = [q for q in self.players if q is not p and q.chained and q.hp > 0]
            p.chained = False
            for q in linked: q.chained = False
        self.rescue(p)
        if p.hp <= 0:
            self.note(f"{p.name}死亡，对局立即结束，停止后续结算")
            raise GameFinished
        for mount in [c for c in p.equipment if c.name == "的卢"]:
            if p.hp <= 0 or mount not in p.equipment: continue
            c = self.divine()
            if c and c.rank < 8: self.draw(p, 2)
            elif c:
                for card in list(p.hand + p.equipment):
                    if card in p.hand + p.equipment:
                        self.drop(p, card, card.name == "的卢")
        for q in linked:
            self.damage(source, q, n, element, transferred=True)

    def respond(self, p, kind, ignore_armor=False):
        for _ in range(1 if kind == "闪避" and p.has("八卦盾") and not ignore_armor else 0):
            c = self.divine()
            if c and c.suit == "♣": self.heal(p)
            if c and c.suit == "♠": return True
        names = ATTACK if kind == "杀" else {kind}
        if kind == "闪避" and p.has("玄武盾") and not ignore_armor: names = names | ATTACK
        c = self.find(p, names, yi=kind != "识破")
        if not c: return False
        was_attack = c.name in ATTACK
        self.note(f"{p.name}打出{c.suit}{c.rank}{c.name}响应{kind}")
        self.drop(p, c)
        if was_attack:
            for _ in range(p.count("乌骓")): self.draw(p, 1)
        return True

    def attack(self, p, c, boost=0, first=False):
        q = self.other(p)
        if not self.can_attack(p, q): return False
        piercing = p.has("轩辕剑")
        if piercing: q.silenced = True
        self.note(f"{p.name}向{q.name}打出{c.suit}{c.rank}{c.name}" + ("，轩辕剑立即封禁技能并无视防具" if piercing else ""))
        self.drop(p, c)
        for _ in range(p.count("乌骓")): self.draw(p, 1)
        for _ in range(q.count("绝影")): self.draw(q, 1)
        # 亮银枪反击允许递归，深度用于发现而非掩盖异常。
        for _ in range(q.count("亮银枪")):
            counter = self.find(q, ATTACK)
            if counter:
                if not self.can_attack(q, p): break
                if self.depth >= 500:
                    raise RuntimeError("亮银枪反击嵌套超过500层")
                self.depth += 1
                self.attack(q, counter)
                self.depth -= 1
        unavoidable = first and p.has("惊羽弓")
        dodged = False if unavoidable else all(self.respond(q, "闪避", piercing) for _ in range(2 if p.has("鸣鸿刀") else 1))
        if dodged:
            self.note(f"{q.name}抵消本次杀")
            if p.has("鸣鸿刀"):
                self.strip(p, random_pick=True)
            if p is self.players[self.active]: self.budget += p.count("青龙偃月刀")
            return
        element = "normal" if c.name == "易" else "fire" if c.suit == "♥" else "thunder" if c.rank == 4 else "normal"
        n = 1 + boost
        for _ in range(p.count("开山斧")):
            if not p.hand: break
            self.drop(p, min(p.hand, key=lambda c: self.value(c, p)))
            n += 1
        hp_before = q.hp
        self.damage(p, q, n, element, ignore_armor=piercing)
        if q.hp < hp_before:
            for _ in range(p.count("龙舌弓")): self.strip(q)
        if q.hp <= 0:
            for _ in range(p.count("白蹄乌")): self.draw(p, 3)

    def equip(self, p):
        chosen = p.character.choose_equipment(self, p)
        cards = [chosen] if chosen else []
        for c in cards:
            if len(p.equipment) >= self.slots(p):
                old = min(p.equipment, key=p.character.equipment_value)
                self.drop(p, old)
                # 替换云锦袍可能将五格降回三格，需要先腾出新装备的位置。
                while len(p.equipment) >= self.slots(p):
                    self.drop(p, min(p.equipment, key=p.character.equipment_value))
            p.hand.remove(c)
            p.equipment.append(c)
            self.note(f"{p.name}装备{c.name}")
            if c.name == "银狮盔": self.heal(p)
            if c.name == "盗骊": self.draw(p, 2)
            if c.name == "丈八蛇矛":
                generated = []
                for _ in range(2):
                    generated.append(Card(self.next_id, self.rng.choice(["♦", "♣", "♠", "♥"]), self.rng.randint(1, 8), "杀"))
                    self.next_id += 1
                self.gain(p, generated)
            return True
        return False

    def tactic(self, p, c):
        q = self.other(p)
        name = c.name
        if not self.can_use_tactic(p, name): return False
        self.note(f"{p.name}打出战法{c.suit}{c.rank}{name}")
        self.drop(p, c)
        self.actions += 1
        if name == "先拔头筹":
            # 只在完整效果开始前抵消一次，选牌获得不能单独识破。
            if self.respond(q, "识破"): return
            revealed = [x for x in (self.take(), self.take()) if x is not None]
            if revealed:
                chosen = max(revealed, key=lambda x: self.value(x, p))
                revealed.remove(chosen)
                self.gain(p, [chosen])
                self.gain(q, revealed)
            return
        if name == "多多益善":
            if not self.respond(q, "识破"): self.draw(p, 2)
            return
        if name == "休养生息":
            # 从下家起，满血不成为目标，逐目标决定是否识破。
            for target in (q, p):
                if target.hp < target.max_hp and not self.respond(self.other(target), "识破"):
                    self.heal(target)
            return
        if self.respond(q, "识破"): return
        if name == "调兵遣将":
            attack = self.find(q, ATTACK)
            if attack:
                self.note(f"调兵遣将：{q.name}对{p.name}出杀，不占用其回合出杀次数")
                self.attack(q, attack)
            elif q.hand:
                given = min(q.hand, key=lambda x: self.value(x, q))
                self.drop(q, given)
                self.discard.remove(given)
                self.note(f"调兵遣将：{q.name}无法出杀，交给{p.name}一张手牌")
                self.gain(p, [given])
        elif name in {"天雷", "久旱", "霜冻", "地火"}:
            self.discard.remove(c)
            q.delayed.append(c)
        elif name == "连环":
            q.chained = not q.chained
            if p.chained: p.chained = False
        elif name in {"夺粮劫营", "破阵卸甲"}:
            if name == "破阵卸甲": self.strip(q)
            else:
                choices = q.equipment + q.hand
                if choices:
                    x = max(q.equipment, key=p.character.equipment_value) if q.equipment else self.rng.choice(q.hand)
                    self.drop(q, x)
                    self.discard.remove(x)
                    self.gain(p, [x])
        elif name in {"箭雨齐射", "烽火狼烟"}:
            if not self.respond(q, "闪避" if name == "箭雨齐射" else "杀"):
                self.damage(p, q, 1)
        elif name == "阵前对决":
            defender, attacker = q, p
            for _ in range(1000):
                if not self.respond(defender, "杀"):
                    self.damage(attacker, defender, 1)
                    break
                defender, attacker = attacker, defender
            else: raise RuntimeError("决斗循环异常")
        elif name == "烈火焚城" and p.hand + p.equipment and q.hand + q.equipment:
            cost = min(p.hand + p.equipment, key=lambda x: self.value(x, p))
            self.drop(p, cost)
            match = next((x for x in q.hand if x.suit == cost.suit), None)
            if match: self.drop(q, match)
            else:
                self.strip(q, burn=True, random_pick=True)
                self.damage(p, q, 1, "fire")

    def recast(self, p, c):
        if c.name != "连环": raise ValueError("仅连环可重铸")
        self.drop(p, c)
        self.note(f"{p.name}重铸连环，弃牌后摸1张；不作为战法使用")
        self.draw(p, 1)
        self.stats["连环重铸"] += 1

    def play_rage(self, p, c):
        if self.rage_uses and len(p.hand + p.equipment) <= 1: return False
        self.drop(p, c)
        if self.rage_uses:
            self.drop(p, self.rng.choice(p.hand + p.equipment))
        self.rage_uses += 1
        self.rage += 1
        self.actions += 1
        self.note(f"{p.name}使用怒气，下一张杀额外伤害累计{self.rage}")
        return True

    def turn(self, index):
        self.active = index
        p, q = self.players[index], self.players[1-index]
        self.turn_id += 1
        self.rescued.clear()
        p.frozen = False
        self.note(f"{p.name}回合开始")
        skip_draw = False
        for c in list(p.delayed):
            # 前一个判定引起摸牌/拆牌后，后续延时牌可能已经离场。
            if c not in p.delayed: continue
            result = self.divine()
            if not result: continue
            self.drop(p, c)
            if c.name == "天雷":
                if result.rank == 4: self.damage(None, p, 4, "thunder")
                else:
                    self.discard.remove(c); q.delayed.append(c)
            elif c.name == "地火":
                if result.rank == 3:
                    self.damage(None, p, 3, "fire")
                    if q.hp > 0: self.damage(None, q, 2, "fire")
                else:
                    self.discard.remove(c); q.delayed.append(c)
            elif c.name == "久旱": skip_draw |= result.suit in {"♥", "♣"}
            elif c.name == "霜冻": p.frozen |= result.suit in {"♠", "♦"}
            if p.hp <= 0: return
        for _ in range(p.count("赤兔")): self.draw(p, 1)
        if not skip_draw: self.draw(p, 2)
        self.actions, self.used, self.budget, self.rage, self.rage_uses = 0, 0, 1, 0, 0
        p.character.play_phase(self, p)
        if p.hp <= 0 or q.hp <= 0: return
        limit = self.hand_limit(p)
        while len(p.hand) > limit:
            self.drop(p, min(p.hand, key=lambda c: self.value(c, p)))
        for _ in range(p.count("爪黄飞电")): self.draw(p, 1)

    def hand_limit(self, p):
        return p.base_hand_limit + 2 * p.count("凤羽盔")

    def check(self):
        cards = self.deck + self.discard + self.burned
        for p in self.players: cards += p.hand + p.equipment + p.delayed
        assert len(cards) == self.next_id, (len(cards), self.next_id)
        assert len({c.uid for c in cards}) == self.next_id
        assert all(len(p.equipment) <= self.slots(p) for p in self.players)

    def run(self, max_rounds=300, check=False):
        self.note(f"对局开始，{self.players[self.first].name}先手")
        for i in (self.first, 1-self.first): self.draw(self.players[i], 4)
        for round_id in range(1, max_rounds+1):
            for i in (self.first, 1-self.first):
                try:
                    self.turn(i)
                except GameFinished:
                    pass
                for p in self.players: p.silenced = False
                self.note(f"{self.players[i].name}回合结算完成")
                if check: self.check()
                dead = [p for p in self.players if p.hp <= 0]
                if dead:
                    assert len(dead) == 1, "死亡应立即结束，不允许继续结算至双方死亡"
                    alive = self.other(dead[0])
                    self.note("对局结束：" + alive.name + "获胜")
                    return {"winner": alive.name, "rounds": round_id,
                            "winner_side": self.players.index(alive),
                            "first_side": self.first, "first": self.players[self.first].name, "stats": dict(self.stats)}
            for p in self.players:
                if not p.silenced: p.character.on_round_end(self, p)
        self.note("达到回合上限，对局未结束")
        return {"winner": "未结束", "winner_side": -2, "rounds": max_rounds,
                "first_side": self.first, "first": self.players[self.first].name, "stats": dict(self.stats)}
