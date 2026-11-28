# AGENTS.md

## 项目边界

- 主项目是本目录 `2b2t-kit/`：Minecraft 26.2、Fabric、Java 25；版本以 `gradle.properties` 为准。
- 客户端源码在 `src/client/java/dev/twob2tkit/`。可热加载实现只在 `runtime/engine/`；`runtime/api/` 与宿主保持稳定。
- 相邻 `meteor-client-source/` 默认只供参考，不修改；其版本可能不同，使用 API 前核对当前游戏。优先复用或协调 Meteor 已有功能，不重复抢按键、视角和物品栏。
- 保留用户已有改动、区域坐标、工程进度和个人配置；不为测试覆盖真实存档或设置。

## 运行与交付

- 实际游戏目录：`/Applications/.minecraft`，不是项目的 `run/` 或用户 Library 目录。
- 当前隔离实例是 `/Applications/.minecraft/versions/26.2`；旧 `26.1.2` 实例保留用于回退，操作前以当前日志与原生状态确认实例。
- 配置：`config/twob2tkit.json`；运行日志：`logs/latest.log` 与 `config/twob2tkit/*.log`，均相对于实际游戏目录。
- 引擎产物：`build/runtime-engine/twob2tkit-engine.jar` → 游戏的 `config/twob2tkit/runtime/twob2tkit-engine.jar`。
- 主包产物：`build/libs/twob2tkit-<version>.jar` → 游戏的 `mods/`；这里只保留一个本 Mod 主包，替换前备份旧版。
- 构建校验通过后用 `python3 tools/deploy_kit.py`（先加 `--dry-run` 看计划；只改引擎时加 `--engine-only`）部署：自动备份旧包、保证 mods 只留一个主包、校验哈希。
- 只改引擎：同步版本、构建校验，部署引擎后用 `/twob2tkit reload` 生效。界面、按键、Mixin、宿主或依赖变化需要完整重启游戏，明确告知用户。
- 引擎不能反向依赖宿主实现；新增稳定接口须考虑旧宿主兼容，不能只换引擎就假定新接口已存在。只有破坏性接口变化才提高 API 版本。
- 回执清理：`python3 decision-runtime/kit_cli.py replies --finished-receipts`（先看 dry-run，再加 `--apply`）把 7 天前已结束、没有本地记录引用的回执无损压缩；需要时 `--restore reply-<id>.json` 恢复原字节。

## 基本要求

- 继续村民交易中心及配套红石施工时，先读 `work/village-trading-20261017/CURRENT-GOAL.md` 和同目录 `project-state.json`，再核对实时游戏与唯一控制器；具体接续步骤、附魔范围、施工凭证及待恢复现场以这些文件为入口，不能只凭简短的对话目标重开工程。
- 每次有实际进展或交接，更新上述接续记录；一次脚本完成、对话结束或临时停控不代表整体目标完成。
- 用户授权自主操作时，先核对实时健康、环境、界面、控制器和原生安全状态；没有正在进行的人工操作或其他控制器、且状态安全时自行接手和继续，不要求用户反复回复固定口令。手动输入期间立即让出控制，结束后依据实时状态判断能否恢复，不因历史接管记录单独要求确认。
- 原生安全锁、紧急停止及危险保护优先；锁仍生效时遵循 Kit 的受控恢复机制，不绕过锁、不重放结果未知的请求。仅在确实需要用户操作、无法确认安全或存在其他无法自主解决的阻碍时请求用户协助，说明具体原因。

- 调用 Kit 功能优先使用原生接口或 CLI，不用截图、按键或菜单点击替代已有接口；缺少接口时补齐可复用入口。
- 不调用 Jev、Laya、Ollama 等模型做游戏决策（2026-11-28 已移除）；需要在候选间选择时使用调用方给出的本地回退。
- 游戏动作使用正常输入或 Minecraft 交互接口；不伪造破坏结果、瞬移或已完成状态。
- 停止、退出和切换功能时释放本功能持有的按键，恢复临时接管的飞行、背包和其它模块设置，不覆盖用户后续手动修改。
- 自动挖掘保护容器、基岩等不可破坏方块；保留液体、危险落差和物资保护。丢弃贵重物品或其它破坏性行为必须有明确授权。
- 诊断先检查实际日志和当前代码；确认模式、版本和时间，不把旧记录或其它功能的日志当成当前复现。
- 修改关键行为时补充对应回归测试；区分编译通过、逻辑测试、安装完成和实机验证，不夸大验收结果。

## 运行状态

- 下达动作前先看总览：`python3 decision-runtime/kit_cli.py status`（只读）。`notes` 会提示状态过期、安全锁、角色死亡、mods 里有多个主包，以及装好的新版本还没生效。
- 需要家、农场等坐标时用 `python3 decision-runtime/kit_cli.py places [--match 名称]`（只读，家排第一，在线时附带距离），不要自己翻配置。

## 材料来源

- 任务缺材料时，先查仓库记录，再决定采集、合成或请用户补充：
  `python3 decision-runtime/kit_cli.py storage find --item iron_ingot --item coal`（只读，不开箱、不发送动作；游戏未运行时加 `--server simpcraft.com`）。
  不知道物品 id 或要找附魔书时用 `storage find --match mending`（按名称、id、附魔文字搜索）。
- 结果只列当前服务器和维度的记录；`confirmed=false` 表示箱子附近有过变化，需要开箱复核。`confirmed_total` 才是较可信的数量。
- `count` 是箱里散放、可直接取的数量；`packed` 是箱内潜影盒里的数量，要走潜影盒取料流程，不能当作散货。`unknown_shulker_containers` 是旧版本记录、盒内物品未知的箱子数，需要开箱一次才会补全。
- 取料走 `kit_cli.py materials start --item <id> --count N`，只读核对用 `materials stock --depot x y z --out ...`；不要自己解析 `twob2tkit.json` 后直接点箱子。
- 仓库记录只说明去哪里找，不证明有货，以实际开箱看到的槽位为准。开箱、存取和关箱时 Kit 会自动更新记录，箱子关着时的变化看不到。

## Minecraft 知识库

- 用户将原本写入 Obsidian 的 Minecraft 项目知识改为保存到 `https://wiki.dogeow.com/` 的 `Minecraft:` 独立命名空间；其他项目使用各自的命名空间，不混入 Minecraft。
- Wiki 用于用户授权范围内整理过的长期资料；当前任务状态、未确认回执和运行日志继续以本地记录为准，不把未验证内容写成事实。
- 不在仓库、日志或页面中保存账号密码、令牌或其他凭据；写入前核对现有页面和版本，写入后回读确认。Wiki 不可访问时保留本地资料，并如实说明未同步。

## 验证

在本项目目录使用捆绑 JDK 25：

```bash
JAVA_HOME=/Users/sam/Code/DogeOW/minecraft-kit/jdk25/Contents/Home ./gradlew test jar verifyRuntimeEngineJar --offline
```

Python 固定离线测试集使用项目托管环境（已装 `requirements.txt` 依赖）：

```bash
cd decision-runtime && "$HOME/Library/Application Support/MinecraftDecisions/venv/bin/python" check_offline.py
```

- 部署后校验版本和文件哈希。未明确要求时，不运行 `runClient`、`genSources`，不修改捆绑 JDK。
- 本文件只保留长期有效的项目约束；具体 bug、日志流水和修复历史放在测试或功能文档中，不继续堆积在这里。
