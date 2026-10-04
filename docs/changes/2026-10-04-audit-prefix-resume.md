# 续接本轮已验证审计前缀

`--audit-prefix` 是显式的只读证据验证入口，供升级后续接同一轮已经完成的审计。它不会暂停、核销未决动作或自动生成停靠状态，也不依据 `len(audits)` 直接跳过分区。

先由唯一实机操作者在当前批次安全清理窗口发出原有 pause；必须等该批真实提交、原 pending 为 None、旧进程结束和同属 Native PARK。之后保存原 `regions.json` 的完整快照，再执行：

```bash
python kit_cli.py --game-dir /Applications/.minecraft/versions/26.1.2 lighting resume \
  --profile <原profile.json> --out <原out目录> \
  --audit-prefix <保留的本轮regions完整快照.json>
```

也支持显式 `lighting audit --audit-prefix ...`。该参数不用于 `run`、其它动作或自动补给。不传参数时保留原来重新审计全部分区的行为；已有前缀标记不会自动授权下一次续接。

接纳条件：

- 原账本及快照均无 pending（包括空对象），同 campaign、world、profile、server、player UUID 和完整模型选择；工作 cursor 已到登记区总数。批次、火把历史、定向选择、已完成审计及 dispatch_sequence 一致。phase、reason 和已处理控制状态可以不同。
- 本轮最后实际 work batch 之后，审计目录编号连续；原索引必须精确为 `0..k-1`，末目录对应当前 dispatch_sequence。不能复用首轮 C1 的 150 条旧列表或任何缺段、额外未知 dispatch。
- 本 campaign 每个正放置批次都需完整原报告、精确原生交互事件／回执、两帧真实 Torch 方块和库存扣一。每个前缀扫描开始时间必须晚于最后真实放置帧的时间。
- 每条前缀都有同角色／模型／世界的完整实际 raw scan，精确格数、请求边界、details、控制版本和事件，修复真实服务器区块检查的宿主版本，以及完整七布尔／两整数／一致风险详情。暗点数从原 raw 数据重新计算，不能信原汇总。
- 审计事件只有已知只读或空气移动，无交互、挖掘、未知终态或库存变化。每份原 `stock-safety.json` 去掉 worker 增加的两个证明字段后，必须等于 automation 下的原生规范 KEEP 回执；原 PARK、final snapshot 与新安全事件匹配。KEEP 原有 false confirmed 标志及同步快照中旧 safety 字段保持原语语义，不据此伪造确认或错误拒绝。
- 两次新鲜当前保护停车及 NativeNoPending 验证，同属最后完成审计的 owner／版本，Torch 库存一致。未确认 mailbox、未决 Torch 意图、当前扫描、人工输入、其它控制者、低健康或身份变化都拒绝。

验证全部成功后保存原快照及所有原件 SHA、真实 Torch 时间和审计请求清单；保留原审计列表，从 k 开始实际读取剩余登记分区。未完成时 `coverage_complete=false`，没有新扫描或放置信用；完成后仍是 ALL 登记分区的逐次真实审计，`goal_complete=false`。失败不改原账本字节、不清 pending、不发送游戏动作。

验证：9 个针对性测试，包括显式保留／无参数全部重扫、C1／间隙／未决／旧 wave／原件缺失、未知扫描／停车、真实 Torch 双帧守恒及时间、角色／模型／当前控制变化。当前 C2 的 32 个完整前缀（从 audit-/00382 开始）及 13 个实际 Torch 回执，两次独立临时副本形状验证通过。模拟剔除 pending／恢复已完成目录编号并刷新末条真实 final 的时间，仅表示证据形状可处理，不表示当前仍运行的工人已满足准入；未写原游戏数据、安装或调用游戏。
