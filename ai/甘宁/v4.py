from .v1 import AI as Parent
from ..base import ATTACK, WEIGHTS
from deck import EQUIPMENT

class AI(Parent):
    version = "v4"

    def choose_equipment(self, g, p):
        if p.name != "甘宁": return super().choose_equipment(g,p)
        # 只为立即回血或濒死保险承受成长代价，其余装备继续洗牌。
        for c in p.hand:
            if c.name == "银狮盔" and p.hp <= 3: return c
            if c.name == "飒露紫" and p.hp <= 1 and not p.has("飒露紫"): return c
        return None
