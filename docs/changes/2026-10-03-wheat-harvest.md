# 注册小麦田的有限收获与原格补种

`potato_harvest.run` 现在支持明确的 `crop='wheat'`；省略 crop 或 `crop='potato'` 保留原土豆布局、journal 前缀/hash、字段及原有收获行为。`potato_farm.Crop` 仅新增收获产物字段：小麦收获 `minecraft:wheat`，补种消耗 `minecraft:wheat_seeds`，两者分别计数。

```python
from potato_harvest import run
from potato_loot_flight import make_pickup

request = {
    'authorized': True,
    'crop': 'wheat',
    'center': registered_layout['center'],
    'radius': registered_layout['radius'],
    'cells': freshly_observed_mature_original_cells[:4],
    'bonemeal': False,
}
result = run(
    client, request, original_cycle_output,
    checkpoint=checkpoint, max_cells=4, bonemeal_budget=0,
    pickup=make_pickup(request['center'], radius=request['radius'],
                       crop='wheat', checkpoint=checkpoint),
)
```

调用者保持现有材料 lease 与已登记田地工作锁，负责到达正常交互距离和收尾。内核不会创建控制器、移动到新田、重连、解除安全锁、翻耕或扩展区域。传入 pickup 时，移动仍由调用者明确提供的既有 helper 执行。

小麦必须命中 `automation/farms/<原种植scope hash>/registry.json`：server、Overworld、完整种植 layout、world_session 全部一致。指定格必须属于 radius 1..2 的原 cells，并在原 `wheat-farm-*.json` 中已登记 planted；原种植或清理有 pending 时不能收获。每个田地的 `harvest-active.json` 指向原周期；即使换输出目录，也不能绕开另一份未决收获。此时返回 `WAIT_RECONCILE` 和 `active_journal`，需要继续核对原文件及原 request，不能从新目录重复挖。

日常收获始终要求全田实际 `minecraft:farmland`、目标实际 `wheat[age=7]`。选物品后与临动作前再次扫描；成熟度、土层、原格空气或手持物变化时等待。每批最多 4 格。小麦的普通 `mine_block` 必须带匹配 request/world/target 的单目标服务器方块更新和 native sequence ACK；仅 `phase=done` 不算破坏确认，未知结果保留原 pending，不重放。

掉落只接受本次新出现、UUID/id 一致、位于该原田格附近的 wheat 或 wheat_seeds。拾取回调每个 UUID 最多调用一次，回调说成功不算物品已入包。谷物与种子的实际库存增量、仍在地上的数量和已观察总量分别核对，两次不同时间的观察稳定且没有任何一种未收齐掉落后才补种。允许真实零种子掉落，但不会从小麦数量猜种子数量；任何消失但无对应库存增量的已见掉落继续 `WAIT_LOOT`。

每次破坏前至少携带 5 个种子，补种后保持至少 4 个。还检查小麦与种子各自的携带空间。补种必须原格仍为空、下方仍为原耕地；只消耗一个实际种子，并以两帧新 `wheat[age=0]` 与完整库存平衡确认。不要求挖除或重新翻耕田地。

结果保留统一的 `phase`、`code`、`harvested_replanted`、`journal`、`known_loot`/`remaining_count`。小麦额外返回 `crop='wheat'`、`wheat_gain`（同 `grain_gain`）和补种后的净 `seed_gain`。`server_verified=false` 仍明确表示整个收获/拾取/种植周期不是完整服务器审计；只有记录内的 mining receipt 使用原生服务器确认，其余为新鲜客户端状态和实际库存证据。

本次只做模块与模拟回归，不部署、不执行游戏动作、不提交 Git。
