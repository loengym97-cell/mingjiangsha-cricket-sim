from .v4 import AI as Parent
from ..base import ATTACK, WEIGHTS
from deck import EQUIPMENT
from .v3 import AI as TacticalAI

class AI(Parent):
    version = "v5"
    defer_wash = TacticalAI.defer_wash
