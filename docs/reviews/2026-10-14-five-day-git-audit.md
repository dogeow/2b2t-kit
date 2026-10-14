# 2b2t-kit 近 5 天 Git 提交审计报告

**审计日期：** 2026-10-14
**仓库路径：** `2b2t-kit/`（嵌套于 `minecraft-kit`）
**对比基线：** `0001214`（2026-10-09 之前最后一次提交） → `2792002`（原报告冻结快照）
**审计范围：** `0001214..2792002` 的已提交历史；未提交工作区不属于该统计。2026-10-14 复核时 HEAD 已为 `394949ae`。

---

## 1. 执行摘要

近 5 个自然日内共有 **210 次提交**，净增约 **+18,475 / -499** 行，触及 **380** 个文件。工作集中在 **平面地图投影建造（flat projection）**、**泥砖/小麦/采石/染料批量工艺链**、**材料任务控制面可靠性**（心跳、取消、容量重试）以及 **客户端战斗与巡航 UX**。

整体质量信号偏正面：

- 该范围新增 **134 份** `docs/changes/` 变更说明；数量不足以证明与 210 次提交一一对应，实机证据路径在文档中可追溯。
- `decision-runtime` 侧测试增量巨大（`test_projection_flat_jobs.py`、`test_material_jobs_backend.py`、`test_mud_pipeline.py` 等）。
- 工作区留存的一次预提交校验记录：**653** 项 Python 测试、**0** 失败（`work/upgrade-26.2-642/precommit-validation/python-result.json`）。

主要风险不在「明显未测的单点」，而在 **核心后端文件体积与变更频率**（`material_jobs_backend.py` 已超 2200 行、5 天内修改 43 次），以及 **对外部 Mod（Xaero）Mixin 的软依赖**。下文分性能、效率、缺陷与残余风险展开。

---

## 2. 提交统计

| 指标 | 数值 |
|------|------|
| 提交总数 | 210 |
| 按日分布 | 2026-10-09: 17；10-10: 86；10-11: 82；10-12: 25；10-13~14: 0 |
| 约定式前缀（标题） | `fix:` 56；`perf:` 7；`feat:` 9；`docs:` 24 |
| 新增变更文档 | 134 篇（`docs/changes/*.md`） |
| 热点文件（行变更量） | `projection_flat_backend.py`、`test_projection_flat_jobs.py`、`material_jobs_backend.py` |

**说明：** 上表只描述冻结快照。加入 `394949ae` 后，`0001214..394949ae` 为 211 次提交、587 个文件、+29,361 / -1,019 行，新增变更文档 158 篇；10-14 已有新提交。

---

## 3. 功能域与变更主题

### 3.1 平面地图投影（Flat projection）

- 新/扩展适配层：`projection_flat_backend.py`、`projection_flat_plan.py`、`projection_flat_cache.FlatMaterialLedger`。
- **性能向：** 复用 flat map 材料账本、合并相邻地图窗口、保留停靠账本、注册航线直飞（`perf:` 系列提交）。
- **正确性向：** 加载中心位姿读全图、手动交接后二次等待、从健康停靠恢复授权目标、空气种子准入拒绝与精确 tail  reconcile（`fix:` / 专题提交）。
- **风险点：** 单文件逻辑与测试体量同步膨胀（backend + tests 合计约 1500+ 行级变更），状态机分支多，依赖 `control_revision` / 租约 / 场景三方一致。

### 3.2 泥砖（Mud）与粗土工艺链

- 模块：`material_jobs/mud_pipeline.py` 及 `test_mud_pipeline.py`（高频修改）。
- **性能：** 跨输出堆叠边界保留输入批次、水瓶堆叠批量准备、16 格容量证明的一次备货访问。
- **缺陷修复：** 登记泥土盈余暂存、粗土饲料、工作区槽位缓存、远程块校验前加载 owned station 等。
- **观察：** 泥链是 10-10~10-11 提交风暴中心，回归测试覆盖度高，但实机边界（陷阱门、开放工作区、容量观察不完整）仍靠 `JobBlocked` 分支兜底。

### 3.3 小麦 / 砾石 / 采石 / 远程地图资源

- 登记小麦：`registered_wheat.py`、`wheat_reconnect_repair.py`、`native_wheat.py` 等；修复重种确认、田块边界、拾取与恢复证据。
- 砾石：导航宿主契约、补给区搜索、部分增益保留为批次（连续 `fix:`）。
- 采石：开放入口保留、矩形矿脉选块、副产物入库、有界工作量、登记竖井复用与空气回程证明。
- 远程地图：高巡航回程、未知 targeted receipt 立即停止、有用整堆才远程返回。

### 3.4 批量合成与仓库 CLI

- `stack_recipe.py`、`kit_runtime/inventory.py`：精确颜色/石材/木板等 **verified batch**；小额外拾取后保持分组合成效率。
- `kit_cli.py` + Java `KitCommands` / `ProjectionSupplyRegistry`：显式 depot 命令与供料协议。
- **效率收益：** 减少往返工作台与重复开格；**代价：** 配方分组与库存快照必须在同一 revision 下验证，否则错误会放大为整批浪费（测试中有针对）。

### 3.5 材料任务控制面与原生客户端

| 主题 | 代表提交 / 文件 | 性质 |
|------|------------------|------|
| 观察期心跳续约 | `15bc9c5`，`material_jobs_backend.observe()` | **Bug 修复**（熔炉等待误判 10s 失联） |
| 仓库容量重试 | 同上 | **Bug 修复**（容量不足误记为缺货） |
| 取消时保留已发布原生动作 | `6863482`，`material_client.request()` `finally` | **并发/取消正确性** |
| 熔炉轮询调度 | `8beddc4`，`processing.py` | **效率**（按配方时长观察，减少无效 poll） |
| 引擎热加载 | `cd098ff`，`runtime_update.py` | **可靠性**（owned task 内加载 staged engine） |
| 待处理取消排水 | `test_material_pending_cancellation.py` | 回归覆盖 publish 失败 vs 已发布取消 |

### 3.6 客户端：战斗、巡航、进度 UI

- **Shield + 弓：** `0b5bda5` — 充能感知瞄准与盾反窗口（`BorerRangedCombat`、`GuardShieldCycle`）。
- **战斗让渡进食：** `d5577b3` — `GuardFoodLease`、`BorerMealPolicy`；与材料任务并行时的争用缓解。
- **Xaero 地图巡航：** `XaeroMapCruiseMenuMixin`（`@Pseudo`，`require=0`）— 可选右键菜单项。
- **材料 UI：** `build_progress_overlay.py`、缺口展示、采集阶段暴露、避免重复短停（`a38071f` 等）。

---

## 4. 性能（Performance）分析

### 4.1 已落地的优化（有明确 `perf:` 或文档背书）

1. **Flat map 账本复用**（`b453f6b`、`fe43e78`、`30d6497`）
   减少跨窗口重复审计与供料计算；依赖 `FlatMaterialLedger` 与 verified window 边界。

2. **泥砖备货访问合并**（`2fa0f41`、`155ded3`、`05fdbc7`、`71e8e9d`）
   16 格证明的一次 visit、输入批次跨输出堆叠、水瓶堆叠 — 直接降低背包整理与往返次数。

3. **熔炉观察调度**（`8beddc4`）
   按已知配方时长安排下一次观察，降低无意义 `observe()` 频率（仍保持安全上限）。

4. **资源发现加速**（`57e30fd` 等）
   `rock_observation_index`、`near_resource_frontier`、verified resource selection — 缩短选材路径。

5. **合成批处理**（`5798dd5`、`aa6a07c`、`462a050`、`7f7ff6a` 等）
   工作台与背包格内 exact batch，减少单格合成循环。

### 4.2 性能相关的设计权衡

- **控制循环轮询：** `material_client.request()` 主循环 `time.sleep(.15)`；`Backend.launch_snapshot()` `0.05`；材料 `checkpoint` 路径常见 `0.1~0.25s`。这是 **延迟 vs CPU/磁盘读** 的显式权衡，对长任务可接受，对极短操作可能略增尾延迟。
- **`material_jobs_backend.py` 体积：** 单进程内大量 BFS/审计/旅行编排，**无明显 N² 全图扫描新增**，但文件过大导致 JIT 式阅读成本高，间接影响后续优化速度。
- **Java 战斗 tick：** `BorerRangedCombat` 在 40 格范围内枚举实体；属既有模式，5 天内仅为盾弓逻辑增量，未见扩大搜索半径的提交。

### 4.3 性能测试与验证缺口

- 文档中多次引用 **实机连续秒级** 与 **work/live-*** 目录证据；自动化侧以 **逻辑/模拟测试** 为主，**缺少持续性的端到端耗时基准**（例如「单窗口 mud 任务 P50 步数」趋势）。
- 原报告环境未成功运行 Gradle；2026-10-14 使用项目 JDK 25 和已有缓存复核，`test jar verifyRuntimeEngineJar --offline` 成功，1978 项 Java 测试无失败。该结果不是游戏实机验收。

---

## 5. 效率（Efficiency / 工程效率）分析

### 5.1 运行时效率（任务完成路径）

- **跳过无效工作：** 不合格岩石修复扫描跳过（`a52a7a5`）、开放沙坑入口规划、reserve-only 建造行程避免（`7b54c33`）等 — 减少无效移动与扫描。
- **登记资产复用：** 工作台出口、采石竖井、室内 depot 位姿、混凝土站预加载 — 降低「每次重新探测世界」成本。
- **地图修复：** 离开站点前捡起修复掉落（`4dcc6de`）— 降低材料损耗与二次补料。

### 5.2 研发与运维效率

- **变更文档密度高：** 134 篇新 `docs/changes/`，利于事后审计与实机对照；与 AGENTS.md「不把流水堆在 AGENTS」一致。
- **测试共置：** 几乎每个行为变更带有 `test_*.py` 或 Java `*Test.java` 增量 — 降低回归成本。
- **隐忧：** `material_jobs_backend.py` 与 `projection_flat_backend.py` 继续 monolith 化；5 天内 backend 43 次 touch，**合并冲突与「改 A 破 B」概率上升**。中长期可考虑按域拆分模块（mud / flat / quarry / travel）而非继续堆叠单文件。

---

## 6. Bug 与可靠性检查

### 6.1 已修复的高影响缺陷（按业务影响排序）

| 严重度 | 问题 | 修复要点 |
|--------|------|----------|
| 高 | 熔炉/等待期间心跳超时导致「控制器失联」 | `observe()` 在 owned 状态下 `heartbeat.touch()` |
| 高 | 取消原生请求时丢失已发布 revision，finish 误判 handoff | `native_inflight` 在 `finally` 中条件保留 |
| 高 | 仓库取料容量不足被记为永久缺货 | 有界整理后仅重试容量阻碍项 |
| 中 | 小麦重种确认、登记田块、边缘拾取 | `registered_wheat` / `f5edb37` 等 |
| 中 | 砾石导航契约与干路导航 | 连续 4 个 `fix:`（10-11 凌晨） |
| 中 | 深采副产物未入库即继续挖掘 | `c9be8c6` |
| 中 | 采石入口在矩形矿脉选择时丢失 | `0c27151` |
| 中 | 盾反窗口与弓充能不匹配 | `0b5bda5` |
| 中 | 材料观察心跳与容量（与上表第一项同源文档） | `docs/changes/2026-10-11-material-observation-renewal.md` |

### 6.2 代码审查中关注的正确性模式（未见明显反模式）

- **Revision / 租约：** `material_client` 对 `control_revision`、`supervision_lease`、`native_inflight` 约束严格；取消与超时路径有注释说明历史事故。
- **「不重复播放」原生操作：** 超时抛 `RuntimeError` 而非盲目 replay；与 `terminal_confirmation.verified` 配合。
- **投影加载：** 未加载审计不计为空投影（`PROJECTION_LOADING_RADIUS` 旅行）— 避免假阴性完工。

### 6.3 仍值得关注的残余风险（非必现 Bug）

1. **`material_jobs_backend.py` 复杂度**
   多嵌套 `while True` + `time.sleep` 与 `busy`/`checking` 标志；逻辑正确性主要靠测试与实机，**静态理解成本高**。

2. **Xaero Mixin 软接入**
   `XaeroMapCruiseMenuMixin` 使用 `@Pseudo` 与 `require=0`：Xaero 未安装或 API 变更时 **静默无菜单**，不会崩溃，但功能消失不易被用户察觉。

3. **双端一致性**
   若干特性跨 Python `decision-runtime` 与 Java `AutomationBridge` / `MaterialTaskChannel`（depot、供料协议）；版本/deploy 不同步时易出现「CLI 有、游戏无」— `gradle.properties` 在 5 天内多次 bump，需与已安装 jar 哈希对照（文档中已有 manifest 习惯）。

4. **测试环境分裂**
   - 预提交子集：653 passed（记录于 work 目录）。
   - 本机 `python3 -m unittest discover`：1801 测试中 **346 errors**（`httpx` 等依赖缺失导致的 import 失败，非被测逻辑失败）。
   新贡献者若未使用项目既定 Python 环境，可能误判「全绿/全红」。

5. **源码与实机版本核对**
   `394949ae` 已补上 10-14 提交；若游戏仍使用局部热更新或未提交 work 脚本，**Git 历史不能代表线上行为** — 需以游戏目录 jar 与 `work/` 快照为准。

---

## 7. 测试与验证摘要

| 来源 | 结果 | 备注 |
|------|------|------|
| `work/upgrade-26.2-642/precommit-validation/python-result.json` | 653 tests, 0 failures, ~11.5s | 模块 42 |
| 本审计 `unittest discover`（系统 Python 3.14） | 346 import errors | 缺 `httpx` 等；不宜作为发布门禁 |
| 项目 JDK 25：`test jar verifyRuntimeEngineJar --offline` | 复核成功，1978 Java 测试无失败 | 主包元数据修正后重新构建 |
| 变更文档中的实机项 | 多处引用 `work/live-20261004/` 等 | 心跳、熔炉收取、泥/麦/采石等 |

**建议门禁（与 AGENTS.md 一致）：**
`JAVA_HOME=.../jdk25/Contents/Home ./gradlew test jar verifyRuntimeEngineJar --offline` + 项目绑定的 Python 依赖环境跑 decision-runtime 全量测试。

---

## 8. 结论与建议

### 8.1 结论

近 5 天提交以 **地图投影长任务** 和 **材料供应链硬化** 为主线，**性能优化有清晰叙事**（账本复用、批量合成、泥链 visit 合并、熔炉调度），**缺陷修复集中在控制面与游戏状态一致性**（心跳、取消、容量、导航契约、采石/小麦/战斗）。测试与变更文档跟得比较紧，本报告的静态叙述不足以单独确定整体可合并风险等级，主要系统性风险来自 **核心后端单文件膨胀** 与 **Mod 可选集成静默失败**。

### 8.2 建议（不要求改代码，仅供后续排期）

1. **架构：** 拆分 `material_jobs_backend.py` 的旅行/审计/采集子域，降低 40+ 次/周的 touch 冲突率。
2. **基准：** 为 flat mud 窗口任务记录固定 scenario 的步数与 wall time（JSON trend），补自动化性能回归。
3. **环境：** 仓库已有 `decision-runtime/requirements.txt`（`httpx==0.28.1`）与 README 中的托管 venv 入口；沿用既定环境执行全量测试，避免系统 Python 的 import 噪声。
4. **集成：** Xaero 巡航项在缺失时打一次 debug 日志或配置提示，避免「功能消失无感」。
5. **发布：** 当前源码基线为 `394949ae` 加本次修复；分别核对主包、引擎和 worker 的实际哈希，保留安装与实机证据。不能要求 26.2 新主包与旧快照 `2792002` 一致。

---

## 9. 附录：HEAD 与 `perf:` 提交列表

**原报告冻结快照：** `2792002` — *Load registered sand sites before acquisition scans*（2026-10-12）

**`perf:` 提交（7）：**

- `05fdbc7` — keep mud input batches across output stack boundaries
- `71e8e9d` — retain mud bulk preparation with stacked water bottles
- `30d6497` — retain parked map ledger and fly registered routes directly
- `fe43e78` — combine nearby map windows and keep healthy preflights online
- `b453f6b` — reuse flat map material ledger across verified windows
- `155ded3` — prepare one capacity-proved 16-cell mud stock visit
- `2fa0f41` — make sixteen-cell mud stock visits for full projection jobs

---

*本报告由静态 Git 历史、关键源码阅读与工作区校验记录生成，未修改任何产品代码。*

## 2026-10-14 复核补充

两份报告的准确反馈已修复，错误统计和测试分类已校正。托管 Python 全量 3728 项、Java 1978 项、伴侣技能 37 项全部通过，没有跳过测试；材料后台已热更新并逐文件核验，游戏未重启。运行主包未为描述文案修正替换。完整处理依据见 [复核与修复记录](../changes/2026-10-14-git-audit-verification-and-fixes.md)。

地图画当前独立审计为 **15011 / 16512**，剩余 1501 格，最终地图像素验收尚未完成。
