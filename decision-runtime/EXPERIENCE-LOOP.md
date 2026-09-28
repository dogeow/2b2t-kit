# Kit 离线经验闭环（第一步）

`experience_loop.py` 从 Kit **已经产生的本机记录**提取有限、去标识化的状态／建议／实际动作／结果。它不连接游戏，不请求 Jev、Laya、Kev 或其它服务，不自动写代码，也不会把学到的策略接入运行中的控制器。玩家接管和原生安全防护仍由 Kit 负责。

三个输入各有不同证据强度：

| 输入 | 保存的事实 | 可用于动作排序？ |
|---|---|---|
| `jev-mining-stalls.jsonl` | AREA 矿工卡点类别、Jev 的候选建议、手动重启后的客户端观察结果 | 否。建议没有被自动执行；看到目标变为空气、列进度变化或角色移动都不是服务器动作回执，移动也可能来自人工操作。没有重启结果的事件被视为未完成。 |
| `dry-paving-v1/*/*.json`、`paving-blockers.jsonl` | 一格铺地的挖掘／拾回／放置确认链，或守卫拒绝原因 | 否。完成可用于确认流程，拒绝可用于故障分类；都不足以泛化为其它位置安全。 |
| `build_supervisor` 的 `events.jsonl` | 实际执行的补料／重扫／重新规划等动作及其后续增量 | 只生成离线候选。至少三个**不同任务**有确认进展，且没有一次未确认或无进展，才标记为“供人工审核”。 |

使用时显式指定本地文件。示例中的路径要换成当前实例及运行目录；读取和报告不会控制游戏：

```sh
python3 decision-runtime/experience_loop.py --store /path/to/private/experience.sqlite3 ingest \
  --mining-log /path/to/config/twob2tkit/jev-mining-stalls.jsonl \
  --paving-dir /path/to/config/twob2tkit/automation/dry-paving-v1 \
  --paving-blockers /path/to/run/paving-blockers.jsonl \
  --build-events /path/to/supervision/events.jsonl
python3 decision-runtime/experience_loop.py --store /path/to/private/experience.sqlite3 report
python3 decision-runtime/experience_loop.py --store /path/to/private/experience.sqlite3 export \
  --output /path/to/private/labeled-examples.jsonl
```

如果想在游玩时持续收集新经验，可以**自己显式启动** `watch`，指定要观察的来源；默认每 15 秒看一次、运行 30 分钟后结束，最长 120 分钟。按 Ctrl+C 可提前停止，数据库会正常关闭。目前没有安装常驻服务，也不会随游戏自动启动：

```sh
python3 decision-runtime/experience_loop.py --store /path/to/private/experience.sqlite3 watch \
  --mining-log /path/to/config/twob2tkit/jev-mining-stalls.jsonl \
  --paving-dir /path/to/config/twob2tkit/automation/dry-paving-v1 \
  --interval-seconds 15 --minutes 30
```

`watch` 只输出新入库条数与总条数；固定周期重新读取时按记录去重。超大日志会额外报告 `tail_only_sources`，表示本轮只看到了文件尾部。它不会实时改动挖矿或建造决策，也不会自动上传数据。尚无重启后观察结果的卡点保持未完成，不会为了追求样本数把暂停当成失败。

重复导入同一记录不会重复计数。数据库最多保留 10,000 条；JSONL 日志每轮从文件末尾最多读取 4 MiB 的完整行，每行最多 16 KiB，只处理最近 2,000 条。超过 4 MiB 的历史开头不会进入这一轮，但日志继续追加后的新行仍可导入。铺地日志每轮最多遍历 2,000 个目录项，`watch` 保留扫描位置，后续轮次继续；新建文件即使排在旧文件后面，也会在完成当前遍历并重新扫描时被发现。超限、损坏、证据不完整的记录跳过。数据库只存预先列出的类别与经过本机随机盐 HMAC 处理的去重标识；导出文件不含账号、服务器、坐标、绝对路径、原始聊天、模型原文、任务 ID 或时间戳。**请勿把原始日志当成可公开的数据。**

`report` 在同一场景内按“确认进展的独立任务数”给候选一个证据顺序；它不是成功概率或速度比较。任何无进展／回执不明的任务都会让该场景动作暂时弃权，直到对记录做人工分析。

导出的 `training_use=diagnosis_only` 适合训练“识别什么情况需要复查或停止”的分类器，不能当成动作正确性的标签。只有 `training_use=recovery_candidate` 才来自执行过且有 Kit 回执的恢复动作；即便标为 `confirmed_progress`，它也只是动作后有进展的关联证据，不能证明动作是唯一原因。`report` 输出的 `candidate_for_human_review` 不是自动执行授权。

要实现真正的持续改进，下一步需要在隔离测试世界为每个候选策略做回放和对照验证，记录失败、风险、版本与服务器差异，再由人工审核代码和安全边界。在线探索、自动改代码及直接使用模型建议尚未接入。模型训练也需要独立的数据许可、划分与评测；这一步只准备可信的最小样本。
