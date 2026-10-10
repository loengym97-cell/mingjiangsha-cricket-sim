from .v4 import AI as Parent
from ..base import ATTACK, WEIGHTS
from deck import EQUIPMENT

class AI(Parent):
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
