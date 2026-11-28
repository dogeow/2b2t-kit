# 文档总览

项目约束先读根目录 [AGENTS.md](../AGENTS.md) 与 [CONTRIBUTING.md](../CONTRIBUTING.md)；Python 分层见 [decision-runtime/ARCHITECTURE.md](../decision-runtime/ARCHITECTURE.md)。当前版本以 [gradle.properties](../gradle.properties) 为准，下列文档中的版本号均为写作时的版本。

## 使用说明

- [usage/只开Minecraft的调用方式.md](usage/只开Minecraft的调用方式.md)
- [features/chat-translation.md](features/chat-translation.md)
- [concrete-maker.md](concrete-maker.md)、[placement-speed.md](placement-speed.md)、[material-jobs-ui.md](material-jobs-ui.md)
- 热更新：[decision-runtime/HOT-UPDATE.md](../decision-runtime/HOT-UPDATE.md)
- Meteor 已有功能索引（写新功能前先查）：[../meteor.md](../meteor.md)

## 功能设计与修复记录（2026-09，Minecraft 26.1.2 时期）

| 文档 | 内容 |
|---|---|
| [AREA-MINING.md](features/AREA-MINING.md) | 区域挖检查与修复（至引擎 1.7.20） |
| [ORE-MINING.md](features/ORE-MINING.md) | 自动找矿改进（引擎 1.7.8） |
| [METEOR-MINING.md](features/METEOR-MINING.md) | 挖掘与 Meteor 自动吃 / 自动工具 |
| [BOW-DEFENSE.md](features/BOW-DEFENSE.md) | 骷髅反击 |
| [UI-AND-DEFENSE.md](features/UI-AND-DEFENSE.md) | 界面与区域挖反击 |
| [UI-REDESIGN.md](features/UI-REDESIGN.md) | UI 统一改版（主包 1.9.x） |
| [SCENERY-PRELOAD.md](features/SCENERY-PRELOAD.md) | 风景预加载（Bobby） |
| [CRASH-2026-09-06.md](reviews/CRASH-2026-09-06.md) | 低血自动下线后的 KillAura 崩溃 |

## 投影建造与施工（2026-10 下旬）

- [automatic-construction-loop.md](automatic-construction-loop.md)
- [printer-mode-handoff.md](printer-mode-handoff.md)
- [projected-channel-water.md](projected-channel-water.md)、[projected-component-correction.md](projected-component-correction.md)、[projected-wet-terrain-mining.md](projected-wet-terrain-mining.md)
- [magma-routing-and-packet-sneak.md](magma-routing-and-packet-sneak.md)、[planned-magma-station-check.md](planned-magma-station-check.md)
- [safe-residual-fire-wait.md](safe-residual-fire-wait.md)、[sand-to-glass-batches.md](sand-to-glass-batches.md)、[shallow-pickup-route.md](shallow-pickup-route.md)

## 按日期的记录

- [changes/](changes/)：每次改动的说明，文件名以日期开头。重要节点：
  - [2026-10-14-minecraft-26.2-upgrade.md](changes/2026-10-14-minecraft-26.2-upgrade.md)：升级到 Minecraft 26.2
  - [2026-10-27-remove-harness2.md](changes/2026-10-27-remove-harness2.md)：移除 harness2
- [reviews/](reviews/)：代码审计与事故复盘
- [audits/](audits/)：2026-10-17 全项目清理审计及逐项补丁
- [experiments/](experiments/)：实验记录
