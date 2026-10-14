# 干燥黏土补料与重连续工

原地图画仍为 16,512 格完整投影，最后独立成图还需要实际地图像素核验。补料、矿区扫描、脚本退出均不代表地图画完成。

## 已验证的现场

- 干燥地表矿区 tile `[759280, 796080]` 的四段完整原生扫描读到 1,441 块黏土。计数只是产地证据，不计入背包；扫描跨客户端 tick，并非原子服务器快照。证据为 `work/live-20261004/dry-land-clay-reconnected-live-survey-407/attempt-001/result.json`。
- 入口使用原有 `_access_shaft` 和 `rock_quarry_batch completion=clear`，逐段检查液体、落沙、容器和底部支撑。第二段 12 格已由新维护请求补完，旧停止回执保留。
- 后续 AREA 出现未返回的破坏确认；`411` 未把该段记为清空，也未重复发送原未知操作。期间日志出现普通协议解码断线 `unknown packet id 24/118`，没有新的低血量退出。日志只能确认现象，尚未证明两者同一根因。
- 重连后使用新世界的实际扫描观察入口，不把旧预测当作完成。`417` 通过普通 `mine_block` 和实际掉落拾取采集四块黏土，背包黏土球逐次 `0→4→8→12→16`。每次矿块回执均为 `single_target_server_block_update_and_native_sequence_ack`。证据为 `work/live-20261004/dry-clay-ordinary-harvest-417/progress.json` 及对应 `mine-*.json`。
- 用户随后手动采集、整理背包。自动控制等待手动移动结束；后续实际 297 块黏土不归因于上述四块自动采集。

## 集成到 Kit

`material_jobs/colored_sources.py` 的黏土源识别允许周围自然岩石和自然岩石支撑，避免把花岗岩、安山岩误作建筑障碍。邻近落沙只有在完整保留的自然实心支撑上才允许存在；不移除沙砾支撑，不开放液体或容器。黏土源按上层、较近的位置排序，其它作物的顺序和保护不变。

20 项 `test_colored_sources`、`test_resource_cached_survey` 检查通过。安装包只从已装 worker 的 260 个清单文件构建，只替换 `material_jobs/colored_sources.py`，保留其它文件及已有染料配方。导入检查通过，旧版已备份。

安装证据：`work/live-20261004/dry-clay-source-worker-420/installation.json`；清单 SHA-256 `481d1cd910bb9a9d882eca0be8b6373b03b082890f537afc4f0b8fa6414d5d53`。这些是 Python worker 变更，不需要重启宿主或更改引擎版本。

## 继续施工

`clay-return-home-and-map-422.py` 在当前健康、静止、无界面且投影仍一致时接管。若用户已离开矿坑，不再要求走旧矿坑出口。返航目标来自当前原生租约绑定的 saved Home，每段用实际位置和新原生回执核验。实际黏土库存返航期间必须守恒；完成返航后调用原完整投影续建入口。旧未知回执保持原状。
