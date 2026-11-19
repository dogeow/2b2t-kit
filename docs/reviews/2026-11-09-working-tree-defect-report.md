# 工作区缺陷报表：性能、Bug、逻辑

**日期：** 2026-11-09  
**范围：** `2b2t-kit/` 当前工作区（含未提交改动与未跟踪源码）  
**基线 HEAD：** `fef3f4708b496ef75491986b4d27bfa9e4febdbc`（*Recover safely from missing footholds*）  
**工作区版本号：** `gradle.properties` 为 Mod `2026.11.06.1`、引擎 `1.8.62`（相对 HEAD 已改，尚未提交）  
**方法：** 阅读相对 HEAD 的 diff、未跟踪的农场/剪叶/掉落追踪实现，以及它们的调用点。未改产品代码，未跑 Gradle 或 Python 测试。

结论按当前源码行为写。带测试的行为变更如果测试与实现一致，记在文末，不单列为缺陷。

---

## 1. 摘要

| 级别 | 数量 | 含义 |
|------|------|------|
| P1 | 6 | 会停挖、走错液体、施工溺水、主线程卡顿，或农场租约判据过宽 |
| P2 | 6 | 单次批次漏剪、热路径分配/扫描、缓存与全文件哈希 |
| 已核对 | — | 连接观察、潜行钓鱼收尾、可堆叠需求大于 1 的潜影盒取出，与现有测试或注释一致 |

---

## 2. P1

### 2.1 方块「重现」按选中次数计数，一次挖掉后第三次再选中就会禁挖

`DefaultTunnelBorerEngine.setMiningTarget`（约 3558–3569 行）在服务器确认挖掉后的 200 tick（10 秒）内，每次重新选中同一格就 `reappearedTargets` 加一。计数达到 3 时抑制 600 tick。

计数发生在 `currentTarget` 发生变化时，不要求中间又被服务器确认挖掉一次。战斗暂停、拾取、改规划都会 `clearMiningTarget`，规划器再选同一格即加一。注释写的是「第三次挖掉又出现」。一次确认挖掉之后，10 秒内第三次把该格设为目标就会跳过它。矿脉边缘和岩浆块出口都走这个入口。

### 2.2 小漏已经在挖掘距离内就不再走近；非区域模式三次失败或 4 秒走不到就整机停止

`BorerLiquidPolicy.shouldWalkToLeak` 现在只看 `leak && !inReach`，`distSqr` 不再参与。`APPROACH_DIST_SQR`（2.25）因此不再让「够得着但还偏远」的漏点继续靠近。

`BorerLiquids.handle`（约 106–141 行）在此之上还有两条停机路径：

- 接近同一漏点达到 80 tick（4 秒）调用 `engine.stop`。
- `giveUpAfterFails`（连续 3 次）对区域模式仍是放弃该点；向前、向下、找矿改为 `engine.stop`。

够得着却封不上的漏，以前会再走近。现在会在当前距离上连试三次，然后停止整个盾构，而不是跳过该矿或只放弃这一格。

### 2.3 找岩浆块时，绕路把「脚下是岩浆块、下面是岩浆」当成干路

`ignoreLiquidUnderFloor` 在找矿勾选岩浆块且目标不比起点更低时返回真。`BorerLiquids.inStandColumn`（约 529–532 行）在这个标志下只检查立足格本身是不是流体，不再调用 `atOrOpenedBy`。

岩浆块本身不是岩浆流体，所以块下的岩浆湖不会让这条绕路被拒绝。同一套引擎里，`safeMagmaFloor` 会因 `pos.below()` 有岩浆而拒绝站立，`unsafeToWalk` 也会在不能蹲走时禁止前进。绕路选点和实际落脚条件不一致：常见结果是对着这条「干路」停步；若后续移动直接采用 `pickDryDetour` 的落点，则会走向岩浆块下方的岩浆。

### 2.4 向上爬升只要 2.5 秒没在着地时升高一格，就取消爬升

`BorerVertical.ascentStalled`（约 23–33 行）只在 `onGround()` 且所在方块 Y 大于上次记录时重置计时。空中升高不算进度。连续调用满 50 tick 后，`DefaultTunnelBorerEngine`（约 1874–1887 行）松开前进和跳跃，改挖头顶或 `skipActive`，跳过失败时 `stop`。

Meteor Scaffold 抬升经常在离地状态下连续上升。这条计时会在约 2.5 秒后把仍在上升的路线判成「台阶无法安全通过」。另外，中间只要有一 tick 没调用（`tick - ascentLastTick != 1`），计时器被清零，卡住时又可能一直不触发。

### 2.5 投影施工主循环不再处理溺水

`goal_workflow.build_phase` 去掉了循环内外对 `interrupt_submerged` 的调用。该函数仍在 `material_jobs/construction_breathing.py`，并仍被 `material_jobs_backend.hold_failed_finish` 使用：水下时暂停施工并要求重新核验干燥站位。

`build_phase` 本身在最长 180 秒的循环里不读 `under_water`。血量条件只出现在停滞改站（`health >= 18`）。走 `goal_workflow` 的投影施工可以在水下继续放置，直到别的停机条件成立。

### 2.6 农场辅助挂在每 tick 的世界观察上，意图文件存在时主线程读盘并扫实体

`KitClient` 每个客户端 tick 调用 `tunnelBorer.observeWorld`。`DefaultTunnelBorerEngine.observeWorld`（约 1007–1008 行）无条件调用 `LocalFarmMelee.tick` 和 `MeteorFarmAssist.tick`。

`MeteorFarmAssist` 在服务器为 `simpcraft.com` 且 `meteor-farm-intent.json` 存在时，每个 tick：

- 读取并解析意图、`status.json`，有时再读 `request.json`；
- 用 12 格膨胀盒查询弹射物；
- 引怪阶段遍历 `entitiesForRendering()`。

状态文件写出有 500ms 节流，读和扫描没有。过期意图文件也会先完成解析和弹射物查询，再在作用域检查里关闭。

同文件还有两处判据问题：

- `sameRevision` 接受原生请求里的 `expected_revision` 或再加 1。控制修订因为别的动作加一后，农场意图仍然算同一份。
- 首次武装时先 `prepareMeleeTarget`，紧接着因为 `owner` 仍为空执行 `close(c, true)`，释放刚拿到的近战租约，再申请一次。`close` 的异常路径会把 `local-farm` 以外的这次失败写成拒绝；`LocalFarmMelee.tick` 的 `catch` 只 `close`，不改写 `local-farm-melee-state.json`，磁盘上可以继续留着 `active: true`。

`LocalFarmMelee` 本身有 100ms 节流，且只在 `127.0.0.1:25579` 上做全实体扫描。它的主线程成本低于 `MeteorFarmAssist`，失效状态文件是另一回事。

---

## 3. P2

### 3.1 剪叶批次里，任何一次未剪成就永久跳过该格

`LeafShearBatch.sendNext`（约 87–88 行）先 `index++`，再检查区块是否加载、是不是自然树叶、确认是否仍挂起、距离、射线和耐久。任一失败都 `return`，这一轮 32 格里不会再回到该坐标。

Python 侧 `leaf_harvest.harvest_batch` 把 `remaining` 放回候选，且 `native_retries < 2` 才再试一次，第二次进入 `skipped`。区块晚一 tick 加载、或确认对象还挂着，就会吃掉唯一的重试。

### 3.2 每次放置都走栈采样并写文件日志

`BorerPlace.rememberPlacedSupport` 在记入保护格之后调用 `StackWalker`，取调用栈上 3 帧方法名，再 `fileLog`。放置发生在客户端 tick 里。封堵和垫脚越密，主线程上的分配和磁盘写入越多。

### 3.3 猪人状态每秒用 64 格膨胀盒扫实体

`PiglinBrawler.nearbyPiglinStatus` 在冷却归零时（约每 20 tick）对 `getBoundingBox().inflate(64)` 做 `getEntities`，再在 Java 里过滤猪人。这只更新 HUD 文案，不攻击。人多或实体多的服务器上，这个查询和战斗扫描叠在同一 tick。

### 3.4 建造进度缓存只在「最近 2 秒」内对内容做摘要

`BuildMaterialProgress.read` 用 `(mtime, size, blake2b)`。文件修改时间距现在超过 2 秒且 mtime、size 未变时直接返回缓存，不再读内容。2 秒内每次 `read` 都重新读字节并哈希。展示轮询若打在刚写完的账本上，会重复哈希；若写入保持相同长度且时间戳不再变化，2 秒后会显示旧 JSON。

### 3.5 商人重连证明每次校验都读完整份 `events.jsonl`

`merchant_preflight_abort.selection_closed_after_reconnect` 为了核对 `events_sha256`，把 `control/events.jsonl` 整文件读入并逐行 `json.loads`。哈希不一致时返回假，不会误放行。事件文件变长之后，每次结算预检的 CPU 和分配随历史增长。

### 3.6 材料任务启动时，打开的箱子要先稳定 30 秒才关闭

`MaterialClient._init_material` 在 `ContainerScreen` / `ShulkerBoxScreen` 且不是恢复模式时调用 `close_stable_storage`。该函数以 0.25 秒间隔观察最多 30 秒，签名用 `json.dumps` 序列化整个菜单。界面在这 30 秒内一直不变才会发一次 `close_menu`。这是故意的防误关，代价是每次带着箱子界面启动材料任务都会堵住调用线程约 30 秒。

---

## 4. 核对后与测试或注释一致的改动

| 位置 | 行为 |
|------|------|
| `game_connection_cli.pending_screen` | 见过连接画面之后回到标题或断开界面仍继续观察到调用方截止时间，不另发连接。`seen_connecting` 已不参与判定。`test_game_connection_cli.py` 要求断开一直等到超时且只发送一次请求。 |
| `idle_service.tick` → `checkpoint` | 原生 `idle_activity.busy` 或任务会话尚未对齐时，最多等 2.5 秒再读下一帧。`test_idle_service.py` 覆盖约 1 秒一帧的快照。真正持续忙碌仍会走 `busy_reason` 并结束任务。 |
| `packed_supplies.take_box` | 去掉 `need==1`。不可堆叠且数量为 1 的装备在需求大于 1 时仍走单件 `quick_move`，外层循环按剩余需求继续。 |
| `ParkingLeasePolicy.stayOnline` | 仅在同一租约、守卫收尾、无手动、血量不低、PvE 守卫已武装、无威胁、身体安全、脚下稳固、近似静止、无界面、饥饿度 ≥ 18 时改为留在在线守卫，不走登出。 |
| 手动开挖与紧急离线锁 | `TunnelBorer.start` 在 `EmergencyExit.held` 时直接返回。界面再读 `manualStartBlock` 显示原因。脚本用的 `startMaterialArea` 不经过这道检查。 |
| 岩浆块蹲走与出口连挖 | `keepMagmaExitDig` 避免每 tick `releaseMine` 把挖掘进度清零。`safeMagmaFloor` 在脚下或四周有岩浆流体时不把岩浆块当落脚点。 |

---

## 5. 本次没有做的验证

- 未执行 `./gradlew test`，也未跑 `decision-runtime` 的离线或全量 Python。
- 未对照 `/Applications/.minecraft/versions/26.2` 里已安装的 Mod 与引擎哈希。工作区版本号已是 `2026.11.06.1` / `1.8.62`，安装目录可能仍是更旧的包。
- 未做实机：岩浆块绕路、Scaffold 上升 50 tick、投影溺水、`simpcraft.com` 上农场意图文件留在磁盘时的帧时间。

---

## 6. 建议的复核顺序

1. 找矿模式在「岩浆块 + 下方岩浆」和「小漏水刚好在挖掘距离边缘」各走一条，确认是停步、跳过还是 `engine.stop`。
2. 打开 Meteor Scaffold 后让找矿向上爬超过 3 秒，看是否被判成台阶无法通过。
3. 用 `goal_workflow.build_phase` 在 `under_water` 为真时跑一小段，确认施工是否仍被暂停。
4. 在 `config/twob2tkit/automation/meteor-farm-intent.json` 存在时抓一次客户端 tick 耗时，区分无文件、过期文件、有效文件三档。
5. 剪叶 burst 在目标区块尚未 `FULL` 时打一次，看该格是进入 `remaining` 后重试成功，还是第二次被 `skipped`。

## 7. 复核与修正

| 条目 | 当前工作区的结论 |
|---|---|
| 2.1 | 属实。每个确认清除只允许计入一次真实重现。反复选中不会增加次数，连续发生三次清除后重现才触发抑制。 |
| 2.2 | 属实。封堵失败且距离偏远时，先验证身体经过的空间能否安全靠近；找矿模式在用尽尝试后可换矿点。无目标可换的挖掘模式仍安全停机。 |
| 2.3 | 属实。绕路候选用与走位一致的岩浆块落脚检查，拒绝下方或周边有岩浆的站位。报告推测的走入岩浆结果尚无实机复现。 |
| 2.4 | 属实。计时按可靠的实际高度进展更新。短暂离开爬升分支不再清空计时，普通原地跳跃也不会持续刷新计时。 |
| 2.5 | 属实。恢复施工前和施工中的水下中断，并覆盖换料、重新站位及收尾路径。复用现有控制权和呼吸保护。 |
| 2.6 | 属实。生产农场在后台有界轮询意图和状态，过期或作用域不符时不扫实体。弹射物仍在客户端按有效作用域即时检查，引怪查询限于附近猪人。只接受意图的准确修订号，移除读取旧请求推断所有权的分支；同一准入只申请一次近战租约。本地试验异常时发布已停止状态。 |
| 3.1 | 部分属实。未发出的叶子遇到区块未载入或确认挂起，批次末尾会有一次有限重查。已经发出的请求及未决确认仍按原回执规则处理。原报告所说的永久跳过只可能发生在 Python 当前工作轮的重试耗尽之后。 |
| 3.2 | 属实。移除每次放置的栈采样。方块坐标与类型的诊断日志仍会写入，尚未量化磁盘开销。 |
| 3.3 | 属实。HUD 继续每秒更新，按猪人类型查询并用平方距离比较。未实测帧时间收益。 |
| 3.4 | 属实。使用设备、inode、mtime、ctime 与长度识别文件。常规原子替换以及保留 mtime 的重写可使缓存失效，元数据不变时不重复读取或计算摘要。 |
| 3.5 | 属实。逐行读取和计算整份原始文件的哈希，只保留必要的四条尾部证据。有效证明的读取成本仍与日志长度有关。 |
| 3.6 | 30 秒观察窗口是有意的防误关条件，输入变化会提前拒绝。保留窗口并去掉每帧的菜单 JSON 重编码。 |

初稿第 4 节的行为维持原有契约。本次验证基于现有工作区，包含已有未提交改动。未安装到 Minecraft，未做服务器上的事故复现或帧时间采样。

本轮最终验证通过 Java **2675 项**与 Python **6061 项**，其中 Python 全量耗时 196.629 秒。主包构建和运行时引擎 JAR 校验通过，`git diff --check` 无问题。
