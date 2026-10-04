# 根据完整实际审计定向补光

首轮实际审计已完整读取全部 150 个登记分区，只有 23 区观察到未保护暗点。再次逐一访问所有矩形会让补光阶段继续跑到首轮没有暗点的海边，例如 region_index 27。`--work-baseline` 用保留的完整真实审计选择所有 `unprotected_dark_floor > 0` 分区；它不依据预测能否覆盖来删掉暗区。

保持原 profile、out 和账本，在实际安全停靠、原 pending 已核销后执行：

```bash
python kit_cli.py --game-dir /Applications/.minecraft/versions/26.1.2 lighting resume \
  --profile <原profile.json> --out <原out目录> \
  --work-baseline <保留的完整首轮regions.json快照>
```

`resume` 保留当前 campaign、cursor、所有已完成批次和实机火把计数，不重新做已经过去的分区。`run` 仍表示显式开始新 campaign；它保留旧批次历史。已有定向 campaign 以后不带此参数的 `resume` 会重新验证同一保留基线，不会悄悄回到全矩形工作。自动补给重建 worker 也携带该选择。

接纳前核对：同原登记 profile／world、全分区索引与 campaign、原 out 下每份完整 raw native scan 的实际格数、修复真实服务器区块检查的宿主版本、世界／服务器／维度／玩家／投影身份、原 scan 事件的请求号／边界／details／控制版本和零库存变化、完整详情重新计算的暗点数，以及原生停靠快照。当前必须是同身份的新鲜健康保护停车且无其他控制者、扫描或人工输入。原基线与全部 raw／事件／停靠证据哈希写入选择记录；变更、不完整或任何当前 pending 都会拒绝，不清除或重放未知请求。

跳过的分区只写 `work_skips`：`new_scan_performed=false`、`region_completed=false`、`placed_verified=0`、`placement_credit=0`。cursor 是队列位置，跳过不表示本轮重新扫描或现场仍然没有暗点。原始基线是分区逐次采样，不是原子世界快照。

工作结束仍完整实际审计 **ALL 150** 登记分区。该参数不能限制 `audit`；中途不产生新的覆盖完成证明，最终 `goal_complete=false` 边界继续保留。定向工作期间的新增暗点只有最终完整审计才能发现；不能用旧零暗记录、预测覆盖或跳过项宣告海岛全部补光完成。
