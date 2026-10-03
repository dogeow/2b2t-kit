# 炉子访问阶段允许正常 lit 变化

火把材料任务 `material-job-10314eeb-3e39-4a9e-813a-e746c6e28a1e` 在收取第三个炉子的木炭前被阻断。两次原生单格扫描都完整、world 相同、revision=348：

- `materials-d79affcb549b`，15:14:29.145：`[761027,65,797846]` 为 `Block{minecraft:furnace}[facing=north,lit=true]`。
- `materials-67f89de1b141`，15:14:29.395：同位置为 `Block{minecraft:furnace}[facing=north,lit=false]`。

250 毫秒内只有燃烧属性改变。调用链是 `processing._wait_collect` → `furnace_batches.collect` → `snapshot` → `work_access.approach_faces`。访问辅助函数完整字符串比较误判，尚未发出该炉的接近或使用；原有 lit 恢复仅覆盖之后 `interact` 的明确原生使用前拒绝。

`approach_faces` 默认仍严格比较状态。炉子 snapshot 显式传入 `_lit_only_transition`；只允许同种普通 `minecraft:furnace`、同 facing 的 true/false 变化。访问前后扫描必须归属当前 world/revision、结果 `done`、目标坐标准确；扫描期间 revision 即使被 client 对象更新，也不能借此授权旧访问。接受转换后，发送原生 `approach_block` 的是最新完整状态，同时把转换前状态保留在访问记录中。

选中物品后再次真实扫描。开炉使用要求同一普通炉及朝向、当前 world/revision，发送这次扫描的完整状态。保留原有明确归属的原生使用前拒绝恢复；未知 interact、slot 操作或接近超时不重试，不增加装料或收取循环。

原木炭批次与库存记录未修改。原批次前两炉已收 4+3 木炭，剩余三炉各 3 原料仍为 `loaded`，不能重新投料。7 木炭可合成 28 火把，该任务原保存记录实际为 0/128 火把，不将中间材料换算成已交付成品。后续恢复仍需核对原世界和原批次归属，并跳过已有 `collected` 回执。

验证使用指定本地 Python 运行 `test_work_access`、`test_furnace_open_recovery`、`test_furnace_batches`、`test_material_processing` 和 `test_processing_fuels`，共 68 项通过。新增回归用真实 north/true→false 状态、坐标和 revision 调用真实 `approach_faces`，覆盖默认严格、再次扫描、换炉种/朝向/world/revision/坐标、不完整回包和未知结果禁止重发。只 mock 菜单观察及原生客户端回包，测试使用临时目录。

本次仅源码与离线测试；未操作游戏、部署、提交 Git 或重跑原材料任务。实机恢复尚未验证。
