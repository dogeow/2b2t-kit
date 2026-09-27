# 本地材料任务

`material_jobs_cli.py --automation <bridge-root> --request <request.json> --out <jobdir>`

调度不调用模型。库存、配方依赖、有限重试、暂停恢复与投影差料在本机处理；游戏操作只由注入的后端执行。原始请求固定保留，修改目标应建立新任务。

## 表层草方块

`acquire("minecraft:grass_block", count)` 接受背包内目标总数，可供投影缺料批次反复调用（例如庭院 199 格）。资源发现只提出有界的天然表层草方块区域；采集前再次检查建造区及仓库缓冲、干燥地面、周围方块和飞行状态。每次只挖一格，服务器确认原方块消失且背包 `grass_block` 净增后才允许下一格；未知回执保留在途记录，不重复挖掘。

草方块需要实际手持、剩余耐久至少 33 的精准采集钻石或下界合金铲。工具按原背包槽位选取，主包 1.9.111 的原生命令在开始与逐帧挖掘时核对手持槽位、工具、附魔和耐久。仅更新 Python worker 而未更新主包时，不能执行此采集路径。

## 后端

`material_jobs_backend.create_backend(request=..., automation=Path(...), out=Path(...), checkpoint=callback)` 返回：

- `catalog`：`ProcessingCatalog` 或兼容对象，提供 `recipes`、`candidates()`、`jar`、`smelting`。
- `observe()`：当前原生快照，含连接、世界范围、控制版本、生命、安全锁、人工接管、36格背包；可提供 `native_task_session`。投影任务还须有新核验的 `projection_audit`。`target_stack_sizes` 可来自初始请求的完整原版注册表，不只包含最终目标；不把 1／16 堆叠物品按 64 计算。
- `stock()`：当前背包数量字典。历史仓库记录、地上物品、炉内在制品不能计入。
- `fetch(targets)`、`craft(targets)`：目标背包总量。
- `acquire(item, count)`、`harden(item, count)`：目标背包总量。
- `smelt(recipe, count)`：`count` 为目标成品背包总量；配方包含 `recipe_id/source/output/ingredients/produces_per_recipe`。
- `build(projection_key)`：有界执行同一投影，完成当前批次或安全停下后返回。
- `make_room(targets, keep_items)`：仅容量不足时寄存本任务新增副产物；保护最初背包、目标和当前配方所需材料。以新库存／空槽变化确认腾出空间，同参数两次无变化会停止。
- `finish()`：停止并清理本后端持有的工作与租约，不能解除健康锁或登录服务器。
- 可选 `recover(inflight)`：核验前次中断动作及在制品。仅 `phase=done,safe_to_replan=true` 且原生无在途工作时允许重新规划。

动作回执为 `{phase: done|waiting|blocked|paused, detail: ...}`。`fetch` 没有可用现货返回 `waiting`，状态机会继续采集原料；`blocked` 表示能力／安全前置缺失，应停止。加工缺燃料等可返回 `waiting,requirements:{item:背包目标总数}`，调度器会先补前置材料。动作不得把仍在运行的原生作业包装成完成回执。

`warehouse_stock_hint` 只帮助选择可取原料的配方路线，例如骨块→骨粉→白染料，不能计入背包或判定材料已到手。金属优先按粗金属→普通熔炼的实际采集路线规划。

后端执行时至少每秒、每次原生动作前调用 `checkpoint()`；它会抛出 `JobPaused/JobCancelled/JobBlocked`，请保留异常，不吞掉或重复原生请求。回执不能代替新背包／方块核验。

## 控制与持久化

`control.json`：`{id: <job-id>, action: pause|resume|cancel, created_at: <严格递增毫秒时间戳>}`。

暂停会释放后端，在本地等待继续。`resume` 指令必须附带与初始格式相同的最新 `context`，写入 `resume-context.json`，不改最初请求；跨服务器、维度或世界会话拒绝续旧任务。重建后端收到更新后的 `context` 与 `_resume=true`，仍须严格核对新的 `expected_revision`，不能跳过控制检查。`initial_control_revision` 可记录后端取得新租约前的版本。不自动登录。

`status.json` 包含 `schema/id/state/phase/detail/done/total/updated_at/terminal/ai_calls`，原生任务号可选。取消为 `state=cancelled,terminal=true`。已暂停任务即使进程重启，也必须收到新 `resume` 指令才接管。

`inflight.json` 在动作前写入；不确定结果保留，不能自动再次投料。`receipts/` 与 `events.jsonl` 保存正常回执及状态转换。新的状态机不会因旧日志显示完成而假定当前物品已在背包。

## 批次与完成

投影默认每批 256 混凝土、128 其他方块，在凑够一批、满足该材料剩余需求或背包接近满时施工。每次施工后从新的 `replacement_items` 重算。不会为整栋建筑一次请求所有沙子、沙砾原料。

单物品也分批积累最终成品，并模拟配方中间原料占位，避免一次把整单沙子／沙砾搬进背包。最终总目标超过已知背包容量会明确阻断。后端仍须在每次动作前核验实际堆叠上限、工具、食物及周转槽位。投影完成必须完整核验 `matched == total` 且差料为空；单物品完成必须新背包数量达到请求目标。

## 加工工位

`processing.smelt(c,recipe,target_count,profile,out,checkpoint)` 与 `processing.harden(c,item,target_count,profile,out,checkpoint)` 使用已存在的客户端，不创建新控制者。每次动作 `out` 独立；恢复旧动作才显式传原目录。

`profile` 字段：

- `recipe_jar`：当前客户端 JAR；普通熔炼配方必须在其中可验证，当前支持标准 1:1 输出。
- `furnace_positions`：允许使用的普通熔炉坐标列表；每轮先核验空炉。可选 `furnace_bank_journal` 需属于同一世界会话。
- `concrete_station`：`support`、`expected_state`，可选 `waypoint`、`staging`、`stand_block`、`batch_size`（1–16）。
- 若工位带屋顶，`concrete_station.shelter_ledger` 指向已核验围护账本，且 `stand_block` 必须对应其干燥站位。

完整装炉的批次可继续收取；部分／未知投料不会再次发送。固化每步记录粉末和成品守恒，未知批次需要独立核验。煤或粉末不足返回材料前置需求。

`processing.recover(c, operation, args, profile, original_out, checkpoint)` 只使用原动作目录恢复：熔炼要求各炉均已完整装料或已收取；固化需要粉末实际消耗与成品净增、工作格残余／新掉落物可对账。先核销旧在制物，才处理未花费的粉末；零消耗且操作未知时不重复放置。成功后再次检查目标背包总数，返回 `safe_to_replan=true`；后端明确拒绝恢复时，调度器不会仅凭当前恰好有足量成品覆盖该拒绝。

围护工位正常结束会先退出。暂停、人工接管或异常时不在 `finally` 走位；`c.material_job_shelter` 与加工账本保存 entering／inside／exiting／outside 状态，`material_job_shelter_ledger` 提供原始布局。后端仅在原控制范围仍安全时收尾退出，再计算高空停靠，不能先尝试穿屋顶上升。

离线回归：`python -m unittest test_material_jobs -q`。测试使用内存库存和炉子，不创建真实游戏客户端。
