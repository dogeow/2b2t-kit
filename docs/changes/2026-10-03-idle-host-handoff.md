# Host 闲置状态与精确抢占

`status/snapshot` 新增 `idle_activity_protocol=1` 和 `idle_activity={busy,conflicts,idle_task_session}`。快照只读实际控制器状态；不会为了查询而停任务、写 owner、关闭菜单或解安全锁。

汇总 Kit 巡航、排队离线、盾构、围箱、喂养、种田、挖树、钓鱼、上基岩顶、猪灵战斗/借用视角、独立防护视角、普通/投影建造、混凝土、结构导航、选区拾取、开箱自动补货、材料/农场后台。Bridge 同时汇总 active、NativeMaterialSession、材料 lease、扫描、桶、地图、耕种/制作、补料、空气航点、Scaffold、投影 mask、ProfessionalPrinter 和防护接管。单项未活动不等于整个 Kit 空闲。

只有 `idle-service-owner.json` schema=1、20位服务 id、实际存活 PID、正确 worker.lock 路径、-1000..2500ms 新鲜心跳，以及 world/task/lease/revision 精确匹配当前 materials lease 时，才能排除本 idle。钓鱼、导航及其它 native primitive 还必须来自相同 service/task/world 标签；钓鱼还核对真实 start generation，外来重新启动同一 fisher 不继承旧 idle 标签。Java 不将 FileChannel 锁当作 Python flock 的证据。

真实 WASD 在输入处理和状态发布前抢占本 idle。正式 Kit 开始入口、材料/农场开始和恢复、原生写操作也接入显式抢占；材料 context 与农场 probe 保持只读。保留既有 `userTaskStarting`、`dispatch`、`stopWork` 原调用链。

抢占复用 scoped `stopWork`：只清理精确本任务的 native input、钓鱼、导航等持有者，确认这些真实控制器已停止，再释放对应 lease。保留 PvE guard、物品、未知回执，不触发离线或解锁。已排队的本 idle 导航离线会取消。菜单通过 `AutoFisher.stopKeepingMenu` 和补料 `closeKeepingMenu` 原样保留，非空 cursor 不作伪完成，也不主动关闭外来菜单；物理右键、非鱼竿的 guard use 不被当作 idle 竿输入释放。手动持键期间不会恢复旧 idle/guard 借用视角，防护仍保留 armed 状态。

Host 不改 Python owner 文件，而在 `idle_activity.yield_ack` 附 service/task/lease/world、revision_before/after、input_released、reason 和时间。该确认只证明输入与 lease 已释放，不证明库存/方块未知动作已完成。带 idle 标签的 release cleanup 要求 `material_job_pause release=true`，不走普通暂停的全模块停止路径。

新增财物能力 `idle_fishing_protocol=1`、真实 clamp 2..8 的 `fisher_chest_range` 和 `fisher_deposit_allowed`。inactive 为 false；精确 fresh idle 标签才调用 `startIdleNoDeposit`，用临时控制器状态禁止查箱/导航/存箱，满包在原生 tick 里立即停止，不等待 Python 空槽轮询，不修改用户 config。站位变化也停止，idle 不使用旧坐标拉回。普通 active fisher 保留原来存箱许可；stop 清掉临时状态。外部 Meteor AutoFish 独立使用竿，列为冲突而不静默接管它。

详细扫描实体行补 `hostile` 与真实 `getBoundingBox` 的 `bounds.min/max` 三维数组。范围仍是当次已加载实体 AABB；这些字段用于区分玩家身体/投竿线阻挡与远处无害实体，不猜物种尺寸，不扩大服务操作授权。

边界：存在外来 active/native owner/scan 或无法归属的原生清理时拒绝抢占；不泛化停其它后台。保留的物品菜单/cursor 会继续阻止正式开工。外部原生请求若仍带抢占前的 expected_revision，会严格拒绝正式动作，调用者须刷新 scope；不会静默改请求。任意插件直接调用组件内部 start、绕过 Kit/Bridge 入口的行为不承诺抢占接线，但其真实活动仍计入 conflicts。

新纯策略与 ASM 接线测试覆盖 owner 时效/存活/路径/身份、外来任务、实际控制器释放、完整聚合、读操作不抢占、正式/手动入口、菜单保持。使用捆绑 Java25，完整离线 `test jar verifyRuntimeEngineJar` 已通过；Host 需完整客户端更新后实机验证。此轮未部署、操作游戏、改版本或提交 Git。
