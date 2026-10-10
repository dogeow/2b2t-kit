# 地图画自动编排接入

本次把地图画专用脚本的普通方块批次计算迁入 Kit 源码，并提供接入现有材料调度器的独立入口。源码和离线验证不会启动游戏控制者、改写当前任务账本、安装 worker、修改游戏配置或切换正在运行的任务。

## 已实现

- `projection_flat_plan.py` 从完整原生模型、当前实机审计和 43 槽库存计算下一步。模型逐格内容重新计算原生哈希；世界坐标、保留格和已登记火把均由任务输入提供。
- 优先选择当前携带材料对应的最近有支撑 3×3 区域，以实际手持堆叠和剩余批次预算裁剪连续施工掩码，每堆保留两个方块。无实际支撑时仅提出一个原生 AirPlace 起始块，再根据确认后的地形重新计算。
- 无可用材料时复用 `projection_stock_plan.plan_stock` 计算一批补料目标，包含保留数量和实际背包容量。工具、命名堆叠、装备、副手和潜影盒内物品不当作可施工现货。
- `projection_flat_backend.FlatMapBackend` 复用已有 `Backend` 的唯一客户端和 `MaterialJob`。取料、原料采集、配方依赖、熔炼、固化、容量调整和后续批次继续由既有材料调度器执行。
- 每个局部窗口先正常导航和扫描，再核对真实手持、设置精确掩码并调用原生打印／起始块接口。原生 ACK、当前实体方块、物资净消耗三者一致后才记为已完成。
- 本批最多施工 128 格（任务可设置 1..256），窗口间使用局部扫描；本批结束再完整审计。内容哈希和几何索引在批内复用，不逐格重读整个模型。
- 所有窗口保留独立账本。任何未知结果都保留原请求，阻止重放、移动收尾或清除未知掩码；已匹配的保留格可以提供实际支撑，但不会升级其旧回执。

## 使用入口

默认只做离线规划，不读取游戏 mailbox，不导入动作后端：

```sh
python projection_flat_jobs_cli.py --model model.json --audit audit.json \
  --snapshot snapshot.json --policy policy.json --out new-plan.json
```

输入模型／审计可使用原生回执或内层对象。离线结果写入一个新文件，拒绝覆盖历史结果。

新任务显式使用该适配器时：

```sh
python projection_flat_jobs_cli.py --execute --request request.json \
  --automation /absolute/path/to/automation --out /absolute/path/to/new-job
```

`request.json` 保持既有材料任务协议（`schema/id/mode=projection/projection_key/targets/context/created_at/target_stack_sizes`），增加：

```json
{
  "flat_map": {
    "schema": 1,
    "content_hash": "实际完整模型的64位sha256",
    "max_cells_per_build": 128,
    "excluded_positions": [],
    "registered_lights": []
  }
}
```

登记数据属于当前投影；不得把未知的旧请求改成成功，也不能用旧库存、炉内在制品或仓库提示替代当前库存。原生模型、当前控制租约和投影变化时必须重新核对，不能沿用旧任务执行。

## 验收范围

此入口处理完整水平矩形中的普通完整方块，采用现有 Kit 原生接口。带轴向、剥皮或其他状态属性的方块继续使用已有专用适配器；当前新入口会明确停止，不猜测替代物、拆除已有方块或丢弃玩家物资。

`MaterialJob` 的完成表示当前投影方块全部通过实机审计。最终地图物品的比例、地理中心和 16384 像素验收属于另一个既有流程，不由该入口冒充完成。

已在原控制者正常结束后，使用当前世界和真实投影进行4格实机小批验收。入口仍由仓库源码运行，未安装为游戏默认 worker，也没有将其它正在运行的任务切换到此入口。继续放大批次前，仍需按具体材料来源处理实际缺口。

## 本次验证

18 项新增回归及相关库存、掩码、登记火把、材料调度和后端测试，共 215 项通过。包含原材料调度器的完整采集→熔炼→施工→补料→完成模拟循环，以及原生未知窗口保留、人工接管、另一控制者、物资守恒和默认离线入口验证。

使用保留的 16512 格地图原生模型与 7522 格匹配审计进行离线回放，重新核对模型内容哈希、31 个保留格与 6 个登记火把，批次计算耗时约 0.24 秒；发往游戏的请求数为 0。这是历史资料的纯计算回放，不是当前实机施工速度或新入口的实机验收。

离线证据：`work/flat-map-orchestration-side-20261010-xzkupayr/offline-replay.json`。

## 最终下降与实机小批验收

首次接入前确认旧导航调用使用 `keep_cruise=True`，只会保持高空而不会落到窗口施工站位。已改为最终下降，并在扫描、选择材料与设置掩码之前核对角色距计划站位不超过0.75格。新增回归覆盖高空到达不能触发任何材料动作，以及从Y140正常下降后才允许打印请求。相关124项通过。

当前世界 `af3be53c-e1e2-4a77-a68a-08feba5a741c`、宿主2026.10.10.1、引擎1.7.96，实际从高空下降到约Y66.6。两次原生窗口真实放置3＋1个闪长岩，库存6→3→2，掩码正常清除，完整图面增量为4，原生高空KEEP已取得。独立全图复核确认8766／16512，剩7746。随后完整Y64..66薄表面复验为0暗点。

实机脚本在正常 `Backend.finish()` 释放客户端之后错误读取 `b.client`，只影响外层报告收尾。原窗口与原生停车原件保留；独立只读审计完成确认，没有重放施工。未来脚本已在finish前保存客户端引用。

证据位于 `work/live-20261004/flat-map-four-cell-native-pilot-af3b-002/backend/` 的两个 `flat-window.json`、原生回执、实物扫描及 `control-001/stock-safety.json`；独立复核为 `flat-map-four-cell-native-pilot-current-audit-af3b-001/audit-result.json`，薄表面复验为 `forest57-mixed-three-cap-current-preflight-af3b-001/actual_current_map_thin_after_four_cells.json`。这验证了实际4格施工，尚未证明所有材料来源或整个地图画完成。
