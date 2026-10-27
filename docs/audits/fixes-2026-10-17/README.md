# 逐项修正记录 · 2026-10-17

初轮审计的24项均已处理，另完成25–27三项必要补充。01在首轮已经完成，其余均基于收到“全部修正”时的工作区逐项备份、修改、定向测试和保存差异。未提交、推送、安装或连接游戏。

[初轮证据、引用关系、Git历史、风险与收益](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/2026-10-17-project-cleanup.md) · [合并净差异](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/all-fixes.diff) · [机器可读验收记录](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/validation.json)

## 每项处理和独立 diff

| 编号 | 问题 | 最终处理 | 定向验证 | Diff |
| --- | --- | --- | --- | --- |
| 01 | 旧 BuildMovement | 删除无调用旧导航；保留真实引擎测试 | Java全量通过 | [01](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/01-buildmovement.diff) |
| 02 | 重复 BuildStations | 站位边界测试改测真实导航，删除重复类 | 3个相关suite通过 | [02](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/02-build-stations.diff) |
| 03 | AdventureScreen | 删除无入口兼容外壳 | HUD/配置相关suite通过 | [03](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/03-adventure-screen.diff) |
| 04 | SessionLog | 删除未采用的日志包装 | 日志复核相关suite通过 | [04](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/04-session-log.diff) |
| 05 | BorerScreenHud | 删除失去渲染入口的类，保留宿主桥/API | 4个HUD/连线suite通过 | [05](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/05-borer-screen-hud.diff) |
| 06 | HotReloadPolicy孤岛 | 退役mtime模型；验证真实加载器拒绝损坏类及先校验再切换 | 6项通过 | [06](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/06-borer-hot-reload.diff) |
| 07 | 旧自动修改/部署链 | 删除BorerAreaThinkDeploy及仅服务它的版本号断言 | 只读建议/策略suite通过 | [07](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/07-readonly-area-think.diff) |
| 08 | PrinterPulse孤岛 | 删除旧模拟；保留真实确认pacer及打印连线覆盖 | 30项通过 | [08](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/08-printer-pulse.diff) |
| 09 | 旧翻耕路径 | 删除TILL和不可达helper；保留原耕地边界及公开计数接口 | 22项通过 | [09](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/09-planter-no-till.diff) |
| 10 | 旧坐标表单helper | 删除4个无调用私有helper，保留当前表单 | 10项通过 | [10](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/10-click-gui-helpers.diff) |
| 11 | 伐木耐久策略 | 接入真实选工具与停止；27补齐平台回收和拾取清叶 | 7项；补充后76项通过 | [11](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/11-chopper-tool-durability.diff) |
| 12 | 旧接近策略 | 退役旧盲飞模型，验证实际路线、全身碰撞和头部阻挡 | 12项通过 | [12](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/12-chopper-managed-approach.diff) |
| 13 | 伐木遇战策略 | 按实际敌意/近期攻击/启用Aura的真实目标判断傀儡 | 7项通过 | [13](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/13-chopper-observed-combat.diff) |
| 14 | 旧挖掘脉冲模型 | 退役旧模型；验证原生挖掘与服务器确认链 | 16项通过 | [14](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/14-chopper-native-mining.diff) |
| 15 | 闲置_distribution | 删除私有燃料分配遗留 | 23项通过 | [15](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/15-remove-unused-fuel-distribution.diff) |
| 16 | 闲置_potato | 删除已被泛化_seed替代的包装 | 40项通过 | [16](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/16-remove-potato-wrapper.diff) |
| 17 | 闲置loading_balance | 删除即时包装，保留等待和守恒检查 | 33项通过 | [17](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/17-remove-instant-furnace-balance.diff) |
| 18 | 重复测试收集 | 使用模块导入fixture，消除18次重复执行 | 三模块17个唯一测试通过 | [18](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/18-unique-test-collection.diff) |
| 19 | 回包fixture竞态 | 临时文件写完后原子替换reply/status | 7项；60次重复；150ms延迟2项通过 | [19](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/19-atomic-cli-replies.diff) |
| 20 | 旧JAR硬依赖 | 批次测试使用自含26.2配方；真实版本校验显式选择JAR | 37项相关；显式26.2集成通过通过 | [20](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/20-self-contained-diorite-recipes.diff) |
| 21 | 箱子测试预期漂移 | 验证waiting、阻挡证据和零接近/取料 | 32项通过 | [21](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/21-obstructed-chest-expectation.diff) |
| 22 | 固定树fixture漂移 | 补齐当前租约、任务归属和落地状态 | 77项通过 | [22](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/22-fixed-tree-fixtures.diff) |
| 23 | CI缓存 | 加入Gradle basic缓存；默认分支push可写，其余只读 | YAML与4个权限场景通过 | [23](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/23-gradle-cache.diff) |
| 24 | CI重复触发 | PR、26.1.2集成分支和tag构建；手动入口；取消同目标旧任务 | YAML与6个事件场景通过 | [24](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/24-ci-triggers.diff) |
| 25 | 补充：离线入口 | 固定离线集增加9个相关回归模块 | 新增84项；固定集1907项通过 | [25](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/25-offline-regression-entrypoints.diff) |
| 26 | 补充：真实配方版本 | 木板可选集成也改显式JAR；补贡献文档 | 默认10项/2可选跳过；26.2时10项全过通过 | [26](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/26-explicit-installed-recipe-check.diff) |
| 27 | 补充：耐久保护旁路 | 共享ChopperTools覆盖主挖、拆平台、拾取清叶；无安全替代则停止 | Chopper19个suite/76项；独立复核通过通过 | [27](/Users/sam/Code/DogeOW/minecraft-kit/2b2t-kit/docs/audits/fixes-2026-10-17/27-chopper-tool-coverage.diff) |

## 最终验收

- Java：356个suite，2,056项，0失败/错误/跳过，强制重跑测试；完整build、verifyRuntimeEngineJar、verifyOptionalMapIntegration全部通过。
- Python固定离线集：113个模块，1,907项，0失败/错误，2项显式配方集成默认跳过。
- Python全量：4,208项、4,208个唯一ID，0失败/错误；2项可选集成默认跳过。执行时阻断真实网络连接与游戏目录写入，未触发阻断事件。
- 可选配方集成：通过MINECRAFT_TEST_CLIENT_JAR明确选择26.2，两模块10项全部通过，无跳过。
- companion-skills：37项全部通过。
- 回包竞态：正常重复60例及临时文件写入延迟150ms的2例均通过；18次重复测试收集已消除。
- 主包和嵌入引擎检查：10个退役类及其内部类均不存在，ChopperTools已包含在主包。
- 27份独立补丁已在临时基线副本依次重放，44个涉及文件与最终源码逐字节一致；净差异为增加588行、删除910行，净减322行（包含新增的真实执行链测试）。

Java命令：

```sh
JAVA_HOME=/Users/sam/Code/DogeOW/minecraft-kit/jdk25/Contents/Home \
  ./gradlew test --rerun build verifyRuntimeEngineJar verifyOptionalMapIntegration --offline
```

## 需要保留的边界

未删除仍有用途的依赖、本机操作接口、Mixin或稳定runtime/api，也保留了主包内置引擎回退和热加载引擎。伐木的改动已经通过逻辑与真实调用连线测试，尚未进行实机操作验收。安装宿主包后需要完整重启，当前没有安装或热重载。

CI只增加依赖、Gradle发行包与可复用状态缓存，保留原有build与验证任务；使用官方basic缓存方式，配置依据为[Gradle官方说明](https://github.com/gradle/actions/blob/main/docs/setup-gradle.md)。触发条件和取消策略依据[GitHub工作流语法](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)，保留PR、当前集成分支26.1.2、tag和手动入口。未运行远端CI，也未声称实际节省秒数。

所有补丁以各项修改前的工作区为基线，保留此前未提交工作；运行期间另有村民模块文件更新，本次diff未纳入该独立变更。01是上轮已应用的补丁；全部源码修正现均已应用，目录中的diff供审查和恢复依据使用。
