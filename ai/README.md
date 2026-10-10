# AI目录维护

每个武将一个文件夹，每个策略版本一个 `v数字.py`。版本文件导出 `AI` 类；该武将的 `__init__.py` 通过 `VERSIONS` 注册版本。`base.py` 只放通用流程和默认估值。

## 修改已有策略

直接编辑对应武将目录的版本文件。通用规则在 `engine.py`，武将技能和属性在 `characters.py`。保存后，等待当前模拟结束，双击上一级的 **重启斗蛐蛐.bat**，再运行新批次。

## 为已有武将新增版本

1. 以王濬为例，新建 `王濬/v8.py`，继承已有策略并覆盖需要改进的方法：

   ```python
   from .v3 import AI as PreviousAI

   class AI(PreviousAI):
       version = "v8"

       def transform_option(self, game, player, options):
           return super().transform_option(game, player, options)
   ```

2. 在 `王濬/__init__.py` 导入 `from .v8 import AI as v8`，并在 `VERSIONS` 中加入 `"v8": v8`。
3. 在 `ai/__init__.py` 的 `AI_LABELS` 中加入 `"v8": "新策略 v8"`，并将 `v8` 加入 `AI_CHOICES["王濬"]`。界面标签保持简短。
4. 重启工作台。选择新版本，用相同种子与旧版进行对比。

旧版本文件尽量保留；改进时新增版本，便于选择与对比。不同武将可以使用相同版本号，注册按“武将名 + 版本号”定位；界面标签目前共用版本号映射，同号策略请使用兼容的简短名称。

## 新增武将

1. 在 `characters.py` 新增技能类，配置血量、留牌上限和装备栏数量，并加入角色 `REGISTRY`。
2. 在此目录新建以武将名命名的文件夹，添加 `v1.py` 和 `__init__.py`。`v1.py` 可以继承 `from ..base import BaselineAI`。
3. 在 `ai/__init__.py` 导入新目录的 `VERSIONS`，加入 `AI_REGISTRY`，并在 `AI_CHOICES` 中配置界面选项。

AI只根据己方手牌、对手公开状态决策，不读取对手暗手牌。每个玩家的技能和AI均为独立实例。

## 验证与历史快照

在 `F:\斗蛐蛐` 运行：

```powershell
python -m unittest discover -s . -p "test_*.py" -q
python simulator.py --diagnostic --games 100 --left-ai v3 --right-ai v7 --check
```

每个正式批次会对整个AI目录中的Python源码计算指纹，并保存到 `versions/引擎指纹/ai/`。旧批次的快照保留当时的目录结构，不要迁移或编辑它们。
