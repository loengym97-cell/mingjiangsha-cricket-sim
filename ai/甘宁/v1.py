from ..base import BaselineAI

class AI(BaselineAI):
    version = "v1"

    def __init__(self, role):
        super().__init__(role)
        self.auto_equips = False

