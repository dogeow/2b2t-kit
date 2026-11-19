# 2026-11-03 自动找矿新增「岩浆块」

- 引擎 `OreTarget` 与宿主 `TunnelBorer.OreTarget` 新增 `MAGMA`（岩浆块），匹配 `minecraft:magma_block` 方块与掉落物。
- 与沙砾相同属于只能单独勾选的建材目标（`explicitOnly()`）：不计入「任意矿石」，不触发时运选镐。原有不站在岩浆块上、遇岩浆停、封液体等保护不变。
- 回归：`OreTargetTest.magmaIsAnExplicitMaterialTargetRatherThanPartOfAnyOre`。离线 Gradle 仍缺 Loom 1.17-SNAPSHOT，未跑整套 JUnit；用捆绑 JDK 25 对 26.2 客户端编译通过，并以相同断言的独立程序（引导注册表）跑过 18 项全部通过。

## 安装（未经 Gradle 构建，按类替换）

- 先核对：游戏中生效引擎、模组内嵌备用引擎、宿主枚举三处类与改动前 HEAD 源码反汇编一致，再只替换 `runtime/engine/OreTarget.class` 与 `borer/TunnelBorer$OreTarget.class`。
- 版本号未变（主包 2026.11.02.18，引擎 1.8.57），以文件哈希区分。
- 备份与哈希：`config/twob2tkit/backups/2026-11-03-magma-ore-target/`（`before.sha256` / `after.sha256`）。
  - 主包 `038f04c3…` → `8abd640a…`；引擎 `da8530d1…` → `f32d339a…`。
- 宿主界面改动需完整重启游戏生效；尚无实机验收。

## 站在岩浆块上「潜行并挖开离开」不动

- 实机（01:30:50–01:31:52）：脚下岩浆块时每帧先 `releaseMine`（`stopDestroyBlock` 清零进度）再 `keepMiningInReach`，逃生口的岩浆块永远挖不完；`handleMagmaBurn` 还会每帧重选方向。专挖岩浆块后频繁触发。
- 修复：`BorerLiquidPolicy.keepMagmaExitDig` 在脚下岩浆块、无岩浆接触/不在水中、目标仍是岩浆块时不松手；`handleMagmaBurn` 沿用仍可挖的当前逃生口。回归 `BorerLiquidPolicyTest.standingOnMagmaKeepsDiggingTheMagmaExitInsteadOfResettingEveryTick`。
- 安装：先核对生效引擎中 `DefaultTunnelBorerEngine`（含工作区未提交改动）、`BorerLiquids`、`BorerLiquidPolicy` 共 6 个类与改动前源码一致，再只替换这 6 个类。引擎 `f32d339a…` → `fbf64336…`，备份 `config/twob2tkit/backups/2026-11-03-magma-exit-dig/`。模组内嵌的备用引擎未含此修复。需 `/twob2tkit reload` 生效；尚无实机验收。

## 专挖岩浆块时蹲着挖，不再「飞行离开」

- 实机：01:35:55 以 `ore=MAGMA` 启动即「enabled Meteor Flight to clear a step」飞走；站在岩浆块上走 `handleMagmaBurn` 的逃离/起飞分支。
- 修复：`sneakOnMagma`（`BorerLiquidPolicy.sneakOnMagma`）仅在找矿勾选岩浆块、未飞行、脚下或前方落脚是岩浆块、脚下与四周无岩浆、未接触岩浆、不在水中时成立：接触逃离直接放行，`unsafeToWalk` 不把这类岩浆块地面算作危险，`tick` 收尾在引擎运行中补按潜行（中途多处会松开潜行）。停止后不再按住。回归 `BorerLiquidPolicyTest.magmaMiningCrouchesOnMagmaUnlessLavaIsBesideOrBelow`。
- 安装：基线核对为上一次补丁的 6 个类，再替换同样 6 个类。引擎 `fbf64336…` → `31e44f01…`，备份 `config/twob2tkit/backups/2026-11-03-magma-sneak/`。需 `/twob2tkit reload`；尚无实机验收。下落到岩浆块（`fallLandingSafe`、`columnWalkableForDescend`）仍按原规则避开。

## 地面下的岩浆不再挡住平走路线

- 实机：01:44–01:45:49 已连续挖并拾取 29 个岩浆块（挖前先封邻接岩浆）。01:46 站在 y=28，脚下 y=27 实心、y=26 岩浆湖，所有目标都被 `skipOrDetour` 以「岩浆 …26… 挡住通往矿脉的通路」跳过：`inStandColumn` 把不会被挖的地面按「挖开会露出岩浆」计入。
- 修复：`BorerLiquidPolicy.ignoreLiquidUnderFloor`——找矿勾选岩浆块且目标不低于脚下时，路线与绕行点的地面只在本身是岩浆/水时挡路；需要往下挖时仍按原规则。身体两格与目标本身、挖前封岩浆不变。回归 `BorerLiquidPolicyTest.flatMagmaRouteIgnoresLavaUnderAnUnminedFloorButDescentStaysStrict`。
- 安装：基线核对为上一次补丁，替换同样 6 个类。引擎 `31e44f01…` → `9ba253a7…`，备份 `config/twob2tkit/backups/2026-11-03-magma-floor/`。需 `/twob2tkit reload`；尚无实机验收。

## 走上安全岩浆块拾取掉落物

- 实机：重载后已挖到 225 个；01:50:56、01:51:05 掉落物落在 3 格外的岩浆块上，连续 8 秒无进展后暂缓（`loot-defer`）。`isStandable` 对岩浆块恒为 false，`BorerWalkRoute` 的落脚判断也排除岩浆块。
- 修复：`safeMagmaFloor`（`BorerLiquidPolicy.safeMagmaFloor`）——找矿勾选岩浆块时，下面、四周及其上方落脚格四周都没有岩浆的岩浆块可站；`isStandable` 与拾取寻路的落脚判断采用它，行走时由 `tick` 收尾补按潜行。回归 `BorerLiquidPolicyTest.magmaMiningMayStepOntoMagmaWithoutLavaToPickUpDrops`。
- 安装：前三个类基线为上一次补丁，`BorerWalkRoute`（含 `$1`）基线为 HEAD 源码，共 8 个类核对一致后替换。引擎 `9ba253a7…` → `aa13f393…`，备份 `config/twob2tkit/backups/2026-11-03-magma-loot/`。需 `/twob2tkit reload`；尚无实机验收。

## 安全岩浆块地面不再报「前方地板不安全」

- 实机：01:55 起反复「目标路线前方地板连续 4 秒不安全，铺路和跳过都没成」并跳过目标。扫描确认脚下和前方整片都是岩浆块，范围内无岩浆。`unsafeToWalk` 放过了岩浆块检查，但最后的 `safeFallDepth` 仍把岩浆块落点当危险。
- 修复：`unsafeToWalk` 在落差扫描前，前方脚下是安全岩浆块即可走。接线回归 `BorerMagmaWalkWiringTest`（ASM 读类，确认调用顺序）。
- 安装：引擎 `aa13f393…` → `eb3ef19f…`，备份 `config/twob2tkit/backups/2026-11-03-magma-walk/`。注意：此次替换时接线检查因类路径先加载 ASM 9.6（不支持 Java 25 类文件）没有跑成，命令未中止；随后用 ASM 9.10.1 对已安装的类补跑，通过。

## 顺路经过岩浆块也蹲着走

- 用户要求：不只是专挖岩浆块，挖其它矿顺路经过岩浆块也潜行通过。`sneakOnMagma`、`safeMagmaFloor` 改用 `magmaWalk()`（向前挖、向下挖、自动找矿；区域挖保留原规则）。「地面下的岩浆不算挡路」仍只用于专挖岩浆块。顺带把 `unsafeToWalk` 被隔开的原注释移回。
- 安装：基线为上一次补丁，仅 `DefaultTunnelBorerEngine` 字节码变化；替换前在新 jar 上跑 4 项接线检查（失败即中止）。引擎 `eb3ef19f…` → `8eb4f078…`，备份 `config/twob2tkit/backups/2026-11-03-magma-roadside/`。需 `/twob2tkit reload`；尚无实机验收。

## 拾取时斜向起跳擦侧墙、与侧墙规则来回打架

- 实机（02:01:05–02:01:09，重载 01:59:40 后）：掉落物在东侧 3.3 格、高 1 格；`hopBody` 按略偏北的偏航延伸 0.85 格，擦到北侧 z=99988 的下界岩，`hopObstruction` 把它设为 `loot-hop-clearance`，引擎随即按侧墙规则作废（`skip-side-wall`），下一帧又挑另一块，循环 8 秒后暂缓。扫描确认正东起跳空间 `94225,33~35,99989` 全空。
- 修复：`walkToward` 起跳空间被挡时，先试 `BorerLootPolicy.axisYaw` 对正到最近的东南西北，对正后干净且前方无岩浆就按对正方向跳；`hopObstruction` 跳过已被作废的目标（`isMiningTargetSuppressed` 改为包内可见）。回归 `BorerLootPolicyTest.diagonalHopSnapsToTheNearestAxisInsteadOfMiningSideWalls`。
- 安装：`BorerLoot`、`BorerLootPolicy`（含内部类）基线为 HEAD 源码，其余为上一次补丁，12 个类核对一致；替换前在新 jar 上跑起跳与之前的接线检查（失败即中止）。引擎 `8eb4f078…` → `359fb6d3…`，备份 `config/twob2tkit/backups/2026-11-03-magma-hop/`。需 `/twob2tkit reload`；尚无实机验收。

## 不再在岩浆块上垫方块又挖掉

- 用户报告：一直在岩浆块上放垫脚方块，然后挖掉，反复循环。`shouldBridgeDrops` 用 `safeFallDepth` 判断前方落差，岩浆块落点算危险，于是 `placeWalkingSupport` 在岩浆块上方垫块；该块挡住岩浆块目标或掉落物，又被挖掉。
- 修复：`dropOntoSafeMagma`（`BorerLiquidPolicy.dropOntoSafeMagma`）——向前挖/向下挖/找矿时，前方往下 0–3 格空气后落到安全岩浆块：`shouldBridgeDrops` 不铺路，`unsafeToWalk` 视为可走（取代上一版只看平地的判断），`sneakOnMagma` 在即将落到安全岩浆块时也按住潜行。回归 `BorerLiquidPolicyTest.shortDropOntoSafeMagmaIsWalkedNotPaved`、`BorerMagmaWalkWiringTest.walkwayPavingSkipsDropsOntoSafeMagma`。
- 安装：`BorerPlace` 基线为 HEAD 源码，其余为上一次补丁，13 个类核对一致；替换前在新 jar 上跑 9 项接线检查和策略断言（失败即中止）。引擎 `359fb6d3…` → `d073d6c0…`，备份 `config/twob2tkit/backups/2026-11-03-magma-drop/`。需 `/twob2tkit reload`；尚无实机验收。

## 地面方块挖了又出现：止循环并补日志（原因未定）

- 实机：02:10:46 重载 `d073d6c0…` 后，02:10:47–57 在 x=94239/94240 两格间来回，轮流挖脚下 `94239/94240 29 99995` 下界岩；每次 `server-cleared-block` 后同一格又是下界岩。目标岩浆块在北 17 格、低 2 格，寻路以「下降接近矿石」挖地面。下方 y=28 下界岩、y=27 岩浆块、y=26 岩浆海（扫描确认）。按 `safeFallDepth` 落一格到 y=28 是安全的，`shouldBridgeDrops` 不应补；放置逻辑此前不写日志，无法分辨是 Kit 补回还是服务器回滚。
- 处理：`setMiningTarget` 对服务器确认挖掉后 10 秒内再次成为目标的非下落方块记 `block-reappeared`，第 3 次暂停挖它 30 秒（`BorerMiningPolicy.reappearedAfterClear`、`suppressReappearedBlock`）；`rememberPlacedSupport` 为每次放置记 `place-block pos block via=调用方法`。回归 `BorerMiningPolicyTest.aFloorBlockThatKeepsComingBackIsSuppressedOnTheThirdTime`、`BorerReappearWiringTest`。
- 安装：`BorerMiningPolicy` 基线为 HEAD 源码，其余为上一次补丁，14 个类核对一致；新 jar 上跑全部策略断言与接线检查后替换。引擎 `d073d6c0…` → `fba3f9db…`，备份 `config/twob2tkit/backups/2026-11-03-reappear-guard/`。需 `/twob2tkit reload`；根因待新日志确认。
