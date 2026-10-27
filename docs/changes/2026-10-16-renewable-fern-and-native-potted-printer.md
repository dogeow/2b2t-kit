# 可再生蕨苗圃及原图盆栽

从当前服务器既有缓存记录找到蕨产地后，实地采回两株。家中已有树场空地 `(760960,64,797815)` 建立一株母蕨；每轮正常使用一次骨粉长成大型蕨，以剪刀挖上半截，实际收回两株，再种回一株。初次扩张的方块更新迟到时只观察、不重复消耗骨粉；后续跨游戏重启从实际仍在的大型蕨重新规划采收，不改旧回执或重放旧操作。

已实机繁殖出背包 8 株，保留原地小蕨母株；骨粉 41→35，随后实际采到两株雏菊。过程满血，母株和两个实际库存结果均有独立记录。登记在当前服务器材料配置 `renewable_fern_nursery`，原树场保留。

盆栽使用现有投影打印机的 FlowerPotGuide 和 FlowerPotFillGuide 两阶段。仅允许空花盆作为已知中间状态，完成仍要求原图最终盆栽方块的服务器更新，以及花盆、植物各少一件。三个已有支撑的位置已全部匹配，完整别墅复核 **2812/2880**；剩余盆栽等待原图普通石英支撑和脚手架。

新增共享模块 `material_jobs/renewable_fern.py`、`projection_potted_plants.py`，分别覆盖迟到方块观察不重放、两阶段盆栽必须同时核验两种物料。未知结果保留掩码和回执，不换动作重试。

当前实机证据：

- `work/upgrade-26.2-642/villa-fresh-renewable-nursery-after-crash-004/renewable-nursery/fern-nursery.json`
- `work/upgrade-26.2-642/villa-fern8-ready-local-daisies2-002/complete.json`
- `work/upgrade-26.2-642/villa-original-ready-fern-pots3-001/potted-print/`
- `work/upgrade-26.2-642/villa-original-ready-fern-pots3-001/control/after.json`
