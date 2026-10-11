# 制泥原料取用前整理空间

完整地图施工收麦后种子增加到 198，背包仅剩一个空槽。仓库取土返回明确的 `packed_workspace_required`，旧工序把它当普通缺料继续远程找土，最终航线受阻。没有采到泥土，旧流水线记录保留。

原料泥土或砂砾不足时，先调用已有 `prepare_mud_inventory`，合并普通堆叠或把超额种子存回已登记仓库，再取原料。明确的容量等待传播为 `WAIT_WORKSPACE`，不再触发采集；投料完成后的空间复核仍保留。未知存取、采集和制泥结果仍不重放。

80 项泥流水线、原生收麦及离田核验定向回归通过。兼容运行包从已安装版本复制，仅替换 `material_jobs/mud_pipeline.py`，不夹带未部署的蘑菇柄主包候选。在线安装，无游戏重启；完整地图从 9642/16512 继续，实机取土验收通过：先合并瓶子得到三个空槽，`inventory_staging_before_raw_inputs` 确认空间后，从 `[761015,64,797852]` 正常取出 8 份泥土，没有触发远程采集。证据 `work/live-20261004/map-full-kit-raw-workspace-126/attempt-001/material-job/0008-fetch/sources.json`。
