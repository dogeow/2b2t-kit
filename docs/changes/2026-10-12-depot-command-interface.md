# 补给箱显式命令接口

过去仓库记录的“建造补给”只有界面切换入口。实际补仓库 [761011,64,797851] 时，worker profile 中加入坐标并不能更新主包内存中的补给许可，因此 218 在动作开始前被拒绝。通过真实仓库记录界面登记后，允许源列表和 profile 均为六个。取料仍依赖本地缓存选择来源、实际开箱槽位证明转移，不把登记当成库存证明。

新增显式入口：

```
/twob2tkit supply allow 761011 64 797851
/twob2tkit supply deny 761011 64 797851
python decision-runtime/kit_cli.py supply allow --pos 761011 64 797851
python decision-runtime/kit_cli.py supply deny --pos 761011 64 797851
```

重复允许或取消保持原状态；重复历史许可会合并。仅接受当前服务器、单人存档和维度已有的仓库记录，允许时继续核验容器结构；取消可以处理当前世界已经失效的仓库。既不打开箱子，也不刷新或伪造其中物品数量。

API `projection_supply_set` 通过独立 `projection-supply-request.json` 和 `projection-supply-reply-<id>.json`，不改游戏动作邮箱、控制版本、移动、物品栏或当前物理操作。复用有界、启动前旧请求不重放的 MaterialTaskChannel，检查当前世界、控制版本和有效期；CLI 保留未知请求，拒绝旧世界或不一致回执。状态中的 `projection_supply_protocol=1` 表示宿主提供此入口。

主包版本 2026.10.12.3 构建成功，1928 项 Java 测试及引擎/可选地图打包验证通过。相关 Python 回归 103 项通过。主包按用户要求等待下次更新，当前实机主包仍 2026.10.11.6，因此没有宣称此新 API 已在运行中可用；本轮施工继续使用已存在的 Kit 原生接口。
