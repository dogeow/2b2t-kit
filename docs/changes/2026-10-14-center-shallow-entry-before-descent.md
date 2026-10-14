# 浅层采坑重进先居中再下降

实际煤矿入口 `[760806,72,797981]..[760807,77,797982]` 已有一列空气。角色停在 `x=760807.002,z=797981.968,y=78` 的格边，浅层规划先下降，身体扫到隔壁的顶部泥土。日志随后要求挖 Y=76，但真实射线仍碰到 Y=77，造成 aim 暂停，没有增加煤。

`BorerAreaPlan.horizontalStep` 现在在切换高度前先核对当前列属于选区且底部身体空间已清空，然后在当前高度居中并刹停。原来的碰撞、液体、保护列和选区检查保持生效。它不会为居中挖掉邻列顶部。

新增回归使用真实浅层规划、射线和独立身体碰撞模拟，从同样的格边高度进入一个已有空列；第一步必须为保持高度的水平居中，随后完整处理其余 18 格。

- 全部 1,956 项 Java 检查通过，`jar`、`verifyRuntimeEngineJar` 通过。
- 引擎 1.7.99 已备份、安装、正常热加载；实机确认导航引擎同为 1.7.99、generation 增加一次，血量 20、背包不变。不更换宿主，不需要重启游戏。
- 引擎 SHA-256：`55e6d827fde71264b28531627365414c8210470f1ee6c00a2011e302dcc78fad`。
- `coal-center-maintenance-and-map-428` 在新维护账本中重新扫描已知停止的入口。旧回执 pending=0、剩余 18，保持原记录。入口完成后实际煤 `12→16`，collect 回执确认增量 4、pending=0，已完整带回原生 saved Home。

安装、热加载和实际采煤证据分别为 `work/live-20261004/center-shaft-engine199-424/installation.json`、`center-shaft-live-reload-425/result.json`、`coal-center-maintenance-and-map-428/acquisition/acquisition-coal.json`、`coal-center-maintenance-and-map-428/return-result.json`。

旧续建请求仍固定 1.7.98 的安装哈希，因此正确拒绝了新文件。`full-map-engine199-request-430.json` 只更新 `runtime_update` 到已验证的 1.7.99/hash，其它原地图范围、内容哈希、16,512 格目标及最终实际地图核验要求不变。
