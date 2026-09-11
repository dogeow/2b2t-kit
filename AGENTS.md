# AGENTS.md

## 项目边界

- 主项目是本目录 `2b2t-kit/`：Minecraft 26.1.2、Fabric、Java 25；版本以 `gradle.properties` 为准。
- 客户端源码在 `src/client/java/dev/twob2tkit/`。可热加载实现只在 `runtime/engine/`；`runtime/api/` 与宿主保持稳定。
- 相邻 `meteor-client-source/` 默认只供参考，不修改；其版本可能不同，使用 API 前核对当前游戏。优先复用或协调 Meteor 已有功能，不重复抢按键、视角和物品栏。
- 保留用户已有改动、区域坐标、工程进度和个人配置；不为测试覆盖真实存档或设置。

## 运行与交付

- 实际游戏目录：`/Applications/.minecraft`，不是项目的 `run/` 或用户 Library 目录。
- 配置：`config/twob2tkit.json`；运行日志：`logs/latest.log` 与 `config/twob2tkit/*.log`，均相对于实际游戏目录。
- 引擎产物：`build/runtime-engine/twob2tkit-engine.jar` → 游戏的 `config/twob2tkit/runtime/twob2tkit-engine.jar`。
- 主包产物：`build/libs/twob2tkit-<version>.jar` → 游戏的 `mods/`；这里只保留一个本 Mod 主包，替换前备份旧版。
- 只改引擎：同步版本、构建校验，部署引擎后用 `/twob2tkit reload` 生效。界面、按键、Mixin、宿主或依赖变化需要完整重启游戏，明确告知用户。
- 引擎不能反向依赖宿主实现；新增稳定接口须考虑旧宿主兼容，不能只换引擎就假定新接口已存在。只有破坏性接口变化才提高 API 版本。

## 基本要求

- 游戏动作使用正常输入或 Minecraft 交互接口；不伪造破坏结果、瞬移或已完成状态。
- 停止、退出和切换功能时释放本功能持有的按键，恢复临时接管的飞行、背包和其它模块设置，不覆盖用户后续手动修改。
- 自动挖掘保护容器、基岩等不可破坏方块；保留液体、危险落差和物资保护。丢弃贵重物品或其它破坏性行为必须有明确授权。
- 诊断先检查实际日志和当前代码；确认模式、版本和时间，不把旧记录或其它功能的日志当成当前复现。
- 修改关键行为时补充对应回归测试；区分编译通过、逻辑测试、安装完成和实机验证，不夸大验收结果。

## 验证

在本项目目录使用捆绑 JDK 25：

```bash
JAVA_HOME=/Users/sam/Code/DogeOW/minecraft-kit/jdk25/Contents/Home ./gradlew test jar verifyRuntimeEngineJar --offline
```

- 部署后校验版本和文件哈希。未明确要求时，不运行 `runClient`、`genSources`，不修改捆绑 JDK。
- 本文件只保留长期有效的项目约束；具体 bug、日志流水和修复历史放在测试或功能文档中，不继续堆积在这里。
