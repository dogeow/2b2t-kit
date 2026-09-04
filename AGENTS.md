# [AGENTS.md](http://AGENTS.md)

这是本地 Minecraft 工具箱工作区，**日常开发目标是 `2b2t-kit/`**。根目录本身不是 git 仓库。

## 工作区布局

```text
minecraft-kit/
├── 2b2t-kit/              # 主项目：Fabric 客户端 Mod（独立 git，基于 fabric-example-mod 26.1.2）
├── meteor-client-source/    # Meteor Client 上游源码，默认只当参考，不要改
├── meteor.md                # Meteor 功能索引与分工对照，写新功能前先查
├── jdk25/                   # 捆绑 Temurin 25（macOS aarch64）
├── net/                     # 少量 Minecraft 26.x 映射残片，不可编译、不要当源码改
└── temurin25.tar.gz         # JDK 压缩包，不要提交或解压覆盖
```

版本以 `2b2t-kit/gradle.properties` 为准（`version` / `runtime_engine_version`），`2b2t-kit/README.md` 可能落后。

## 技术栈（2b2t-kit / mod id: twob2tkit）


| 项   | 值                                                   |
| --- | --------------------------------------------------- |
| 游戏  | Minecraft 26.1.2                                    |
| 加载器 | Fabric Loader 0.19.3 + Fabric API `0.155.2+26.1.2`  |
| 构建  | Java 25、Gradle 9.5.1、Fabric Loom 1.17               |
| 环境  | 仅客户端（`fabric.mod.json` → `"environment": "client"`） |
| 包名  | `dev.twob2tkit`                                    |
| 配置  | `/Applications/.minecraft/config/twob2tkit.json`   |


与 Meteor **没有** Addon API 依赖。飞行靠玩家自己开的第三方飞行；本 Mod 只模拟原版 `KeyMapping.setDown` / `KeyMapping.click`。

Meteor 源码面向 **26.2**，2b2t-kit 是 **26.1.2**。对照 API 时先在 Yarn/Loom 映射里确认，不要直接抄 Meteor 的 26.2 签名。

## 本机路径

游戏是 HMCL，目录是 `/Applications/.minecraft`，**不是** `~/Library/Application Support/minecraft`，也不是项目里的 `run/`。


| 用途     | 路径                                                                         |
| ------ | -------------------------------------------------------------------------- |
| 源码     | `/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit`                          |
| JDK    | `/Users/sam/Code/DogeOW/minecraft-kit/jdk25/Contents/Home`                 |
| 热加载引擎  | `/Applications/.minecraft/config/twob2tkit/runtime/twob2tkit-engine.jar` |
| 完整 Mod | `/Applications/.minecraft/mods/twob2tkit-<版本>.jar`                        |
| 配置     | `/Applications/.minecraft/config/twob2tkit.json`                          |
| 各功能诊断 | `/Applications/.minecraft/config/twob2tkit/<module>.log`（`ModuleFileLog`） |
| 盾构诊断 | `/Applications/.minecraft/config/twob2tkit/borer.log`（`BorerFileLog`）     |
| 挖树诊断 | `/Applications/.minecraft/config/twob2tkit/chopper.log`（`ChopperFileLog`） |
| 种田诊断 | `/Applications/.minecraft/config/twob2tkit/planter.log`（`PlanterFileLog`） |
| 游戏日志 | `/Applications/.minecraft/logs/latest.log`（`[twob2tkit/<module>]`）         |


不要主动跑 `./gradlew runClient`、`./gradlew genSources` 或长时间 Gradle 任务，除非用户明确要求。也不要去改 `jdk25/`。更细的热更新说明见 `2b2t-kit/HOT-RELOAD.md`。

## 运行日志

诊断盾构 / 找矿 / 卡住时**先读运行日志**，不要只猜代码。用户说「检查」时，从下面水印的**下一行**往下读，读完更新水印。

| 文件 | 路径 | 内容 |
| --- | --- | --- |
| 游戏日志 | `/Applications/.minecraft/logs/latest.log` | 完整：`start` / `mining-target` / `cannot-break` / `VERTICAL_*` / `skip-ore`；各功能：`[twob2tkit/<module>]` |
| 盾构专用 | `/Applications/.minecraft/config/twob2tkit/borer.log` | 同上（1.6.145 起找矿也会写入；以前只在回家时写，会缺本局） |
| 挖树专用 | `/Applications/.minecraft/config/twob2tkit/chopper.log` | `start` / `lock-tree` / `clip-miss` / `clip-switch` / `mine-fail` / `periodic` |
| 种田专用 | `/Applications/.minecraft/config/twob2tkit/planter.log` | `start` / `clip-miss` / `harvest-stall` / `periodic` / `stop` |
| 喂养 | `.../feeder.log` | `start` / `approach-stuck` / `feed-fail` / `periodic` / `stop` |
| 钓鱼 | `.../fisher.log` | `start` / `inventory-full` / `no-rod` / `periodic` / `stop` |
| 巡航 | `.../cruise.log` | `start` / `unstick` / `periodic` / `stop` |
| 围箱 | `.../surround.log` | `start` / `no-block` / `place-fail` / `out-of-reach` / `periodic` / `stop` |
| 打猪人 | `.../brawler.log` | `start` / `no-ammo` / `no-bow` / `stuck-bow` / `periodic` / `stop` |
| 下界顶 | `.../nether-roof.log` | `start` / `pearl-throw` / `pearl-fail` / `no-pearl` / `periodic` / `stop` |
| 建造 | `.../builder.log` | `start` / `approach-stuck` / `place-fail` / `no-block` / `periodic` / `stop` |
| 战斗 | `.../combat.log` | `hurt` / `death` / `protect-arm` |

- 水印记「实际读到的最后一行」：路径 + 行号 + 时间戳/短摘。不要整段粘进文档。
- `latest.log` 游戏重开会轮转：文件变短或开头时间更新则从第 1 行重读。
- `borer.log` 超 256KB 会拦腰截断；行号对不上就从文件头重读。
- `chopper.log` 同样 256KB 截断；挖树卡住先读这个，不要只猜 `AutoChopper`。
- `planter.log` 同样 256KB 截断；种田打掉围墙或空挥先读这个。
- 其它功能同样 256KB 截断，文件名见上表。卡住先读对应 `config/twob2tkit/<module>.log`。
- 主机 `LogReview` 扫除盾构外的这些日志；盾构卡住走「想想」（`BorerAreaThinkAsk`）。

**当前水印（2026-09-02）**

- `minecraft-exported-crash-info-2026-09-02T18-48-33`；18:48:27 **1.6.291** 区域挖刚开、封水 3 次失败 → `liquid-abandon` → `area-think` 时 `areaShaftColumn` 仍为 null → NPE。引擎 **1.6.292** 先 `ensureShaftColumn` 再想想
- `latest.log` / `borer.log` 见上包内 `minecraft.log` 第 **1671–1674** 行

## 两套产物，不要搞混


| 改了什么                                                | 产物                                           | 安装到哪                                              | 怎么生效                  |
| --------------------------------------------------- | -------------------------------------------- | ------------------------------------------------- | --------------------- |
| 盾构 / 找矿 / 向下挖 / 铺路 / 拾取 / 垂直寻路                      | `build/runtime-engine/twob2tkit-engine.jar` | `config/twob2tkit/runtime/twob2tkit-engine.jar` | **热加载**，不用关游戏         |
| 界面、巡航、挖树、种田、按键、Mixin、`BorerHost` 新方法、`fabric.mod.json` | `build/libs/twob2tkit-<version>.jar`        | `mods/twob2tkit-<version>.jar`                   | **必须退出 Minecraft 再开** |


热加载 **只换引擎 jar**。不要把整包 `twob2tkit-*.jar` 丢进 `config/twob2tkit/runtime/`。`mods/` 里只能留 **一个** `twob2tkit-*.jar`。

能热更新的源码只限 `src/client/java/dev/twob2tkit/runtime/engine/`（`DefaultTunnelBorerEngine`、`BorerAim`、`BorerHazards`、`BorerItems`、`BorerThreats`、`BorerTrail`、`OreTarget`）。巡航、挖树、界面、Mixin、`TunnelBorer`、`BorerHost` 热加载无效。

主机功能按子包组织（`dev.twob2tkit.<feature>`）：`villager`、`chopper`、`planter`、`fisher`、`feeder`、`surround`、`piglin`、`storage`、`recipe`、`structure`、`adventure`、`borer`、`cruise`、`combat`、`nether`、`builder`、`logreview`、`aihud`、`survival`。入口与 ClickGui 等仍在根包 `dev.twob2tkit`。

## 热更新（只改了 engine）

1. `gradle.properties` 里 `version` 和 `runtime_engine_version` 一起加一号。
2. `DefaultTunnelBorerEngine.RUNTIME_VERSION` 改成同一个号。
3. 编译并只复制引擎：

```bash
JAVA_HOME=/Users/sam/Code/DogeOW/minecraft-kit/jdk25/Contents/Home \
  /Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/gradlew \
  -p /Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit jar --offline

mkdir -p /Applications/.minecraft/config/twob2tkit/runtime
cp /Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/build/runtime-engine/twob2tkit-engine.jar \
   /Applications/.minecraft/config/twob2tkit/runtime/twob2tkit-engine.jar
```

1. 游戏里点 **设置 → 检查并加载新版**，或 `/twob2tkit reload`。加载成功聊天会写引擎版本号；会先停当前盾构并松键。失败会继续用旧引擎，不要当已更新。
2. 告诉用户：只改挖矿/盾构时 reload 即可，**不要**说关游戏。

「恢复内置版本」会丢掉热加载包，回到当前 mods 里那份主机自带的引擎。

## 主机更新（改了界面 / 巡航 / 挖树 / 种田 / Mixin）

```bash
JAVA_HOME=/Users/sam/Code/DogeOW/minecraft-kit/jdk25/Contents/Home \
  /Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/gradlew \
  -p /Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit jar --offline

rm -f /Applications/.minecraft/mods/twob2tkit-*.jar
cp /Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/build/libs/twob2tkit-<新版本>.jar \
   /Applications/.minecraft/mods/

cp /Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/build/runtime-engine/twob2tkit-engine.jar \
   /Applications/.minecraft/config/twob2tkit/runtime/twob2tkit-engine.jar
```

然后 **完全退出 Minecraft 再开**。F3+T、`/reload`、热加载引擎都不够。对用户要明确说关游戏重开，不要说「reload 就行」。

## 2b2t-kit 代码地图

入口与编排：

- `KitClient` — `ClientModInitializer`，客户端指令、按键、tick 分发
- `KitController` — 高空巡航（升空 → 转向前进 → 绕障 → 到达/离线）
- `KitConfig` — Gson 配置；新增字段要有合理默认值
- `KitKeys` / `KitKeyBindsScreen` — 按键；语言键在 `assets/twob2tkit/lang/{zh_cn,en_us}.json`

界面：五个标签在 `KitTab`（巡航 / 生电 / 保护 / 助手 / 设置）。屏幕继承 `KitHudScreen`，绘制用 Minecraft 26 的 `extractRenderState(GuiGraphicsExtractor, ...)`，**不要**写回旧版 `render(GuiGraphics, ...)`。

功能模块（包内 `final class`，几乎都是 package-private）：


| 模块   | 类                                                                    | 说明                    |
| ---- | -------------------------------------------------------------------- | --------------------- |
| 巡航   | `KitController`, `CruiseCeilingMiner`, `NetherRoofAssist`     | 模拟跳跃/潜行/前进；可挖开挡路天花板   |
| 盾构   | `TunnelBorer` + `runtime/`                                           | 向前挖 / 向下挖 / 自动找矿，可热加载 |
| 围箱   | `AutoSurround`                                                       | 圆石等方块把自己围起来           |
| 建造   | `MachineBuilder`, `TechMachines`, `SchematicLoader`                  | 生电机全息与摆放、schematic 导入 |
| 助手   | `AutoFeeder`, `AutoPlanter`, `AutoChopper`                            | 喂养 / 种田 / 挖树            |
| 保护   | `SurvivalAlertMonitor`, `AdventureMonitor`, `ContainerAssistant`     | 提醒、死亡点、开箱补货           |
| 本地知识 | `LocalRecipes`, `LocalRecipeBookInjector`, `LocalAdvancementManager` | 不向服务器伪造配方或进度          |


Mixin（`src/client/resources/twob2tkit.client.mixins.json`，`JAVA_25`）：

- `MinecraftTickMixin`（priority 2000，`tick` HEAD）— 在玩家采样按键**之前**写入移动/挖掘输入
- `MinecraftTickTailMixin`（priority 500，`tick` RETURN）— Meteor 改朝向之后把巡航朝向写回去
- `MouseHandlerMixin` — 全息预览滚轮；鼠标转动后重新施加朝向
- 其余：潜行放置、配方书、本地进度、登录种子哈希、中键选取全息方块

## 运行时引擎边界

稳定核心（改完需重启）：

- `dev.twob2tkit.runtime.api.BorerEngine`
- `dev.twob2tkit.runtime.api.BorerHost`
- `TunnelBorer`（`URLClassLoader` 加载外部 jar）

可热加载（`runtimeEngineJar` 只打包这些）：

- `dev.twob2tkit.runtime.engine.*`（入口 `DefaultTunnelBorerEngine`）

规则：

- 引擎代码只能依赖 `runtime.api` 和 Minecraft/Fabric，不能反向依赖 `TunnelBorer` 等核心类。
- `build.gradle` 的 `verifyRuntimeEngineJar` 会失败，如果引擎 jar 漏了 `DefaultTunnelBorerEngine`，或误打进 `runtime/api`。
- 热加载用的是 **子 ClassLoader，只隔离 `dev.twob2tkit.runtime.engine.*`**。`BorerHost` 走主机那份。引擎不能依赖「主机已经是新接口」。
- **不要**在 `BorerHost` 上加没有 `default` 的新方法后只热加载引擎。旧主机会 `NoSuchMethodError` 崩游戏（2026-08-14 已发生：`borerCoalXpMode`）。新方法必须有 `default`；引擎里调用新方法要用反射，找不到就当 false / 默认值。
- `BorerHost.apiVersion()` / `BorerEngine.requiredHostApiVersion()` 目前是 `1`。破坏性宿主 API 才加版本，不要随手改。
- 同步 bump `version` 与 `runtime_engine_version`。

## 写新功能前：先查 Meteor

这台机器上 Meteor 是常开的。**新功能一律先确认 Meteor 有没有，别重复造轮子。**

1. **先查 `meteor.md`**（按分类列了 Meteor 全部模块）。拿不准就 `rg` 一下 `meteor-client-source/`。
2. **Meteor 有 → 不要重写**，界面上引导用户开对应模块即可。
3. **Meteor 有但不够 → 只补差额**，并且要能共存：给一个「这块交给 Meteor」的开关，
   关闭时本模块不抢视角、不抢按键、不抢攻击充能。参考 `KitConfig.brawlerMeleeEnabled`——
   关掉之后 `PiglinBrawler` 只做 KillAura 不做的事（反弹恶魂火球、拉弓、飞行拉扯）。
4. **确实没有 → 才新写**，写完回来更新 `meteor.md` 第 4 节的对照表。

已经踩过的坑：Meteor 的 `world/auto-breed` 早就能喂食动物繁殖，但仓库里又写了一份 `AutoFeeder`。
同类欠债（`selectWeapon` vs `combat/auto-weapon`、`selectTool` vs `player/auto-tool`）都记在
`meteor.md` 第 4.1 节。收敛这些的时候按第 3 条办，加开关，不要直接删功能。

另外注意「同名不同事」：`combat/surround` 是脚下放黑曜石防水晶爆炸，本仓库的 `AutoSurround`
是把人整个封进方块盒子躲怪，两者不是一回事。

## 开发约定

- 默认只改 `2b2t-kit/`。未明确要求时不要改 `meteor-client-source/`（GPL-3.0）。
- 写新功能前先查 `meteor.md`，见上一节。Meteor 有的就用它的，不够就写增强让它配合。
- 不要把 Meteor 加进 `build.gradle` 依赖；不要用 Meteor Addon API。
- 移动、挖掘、放置走原版按键/点击，让 Meteor Auto Tool、隔空放置等仍能接手。不要另发一套破坏/放置包。
- `/twob2tkit ...` 是 Fabric 客户端指令，不会进服务器聊天。
- 配方书增强不得伪造服务器配方编号；本地进度只写本机配置。
- 新增按键必须同时改 `KitKeys`、`zh_cn.json`、`en_us.json`。
- 界面文案可以中文；代码标识符、配置键、枚举名用 ASCII。
- 类默认 package-private；只有 Mixin 和入口需要 `public`。
- 停止任何自动动作时释放本 Mod 按下的键，并尽量同步真实鼠标状态。
- 不要回滚用户已有的无关改动。
- **落差 / NoFall**：只改 `BorerFallPolicy`。没开 NoFall 最多 3 格，开了最多 48 格；安全落差要走下去，不要铺路，也不要写死「只许 1 格」。往更高矿走时 1 格台阶仍要走，不要空站「前方落差不跳」。回归测试：`BorerFallPolicyTest`。改走路/铺路前先跑 `./gradlew test`。
- **挖树捡东西**：只改 `ChopperLootPolicy`。树苗卡在树冠时要飞过去，不要关飞行按跳；地面只跳一格台阶。弹跳造成的距离抖动不算靠近。回归测试：`ChopperLootPolicyTest`。
- **挖树遇铁傀儡**：只改 `ChopperCombatPolicy`。铁傀儡不是 `Enemy`，只扫敌对会漏掉。KillAura 开着或傀儡在打你时停砍、切剑、飞到头顶交给杀戮光环，不要拿着剪刀继续砍/补种。回归测试：`ChopperCombatPolicyTest`。
- **挖树补种卡叶墙**：只改 `ChopperApproachPolicy`。走向树桩时准星打在树叶上要先剪，不要对着叶墙按 W 直到 approach-stuck。回归测试：`ChopperApproachPolicyTest`。
- **找矿捡掉落物**：只改 `BorerLootPolicy`。背包多几颗不算捡完；地上还有同类就要继续。原版拾取垂直只有 0.5 格，坑底安全落差要走下去；1×1 坑挖头开 1×2。回归测试：`BorerLootPolicyTest`。
- **身旁矿 / 没视线空等**：只改 `BorerOrePolicy`。勾选矿在身旁一格、高度差 ≥ -1（含通道地板、立足点和头顶天花板）且够得着时要挖，不要报「没有可挖视线」，也不要站住「不退出通道」。脚下矿落地不安全（岩浆/虚空/超深）才跳过。选矿时身旁/脚下优先于远处同层。回归测试：`BorerOrePolicyTest`。
- **向下挖阶梯**：只改 `BorerStairPolicy`。矿比脚低 1 是地板那层，平着走；低 2 格才下台阶。前方 1 格落差直接走，不要「向下挖阶梯」空站。Meteor Step 且头顶已通时跨 1 格高，不要挖掉台阶。回归测试：`BorerStairPolicyTest`。
- **通道居中**：只改 `BorerCenterPolicy`。碰撞箱已经刮到侧壁才横移；略偏中心不要在 1×2 里左右撞墙。矿在附近更高/更低处不要沿通道走回头。已选的通道前方不要用后来拧向矿的朝向当成侧壁丢掉。对角接近时保持当前轴向，不要每拍在东西/南北间切换。回归测试：`BorerCenterPolicyTest`。
- **准星打得到却提示打不到**：只改 `BorerMiningPolicy`。勾选矿够得着时，准星打到矿就挖矿；轴向打到旁边挡路就改挖挡路，不要当侧壁丢掉后空转。脚前矿头前石头先挖头。回归测试：`BorerMiningPolicyTest`。
- **回家路点**：只改 `BorerTrailPolicy`。金色箭头沿已挖 1×2 走；主世界不用下界门当家；人还在巷道里重新开盾构不要清路点。回归测试：`BorerTrailPolicyTest`。
- 不要为无关改动去引入新的测试框架。已有的 JUnit 5 只测这种容易被改掉的规则。

## 常见坑

- **输入时序**：26.1 里玩家在 `Minecraft.tick` 开头采样 `KeyMapping`。盾构/巡航输入必须在 HEAD mixin 里写好；写在 `END_CLIENT_TICK` 就晚了，表现为“按着键但人不动”。
- **朝向争夺**：Meteor 会在 tick 中改视角。巡航依赖 `MinecraftTickTailMixin` + `MouseHandlerMixin.turnPlayer` 再写回朝向。
- **按键争夺**：Meteor 的 `anti-afk` 每 tick 都会写跳跃/潜行/左右键（`jump` 那条还会强制松开玩家自己按下的空格）。用户报「自己跳一下、手动跳不了」「自己蹲下」「自己左右横移」时先怀疑它，不要在本 mod 里瞎找。完整清单见 `meteor.md` 第 2 节。
- **热键 vs 输入框**：`KitHudScreen` 在 `EditBox` 获得焦点时忽略开关 GUI 的键，但紧急停止（默认 End）始终有效。
- **冲突模块**：`tickNavigation` 同时只跑一个动作（盾构 > 围箱跳过巡航 > 喂养/种田/挖树/下界顶 > 巡航）。新自动模块要挂进这条链，并在停止时松键。
- **不破坏基岩/屏障/容器/刷怪笼**；不自动拆下界基岩。
- **Loom `splitEnvironmentSourceSets`**：客户端代码在 `src/client/java`，资源在 `src/client/resources` 与 `src/main/resources`。Mixin JSON 改了要同步 `fabric.mod.json`。
- **落差被改没**：1.6.149 修挖穿立足点时写成「空气就铺路、只许下 1 格」，把 8 月 15 日的 NoFall/3 格约定盖掉了。落差规则在 `BorerFallPolicy`，有 `BorerFallPolicyTest`。
- **矿更高就空站 1 格落差**：往上走时把所有落差都禁了，前方 1 格空气也 WAIT「前方落差不跳」。1 格台阶要走。规则在 `BorerFallPolicy.shouldWalkIntoDrop(drop, climbing)`。
- **贴着矿空等**：1×2 已通、矿在下一格地板时，轴向 `horizontalDistance <= 1` 会标 `frontOccluded`，通道扫描又不扫 y-1。规则在 `BorerOrePolicy`。
- **头顶矿不挖**：矿就在 1×2 天花板（dy=2），旧规则 dy≤1 不当身旁矿，确认挖掉旁边石头后继续开通道。规则在 `BorerOrePolicy.mineAdjacentInsteadOfWait`。
- **够得着却拧视角**：准星打不到就「走近再挖」，`walkForwardCentered` 把视角拧向矿；下一拍又选隔壁柱子高于通道的沙砾。规则在 `BorerStairPolicy.keepAimingInsteadOfWalking` / `ignoreOverheadFalling`。
- **贴坑沿对准再挖卡住**：立足点列和身体列差一格，对着打不中的侧石空挥，10 秒后把矿 skip 掉。1×2 用 `blockPosition` 朝矿开；`keepAiming` 要准星真打到；非矿石头超时只换块。规则在 `BorerStairPolicy.tryOreHeadingFirst`。
- **向下挖阶梯空走**：矿只低 1 格（地板那层）或前方已是 1 格落差时不要进 `VERTICAL_DOWN` 空站。1 格落差走下去；Meteor Step 跨 1 格高。规则在 `BorerStairPolicy`。
- **下去后 1 格高过不去**：脚前空气、头前石头，垂直寻路因头挡住不能走就报没有落脚。人的判断是挖头。规则在 `BorerStairPolicy.mineHeadToOpenOneByTwo`。
- **贴边卡住**：人偏出格子中心，碰撞箱刮到侧壁，1×2 已通还去挖隔壁石头，准星打不中就按 W。规则在 `BorerCenterPolicy`。
- **1×2 左右撞墙**：1.6.159 用 0.06 偏移就横移，两边都是石头时来回撞；矿在头顶还会沿通道走回头。规则在 `BorerCenterPolicy.overlapsSideWall` / `stayAndClimb`。
- **对角找矿左右横摆**：顺路矿 dx≈dz 时朝向在北/西之间切换，再走进落差，人在格边来回走。对角保持当前轴向；矿在更高处不跳深坑，1 格台阶要走。规则在 `BorerCenterPolicy.stableAxisHeading` / `BorerFallPolicy.shouldWalkIntoDrop(drop, climbing)`。
- **准星/HUD 闪动**：找矿每 tick `lockHeadingToward` 矿，垂直寻路选出的正前方被 `isOffCorridorWall` 当成侧壁丢掉，下一拍再选回来。规则在 `BorerCenterPolicy.isOffCorridorWall`。
- **轴向打不到对角矿**：矿在斜前方、距离 1.5，`lookAxis` 锁东/北打到旁边石头；`isOffCorridorWall` 把这块石头丢掉，然后报准星打不到。够得着时打到矿就挖，打到挡路就改挖挡路。规则在 `BorerMiningPolicy`。
- **脚前矿头前石头准星不命中**：矿在 1×2 脚那层、头前是石头，眼睛在头那层，lookAxis 打到头却死盯矿，每 tick 清目标。先挖头。规则在 `BorerMiningPolicy.mineHeadToSeeAdjacentOre`。
- **脚底矿不挖**：勾选矿在身旁/脚下那层，前方墙还在或立足点就是矿，也要挖，不要「不退出通道」空站。挖了会掉进岩浆/虚空/超深才跳过。规则在 `BorerOrePolicy.mineAdjacentOre`。
- **先挖远处同层、脚下不挖**：旧 `approachScore` 把垂直差 ×25，4 格外平地矿压过脚下矿；身旁扫描还跳过脚下。近的先挖。规则在 `BorerOrePolicy.approachScore`。
- **挖树抬头卡住**：树冠原木被树叶挡住，`mine()` 裁剪对不上就松手，却仍 `return` 不飞不走。挡住就砍树叶，砍不成则飞近。过程写 `chopper.log`。
- **挖树捡东西一直跳**：捡掉落物时强制关飞行，树苗在树冠上就按跳，弹跳还把 stuck 计时清掉。树苗高了要飞；地面只跳一格。规则在 `ChopperLootPolicy`。
- **挖树剪刀打铁傀儡**：KillAura 实体列表勾了铁傀儡时，挖树换剪刀砍挡路树叶，光环就拿剪刀抽傀儡。铁傀儡不是 `Enemy`，旧逻辑不停砍、不切剑、不飞。规则在 `ChopperCombatPolicy`。
- **挖树补种卡在树叶里**：砍完去补种只看树桩坐标按 W，叶墙够得着也不剪。卡住后 `clearTree()` 把树苗清掉还会 NPE。规则在 `ChopperApproachPolicy`。
- **剪刀砍树叶一直 stage=-1**：秒破点一下后立刻松左键，原版 `continueAttack(false)` 会 `stopDestroyBlock`。要点并在这一拍按住。规则在 `ChopperMinePolicy`。
- **挖树闪屏 / 人晃**：够得着还「飞近再砍」会开关飞行、准星在树叶和树干间甩、提示每拍重刷。够得着就站住砍挡路树叶。规则在 `ChopperApproachPolicy`。
- **剪刀快坏挖不动**：Meteor `auto-tool` 开了 `anti-break` 会取消破坏。不要把快坏剪刀握在手上，叶子改空手。规则在 `ChopperToolPolicy`。
- **够得着停住砍**：准星对不齐就松手站住，没有超时。够得着要瞬间对准并砍准星那块，约两秒还对不齐就跳过。规则在 `ChopperApproachPolicy`。
- **游戏里问 Grok 看日志**：`LogReview` 扫各功能 `config/twob2tkit/*.log`，卡住问本机 Grok 或 `xai.key`。过程画在屏幕左上角固定面板（`AiHud`，不跟镜头）。课也进聊天。不改 jar。规则在 `LogReviewPolicy`。盾构想想同样走这块面板。
- **挖矿提示跟着人晃**：旧 `BorerHud` 把状态钉在准星前的 3D 字上。改由 `BorerScreenHud` 画在屏幕正中下方，转头跑步都不跟。区域黄框/回家箭头仍钉世界坐标。
- **钻石掉坑里不捡**：背包一增加就结束本轮，坑里剩下的丢掉；原版拾取垂直只有 0.5 格，1 格深的坑沿站着够不着。规则在 `BorerLootPolicy`。
- **回家箭头穿墙斜线**：主世界把下界门坐标当成路点 0，开局再清成「门+脚底」两条，金色箭头就指着墙壁。箭头只画巷道上相邻路点。规则在 `BorerTrailPolicy`。
- **回家箭头画在远处下层**：人在 Y=-31，路点在 Y=-50，always-on-top 穿到当前 1×2。只画同一层眼前的段，从脚边开始。规则在 `BorerTrailPolicy.drawSegmentNearPlayer`。
- **种田挖掉围墙**：收成伪造 `BlockHitResult` 按左键，真实准星打到 9×9 土墙就把墙挖了，作物还在所以「收了 0」。准星打到作物才挖；田边土墙不锄。规则在 `PlanterPolicy`。
