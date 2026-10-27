# 项目清理审查 · 2026-10-17

> 以下保留首轮审计时的证据和状态。用户随后要求“全部修正”，24项现均已处理；逐项差异、补充修正和最终测试结果见[修正验收记录](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/README.md)。删除文件的原位置以对应补丁为准。

## 范围、结论和修改边界

实际项目是 `/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit`，当前分支 `26.1.2`、HEAD `37ebe2c`；实际 Minecraft 版本以 `gradle.properties` 的 **26.2** 为准，不能从分支名判断。外层仓库只有初始提交；本报告的历史均来自内层项目仓库。

审查前工作区已有大量修改和未跟踪文件。检查覆盖修改前的 506 个生产 Java 文件、356 个 Java 测试文件、755 个 Python 文件（346 个生产文件），以及资源注册、Gradle、CI、依赖和 companion-skills。相邻 Meteor 源码和捆绑 JDK 按 AGENTS.md 作为参考/工具，不作为本项目的清理对象。未访问 Notion，未启动、连接、安装或重载游戏。

共记录 **24 项**：14 项 Java 遗留/重复/测试孤岛，3 项 Python 闲置函数，5 项测试问题，2 项 CI 优化。它们的置信度和处理方式不同，不能一律直接删除。本轮唯一代码修改是 **01：删除 7 行 BuildMovement**；其余保持原样，没有实际 diff。报告和独立补丁属于本次交付资料。

“无引用”表示核对了仓库内生产、测试、字符串反射、资源注册、Gradle/CLI 入口；无法证明任意仓库外临时脚本绝不调用公开函数。Git 历史按提交记录描述，不能据此确定当前未提交修改的作者。

## 已执行的验证

| 验证 | 结果 |
| --- | --- |
| 修改前强制重跑 Java 测试 | 355 个 suite，2,048 tests，0 failure/error/skip |
| 修改后强制重跑 Java 测试 | 2,048 tests，0 failure/error/skip |
| 修改后 jar、verifyRuntimeEngineJar、verifyOptionalMapIntegration | 全部通过；当前版本 JAR 不再包含 BuildMovement.class |
| 完整离线 Gradle build | 通过；热缓存增量构建 profile 总计 0.877 秒 |
| Python 固定离线集，104 个模块 | 1,822 tests，94.874 秒；1 failure + 2 errors，见 21、22 |
| 上述 3 个失败测试精确复跑两轮 | 每轮均同样 1 failure + 2 errors（0.047/0.044 秒），是确定性失败 |
| Python 相关 6 模块 | test_colored_pipeline、test_furnace_batches、test_potato_farm、test_wheat_farm、test_physical_idle、test_session_readiness：89 tests 通过 |
| companion-skills | 37 tests 通过 |
| Python 全目录只读 discovery | 405 个运行时测试模块，4,220 个执行项、4,202 个唯一 ID、0 导入错误；未执行全量套件 |
| 重复收集涉及的三个模块 | 35 个执行项通过，0.171 秒，含 18 次多余执行 |
| kit_cli 竞态验证 | 正常重复 60 例通过；只延迟测试回包写入 150ms 后，两个相关测试均触发 JSONDecodeError |

Python 使用既有 `/Users/sam/Library/Application Support/MinecraftDecisions/venv/bin/python`。只读 discovery 禁止文件写入、网络、子进程和线程启动，没有触发被禁止操作。Java 首次普通运行命中测试缓存，因此表中采用随后明确 `--rerun` 的结果。

Java 复验命令：

```sh
JAVA_HOME=/Users/sam/Code/DogeOW/minecraft-kit/jdk25/Contents/Home \
  ./gradlew test --rerun jar verifyRuntimeEngineJar verifyOptionalMapIntegration --offline
```

Python 固定集命令：

```sh
'/Users/sam/Library/Application Support/MinecraftDecisions/venv/bin/python' decision-runtime/check_offline.py
```

## Java 发现

### 01 · 已删除：旧 BuildMovement

- **位置/引用：** 删除前 `src/client/java/dev/twob2tkit/builder/BuildMovement.java:1–7`。全库只有类声明、构造器和同名测试类名；无调用、注册或反射。生产 [ProjectionBuildJob.java:316](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/builder/ProjectionBuildJob.java:316) 调用 `navigation.motion()`；[BuildMovementTest.java:5](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/test/java/dev/twob2tkit/builder/BuildMovementTest.java:5) 也直接测试 DefaultBuildNavigation。
- **历史：** `6da06e9`（2026-09-22）引入热加载导航，同次将实际调用和测试迁移，旧类注释已经标为 Legacy；之后无修改。
- **风险/收益：** 极低。删除 7 行，避免误用已经与新导航漂移的到达阈值；构建收益可忽略。不删除或改名现有测试，不变更 runtime/api。
- **测试/diff：** 修改前后全量 Java 各 2,048 tests 通过，包含 BuildMovementTest、BuildNavigationReloadTest；两项打包验证通过。[独立补丁](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/2026-10-17-buildmovement.diff)。

### 02 · 重复站位枚举 BuildStations

- **位置/引用：** [BuildStations.java:7](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/builder/BuildStations.java:7) 与 [DefaultBuildNavigation.java:23](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/runtime/engine/DefaultBuildNavigation.java:23) 的枚举循环、距离判据和排除规则相同。生产 ProjectionBuildJob:283 使用 `navigation.stations()`；旧类只被 BuildStationsTest:7、15 调用。
- **历史：** `6da06e9`（2026-09-22），与导航迁移一起引入。
- **风险/收益/下一步：** 低。先把旧测试改测真实导航，再删旧类 18 行，保留边界覆盖；运行 BuildStationsTest、BuildPathTest、BuildNavigationReloadTest。仅减少维护重复，不能声称明显提速。

### 03 · 无引用的 AdventureScreen 旧入口

- **位置/引用：** [AdventureScreen.java:10](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/adventure/AdventureScreen.java:10) 只转到 AssistHomeScreen，没有实例化、注册、反射或测试引用；实际 KitTab:53 直接创建 AssistHomeScreen。
- **历史：** `eb86c4d`（2026-09-04）初始提交已经标为“旧入口”；`394949a`（2026-10-14）只适配新 `minecraft.gui.setScreen` API，未恢复入口。
- **风险/收益/下一步：** 低，27 行兼容外壳可独立删除；运行 Java 全量测试与编译，保留真实助手页面。收益是减少旧入口混淆。

### 04 · 未采用的 SessionLog 包装

- **位置/引用：** [SessionLog.java:6](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/SessionLog.java:6) 只有自身声明和内部调用；没有类型使用、实例化或注册，不是稳定 runtime/api。
- **历史：** 仅 `eb86c4d`（2026-09-04），原意是单功能 start/stop/periodic/once 诊断包装。
- **风险/收益/下一步：** 低；独立删 38 行未采用机制，编译、Java 测试和 jar 检查即可。无可量化运行时收益。

### 05 · 失去入口的 BorerScreenHud

- **位置/引用：** [BorerScreenHud.java:12](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/borer/BorerScreenHud.java:12) 的 show/hide/render 没有调用；KitClient.renderScreenHud:365–370 不渲染它。BorerScreenHudBridge 反射的是宿主方法，不能按名称相似视作调用此类。
- **历史：** `eb86c4d`（2026-09-04）引入；`3d02f68`（2026-09-27）加入 WorkHud 存在时隐藏；`394949a`（2026-10-14）适配 HUD API。
- **风险/收益/下一步：** 低至中，66 行；应先确认是否仍有恢复旧面板的产品意图，再独立移除。BorerHost:184、188 的空默认实现属于另一问题，删除本类并不能修复 HUD。运行 Java 全量测试、相关宿主连线检查。

### 06 · BorerHotReloadPolicy 只有孤立测试

- **位置/引用：** [BorerHotReloadPolicy.java:4](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/borer/BorerHotReloadPolicy.java:4) 只被 BorerHotReloadPolicyTest:12–15 调用；生产没有 jarNewer/stable/STABLE_TICKS 引用。
- **历史：** 仅 `eb86c4d`（2026-09-04），原意是等待复制中的 JAR 稳定。
- **风险/收益/下一步：** 低至中；20 行及其孤立测试。先确认自动监测 JAR 的需求是否废弃，再删除，或把需要的规则接入实际加载流程并验证。保留真实手动热加载和兼容检查；收益是避免虚假的生产覆盖印象。

### 07 · 废弃的自动改源码/部署链

- **位置/引用：** [BorerAreaThinkDeploy.java:17](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/runtime/engine/BorerAreaThinkDeploy.java:17)。生产调用全部消失；仅 BorerAreaThinkPolicyTest:175 调 nextPatchVersion，ReadOnlyTest:17 是禁止调用的负向断言。
- **历史：** `eb86c4d`（2026-09-04）引入；`59f3cc4`（同日）改 mod ID；**`76aee4b`（2026-10-02）明确将 BorerAreaThinkAsk 改为只读 HTTP 建议，删除 CLI/sourceRoot/deploy 调用，遗留此类。**
- **风险/收益/下一步：** 低；独立删除 172 行过时的源码写入/构建/部署代码，并处理仅服务于它的版本号测试。运行 BorerAreaThinkReadOnlyTest、BorerAreaThinkPolicyTest、引擎 JAR 检查。不要改只读限制。

### 08 · PrinterPulse 模型未接入真实打印

- **位置/引用：** [PrinterPulse.java:4](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/automation/PrinterPulse.java:4) 仅 PrinterPulseTest 模拟器使用；ProfessionalPrinter:128、169、179、250 使用 ConfirmedPlacementPacer 和实际服务端确认。
- **历史：** `c1b8a65`（2026-09-12）引入每 20 tick 一次提案的模型。
- **风险/收益/下一步：** 中。仅 7 行，主要问题是孤立模型测试可能被误当成生产节奏覆盖。先核对真实 pacer 对延迟确认的测试，再移除旧模型及模拟测试；保留服务端确认机制。

### 09 · 禁用自动翻耕后的不可达路径

- **位置/引用：** [AutoPlanter.java:707](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/planter/AutoPlanter.java:707)：tillSpot:707–716、selectHoe:1106–1122、hasFarmlandNearby:902–914、isHarvestTarget:753–757 均为 private 且无调用。唯一创建 Action.TILL 的位置是无调用的 tillSpot，因此对应执行/展示分支从当前入口也不可达。
- **历史：** `591110d`（2026-10-03）改为仅维护启动时已有耕地，删除旧调用；PlanterHarvestWiringTest:59–61 明确禁止进入旧翻耕路径。
- **风险/收益/下一步：** 删除无调用 private helper 风险低；继续清理 TILL 枚举与展示分支风险中，应作为一个完整旧翻耕问题单独处理。约 45 行 helper 可减少；运行 PlanterHarvestWiringTest 和田地边界/策略测试，保留“不自动翻耕”覆盖。

### 10 · 删除旧表单后遗留的界面 helper

- **位置/引用：** [ClickGuiPages.java:841](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/ClickGuiPages.java:841)：chipAreaSize:841–850、setCoord:890–915、currentX:918–920、currentZ:923–925 都是 private 且只有声明，无反射或测试引用。
- **历史：** `eb86c4d`（2026-09-04）引入；`c1b8a65`（2026-09-12）删除旧区域/坐标表单调用，却保留 helper。
- **风险/收益/下一步：** 低，约 42 行方法正文；可按“旧坐标表单残留”独立清理，运行界面/坐标解析相关测试及编译。避免误修改当前坐标输入逻辑。

### 11 · ChopperToolPolicy 是未接入的策略测试

- **位置/引用：** [ChopperToolPolicy.java:9](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/chopper/ChopperToolPolicy.java:9) 仅同名测试调用；AutoChopper:796–828 选工具没有调用 tooWorn。
- **历史：** `eb86c4d`（2026-09-04）引入后未修改。
- **风险/收益/下一步：** 中；39 行可能保存未接入的耐久保护意图。先判断规则应接入还是已废弃，再单独处理并增加真实执行链验证。直接删孤立测试会丢掉需求记录；潜在收益是让测试覆盖与实际工具选择一致。

### 12 · ChopperApproachPolicy 是未接入的接近策略

- **位置/引用：** [ChopperApproachPolicy.java:9](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/chopper/ChopperApproachPolicy.java:9) 仅同名测试引用；生产 approach 没有调用这套清叶/飞越决策。
- **历史：** `eb86c4d`（2026-09-04）引入后未修改。
- **风险/收益/下一步：** 中；75 行。应先明确生产需要的接近规则，再处理旧策略与测试。运行同名策略测试和实际接近连线测试；收益是消除两套互不相连的行为描述。

### 13 · ChopperCombatPolicy 与实际威胁判断脱节

- **位置/引用：** [ChopperCombatPolicy.java:9](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/chopper/ChopperCombatPolicy.java:9) 只有同名测试引用；测试含铁傀儡威胁，实际 AutoChopper.nearbyHostile:763–772 只判断 Enemy。
- **历史：** `eb86c4d`（2026-09-04）引入后未修改。
- **风险/收益/下一步：** 中；38 行。先确认实际威胁需求，再接入必要规则或独立废弃；不能仅删策略就声称战斗保护已修复。需要验证实际 nearbyHostile 调用链；收益是减少测试与生产行为不一致。

### 14 · ChopperMinePolicy 只有布尔模型测试

- **位置/引用：** [ChopperMinePolicy.java:6](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/src/client/java/dev/twob2tkit/chopper/ChopperMinePolicy.java:6) 无生产调用，同名测试只验证其布尔表达式。
- **历史：** `eb86c4d`（2026-09-04）引入后未修改。
- **风险/收益/下一步：** 中；30 行。先把需要的挖掘保护映射到真实链路及测试，再独立删旧模型。收益是避免只测试一份生产未使用的规则。

## Python 发现

### 15 · colored_pipeline._distribution 遗留

- **位置/引用：** [colored_pipeline.py:341](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/decision-runtime/material_jobs/colored_pipeline.py:341)，341–348 只有定义，无调用、导入或字符串引用。当前 283–298 行委托 processing 按实际允许燃料规划。
- **历史：** `76aee4b`（2026-10-02）引入；`394949a`（2026-10-14）删除唯一调用，取消强制煤炭估算，改用实际允许燃料。
- **风险/收益/下一步：** 低，私有 helper 8 行；可独立删除，运行 test_colored_pipeline。相关基线已通过。减少旧煤炭策略歧义，无明显速度收益。

### 16 · 土豆专用包装 _potato 已被泛化入口替代

- **位置/引用：** [potato_farm.py:311](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/decision-runtime/potato_farm.py:311)，311–312 仅定义；实际 416 行调用 `_seed(proxy,crop,snapshot)`。
- **历史：** `76aee4b`（2026-10-02）原土豆实现；`591110d`（2026-10-03）泛化为土豆/小麦并迁移调用，保留包装。
- **风险/收益/下一步：** 低；仓库外临时脚本仍有极小不确定性。独立删 2 行，运行 test_potato_farm、test_wheat_farm，二者基线已通过。

### 17 · loading_balance 是闲置的即时检查包装

- **位置/引用：** [furnace_batches.py:140](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/decision-runtime/furnace_batches.py:140)，140–143 仅定义。生产及测试均调用 wait_loading_balance，等待版在 154 行直接调用相同 `_loading_matches`。
- **历史：** `3d02f68`（2026-09-27）同时引入两种包装，实际加载路径从引入时就用等待版；`76aee4b`（2026-10-02）扩展燃料参数后继续遗留。
- **风险/收益/下一步：** 低至中，因为是公开命名函数，不能完全排除仓库外调用。独立删 4 行，保留等待与物品守恒检查；运行 test_furnace_batches，基线已通过。

## 测试问题

### 18 · 导入 TestCase 导致 18 次重复执行

- **位置/引用：** [test_owned_grass_refill.py:5](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/decision-runtime/test_owned_grass_refill.py:5)、[test_registered_grass_bed.py:3](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/decision-runtime/test_registered_grass_bed.py:3) 导入 test_direct_clay_refill.Tests 为 DirectFixture，只用其 setUp，却被 unittest 同时收集9条测试。全目录仅这两处同类导入。
- **历史：** 三个文件均未跟踪，没有可归因提交历史；不能推断加入时间或作者。
- **验证/风险/收益/下一步：** 4,220 项对比 4,202 唯一 ID，9条各出现3次，额外18次；三模块35次执行全部通过。低风险改为模块导入后调用 fixtures.Tests.setUp(self)，保留17个唯一测试。节时不到约0.1秒，主要收益是统计和覆盖准确；需复查 loader ID 去重与三模块测试。

### 19 · test_kit_cli 回包 fixture 的可复现线程竞态

- **位置/引用：** [test_kit_cli.py:48](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/decision-runtime/test_kit_cli.py:48)、97、100 在响应线程直接 write_text 最终 reply/status；[kit_cli.py:108](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/decision-runtime/kit_cli.py:108) 发现文件即解析，可能读到刚创建但未写完的 JSON。
- **历史：** 普通命令例来自 `3d02f68`（2026-09-27），补给例来自 `5798dd5`（2026-10-12）。生产 AutomationBridge:4532、MaterialTaskChannel:53–58 用临时文件加原子替换，fixture 与生产发布契约不同。
- **验证/风险/收益/下一步：** 正常60例全通过；仅在 fixture 打开文件与写数据间注入150ms延迟，两例均 JSONDecodeError。证明竞态窗口存在，**未在自然重复中观察到随机失败**。低风险将测试回包也改为临时文件原子发布；保留异步确认和不重复请求的断言，再重复测试及延迟验证。删除测试会丢失覆盖，不建议。

### 20 · 固定离线测试依赖旧版本安装 JAR

- **位置/引用：** [test_material_bulk_diorite.py:29](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/decision-runtime/test_material_bulk_diorite.py:29) 每次 setUp 强读 `/Applications/.minecraft/versions/26.1.2/26.1.2.jar`，没有 skip 或自包含 fixture；check_offline.py:15 固定纳入。当前项目是26.2。
- **历史：** `1174062`（2026-10-05）新增批量闪长岩配方/容量回归。
- **验证/风险/收益/下一步：** 模拟旧 JAR 缺失即 FileNotFoundError，这是确定性环境依赖，**不是 flaky**。低至中风险：批次逻辑使用小型 fixture JAR，真实版本集成另留有条件检查；不能直接删配方及容量断言。收益是无需旧游戏安装即可运行离线集，并明确测试哪一版本配方。

### 21 · 箱子阻挡测试的异常预期已漂移

- **位置/引用：** [test_targeted_supply.py:289](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/decision-runtime/test_targeted_supply.py:289)，289–297 仍期望 RuntimeError。当前 container_access.py:24–30、53 改为 OutdoorChestLandingBlocked(OutdoorChestChanged)，material_jobs_backend.py:825–830 捕获来源变化后保留证据，908行返回 waiting。
- **历史：** 测试来自 `3d02f68`（2026-09-27），本次行为变化来自当前已有的未提交工作，未归因给某个历史提交。
- **验证/风险/收益/下一步：** 固定集失败，精确两轮均“RuntimeError not raised”。中风险，先确认新语义，再验证 waiting、阻挡证据和无 approach/取料动作。删除风险高，会丢失箱子接近保护覆盖；收益是恢复可信的离线基线。

### 22 · 两条固定树测试缺少新增前置检查的 fixture 字段

- **位置/引用：** [test_material_jobs_acquisition.py:850](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/decision-runtime/test_material_jobs_acquisition.py:850)、886；公共 FakeClient:20–35 缺 task。当前未提交 acquisition.py:2144–2145 调用新 fixed_tree_ground.prepare，其20行还检查材料租约及落地状态。
- **历史：** 两测试分别来自 `40f3e92`（2026-10-06）、`394949a`（2026-10-14）；新 helper 未跟踪，调用变更属于现有未提交工作。
- **验证/风险/收益/下一步：** 固定集两错误，精确两轮均在对应 protocol=1/enabled=True 分支 AttributeError。低至中风险补齐 fixture 的归属和已落地状态，或由专门 helper 测试承担前置检查并隔离领域测试；不移除生产安全校验。收益是恢复两条真实树根选择回归覆盖。

## 构建耗时

### 23 · CI 没有配置 Gradle 缓存

- **位置/引用：** [build.yml:11](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/.github/workflows/build.yml:11)，使用临时 ubuntu runner；17–21行 setup-java 没有 cache，24–25行直接 gradlew build，全工作流没有 setup-gradle/actions-cache 或其他缓存配置。
- **历史：** 项目内最近修改为 `eb86c4d`（2026-09-04），当前仍沿用该配置。
- **风险/收益/下一步：** 低至中；为依赖和可安全复用的 Gradle 状态配置受维护的缓存机制，可减少重复下载和 Loom 处理。需要实际连续两次 CI 比较冷/热耗时，并核查 PR 缓存写入权限及缓存失效规则；本轮未运行远端 CI，**没有编造节省秒数或百分比**。这是比删几十行代码更值得验证的提速候选。

### 24 · push 和 pull_request 可能重复构建同一次更新

- **位置/引用：** [build.yml:7](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/.github/workflows/build.yml:7) 无条件同时监听 push/pull_request，且没有 concurrency。仓库内功能分支存在开放 PR 时，一次 push 可同时触发两套相同 build；连续推送也不会取消过期构建。
- **历史：** 当前行为保留自 `eb86c4d`（2026-09-04）。默认远端分支当前是26.1.2，应以真实分支策略配置，不能假设 main/master。
- **风险/收益/下一步：** 低至中；独立调整触发范围与同目标旧运行取消策略，保留主分支和 PR 所需检查。上述条件下可从两次完整任务减少为一次，节省约一个构建的 runner 工作量；**这不是单次构建耗时减半的承诺**。需用实际 PR/推送事件验证 required checks 没有遗漏，本轮不改发布流程。

## 没有判定为可删的内容

- **无用依赖：** 没有找到可确认删除的直接依赖。Fabric API 有实际事件/注册用途，JUnit/launcher 用于测试；httpx 被 decisions、local_decision_runtime、ollama_decision 使用；可选 laya-mlx 在 decisions:58–59 延迟导入。不能把可选依赖等同于废弃依赖。
- **API route：** 项目没有普通 Web API route 目录；主要是 AutomationBridge/MaterialTaskChannel 的本机操作接口。独立 CLI、外部控制器和动态动作名属于调用入口，不能因没有 Java 静态调用就删。此次没有确认可安全删除的操作接口。
- **Mixin/CLI/反射：** 36 个 Mixin 均与配置一一对应；VillageHintCli 由 build.gradle 的 JavaExec 启动；local_decision_runtime.py 由 Java LocalDecisionRuntime 启动，material_jobs_cli.py 由 MaterialJobs 启动；companion-skills 可从 skillctl.py/CLI 到达。稳定 runtime/api 默认方法不按零直接引用删除。
- **双份引擎：** 主包顶层 engine class 与嵌入 runtime-engine.jar 不是本次可删的重复；TunnelBorer.loadBuiltIn:543–550 还需要主包类加载器提供内置回退，热加载使用独立 loader。
- **直接不可达语句：** Python 全量 AST 没有发现 return/raise 后紧接的无条件不可达语句；Java 可明确报告的是09所述旧翻耕路径，不扩张为所有低引用分支都不可达。
- **构建实测排除：** 完整热缓存 build 的 profile 总计0.877秒；sourcesJar0.146秒，两项包验证0.017/0.009秒。删除源码包、关闭验证、提高堆或打开 configuration cache 都没有本次证据支持为“明显提速”，因此不改。
- **flaky 判断边界：** 固定随机种子、虚拟时钟和 ASM/源码连线测试不因重构敏感就被判为 flaky；本轮确认的是19的可复现调度窗口，20–22属于确定性环境/fixture问题。

## 后续处理顺序

下一轮优先独立处理19的测试回包发布，其次分别处理21和22恢复离线基线，再考虑07的废弃部署链。每轮只选一项，保留现有用户改动，先保存该项基线、做最小修改、运行相关测试并交付单独 diff；涉及测试孤岛的策略，先确认实际规则应接入还是废弃。
