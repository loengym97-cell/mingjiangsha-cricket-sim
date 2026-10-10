from .v1 import AI as Parent
from ..base import ATTACK, WEIGHTS
from deck import EQUIPMENT

class AI(Parent):
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
