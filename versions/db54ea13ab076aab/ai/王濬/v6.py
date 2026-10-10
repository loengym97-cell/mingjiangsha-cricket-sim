from .v1 import AI as Parent
from ..base import ATTACK, WEIGHTS
from deck import EQUIPMENT
from .v3 import AI as TacticalAI

class AI(Parent):
    version = "v6"
    defer_wash = TacticalAI.defer_wash

    def transform_card(self, g, p, eligible):
        c = TacticalAI.transform_card(self,g,p,eligible)
        if c.name in ATTACK and sum(x.name in ATTACK or x.name=='易' for x in p.hand)==1 and g.can_attack(p,g.other(p)) and g.used<g.budget:
            return None
        if c.name in {'怒气','易','蟠桃'} and p.hp<=2: return None
        return c

    def transform_option(self,g,p,options):
        return TacticalAI.transform_option(self,g,p,options)
