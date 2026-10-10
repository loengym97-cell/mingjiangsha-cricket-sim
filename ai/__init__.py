"""统一入口：按武将、策略版本创建独立AI实例。"""
from .base import ATTACK, WEIGHTS, BaselineAI
from .王濬 import VERSIONS as WANG
from .甘宁 import VERSIONS as GAN
from .白板 import VERSIONS as BLANK

AI_REGISTRY = {"王濬": WANG, "甘宁": GAN, "白板": BLANK}
AI_LABELS = {"v1": "基线 v1", "v2": "择机装备 v2", "v3": "转化优化 v3",
             "v4": "保命装备 v4", "v5": "先杀后洗 v5", "v6": "保留关键牌 v6", "v7": "距离拆牌 v7"}
AI_CHOICES = {"王濬": ["v1", "v3", "v6"], "甘宁": ["v1", "v2", "v4", "v7"], "白板": ["v1"]}

def create_ai(version, role):
    versions = AI_REGISTRY.get(role.name, {"v1": BaselineAI})
    if version not in versions:
        raise ValueError(f"{role.name}没有AI版本{version}")
    return versions[version](role)

