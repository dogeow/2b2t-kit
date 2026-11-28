# twob2tkit

Minecraft 26.2 的 Fabric 客户端 Mod，提供采矿、巡航、生产、仓储和生存保护等自动化功能。

- 所有动作都通过普通游戏输入完成，服务器不需要装任何 Mod。
- 可以和 Meteor 一起用；投影建造会配合 Litematica / Printer。
- 运行逻辑放在可热更新的引擎里，多数更新不用重启游戏。

## 安装

1. 安装 Minecraft 26.2 的 Fabric Loader 和 Fabric API。
2. 把 Releases 里的 `twob2tkit-<version>.jar` 放进 `.minecraft/mods`，只保留一个版本。
3. 可选：Meteor Client、Litematica + Printer。

## 使用

按 `U` 打开工具箱。左侧导航栏按分类列出所有功能，可以搜索和收藏，运行中的功能带绿点。右侧是功能页，页头有状态和 开始/停止 按钮。打开页面不会自动开始任何任务。

| 分类 | 功能 |
|---|---|
| 挖掘 | 区域挖、自动找矿（配合 Xray，含水下采沙砾）、隧道掘进、挖矿路线与安全 |
| 出行 | 自动巡航（绕障、挂机保护、下界基岩顶）、地点与死亡点、风景预加载、附近结构与世界种子 |
| 生产 | 砍树、种田、喂养、钓鱼、农场管家、混凝土制作、材料任务、投影建造、打猪人 |
| 仓储 | 仓库记录（开箱自动记录、可搜索）、行动清单与补货、配方指南、村民职业 |
| 保护 | 自动保护与白名单、自动围箱、生存提醒 |
| 设置 | 通用设置、按键绑定、聊天翻译、运行与兼容 |

巡航也可以用指令：`/twob2tkit start <X> <Z> <Y>`。`/twob2tkit help` 列出全部指令。

## 默认按键

| 按键 | 作用 | 按键 | 作用 |
|---|---|---|---|
| `U` | 工具箱 | `End` | 紧急停止 |
| `G` | 开始/停止巡航 | `B` | 盾构机 |
| `H` / `P` | 回家 / 回地狱门 | `V` | 自动围箱 |
| `N` | 自动喂养 | `J` | 自动种田 |
| `K` | 自动砍树 | | |

按键可以在“设置 → 按键绑定”里改。

## 安全

默认在到达目标、陌生玩家靠近（64 格）、生命值不高于 8，或连续 30 秒卡住时自动离线。可以在巡航页修改，或用 `/twob2tkit set ...` 改。低血量触发的安全锁要在游戏里手动解除。

## 热更新

把新的 `twob2tkit-engine.jar` 放进 `.minecraft/config/twob2tkit/runtime/`，再输入 `/twob2tkit reload`。主包本身更新后需要重启游戏。详见 [HOT-UPDATE.md](decision-runtime/HOT-UPDATE.md)。

## 构建

需要 JDK 25：

```bash
./gradlew test jar verifyRuntimeEngineJar --offline
```

开发约定见 [AGENTS.md](AGENTS.md)，更多文档见 [docs/README.md](docs/README.md)。
