# 原生材料管线：干燥黏土列采集

原图陶瓦仍缺料。此前逐次临时采集已在实机取得 40 个黏土球并合成 10 块黏土；其中 8 块绿色陶瓦随后由投影打印机铺完，完整服务器审计从 15011 增至 **15019 / 16512**。

将已验证的采集流程加入 `material_jobs/dry_clay_columns.py`，通过已有 `colored_sources.acquire()` 接到陶瓦依赖链。使用现有 Backend/MaterialClient，接受绝对背包目标，不启动第二个行动控制器或模型。

- 仅处理显式登记的 `natural_survey` 区域、列顶坐标、地板高度和竖井入口；每格使用当前完整扫描，地板保持原状态。
- 在已连通空气中移动，使用 0.2 格脚部余量通过两格高通道。仅移除登记列中的普通石头和黏土，保留液体、砾石、容器、保护区及照明支撑。
- 用当前工具和手持元数据执行正常采集；每块黏土必须有实际 4 个黏土球增量。需要黏土块时，通过当前 JAR 的 2×2 配方合成并核对实物收支。
- 原图缺料需要远程产地，复用已完成的 8 段原生航线。只有显式登记的当前世界路线可用于远程行程，每段不超过 320 格；抵达和竖井空气重新由当前接口核实。
- 未确认的移动、采集、拾取、合成保留原意图；跨任务且区域重叠时同样拒绝重放。已耗用的完成记录不能重新提供库存信用，已无黏土的列不会继续挖石头。
- 距离准入在任何动作发布前拒绝时，依据请求身份未改变、没有在途请求和实际位置未改变记录已拒绝，不伪装成已执行操作。

首轮实机调用因为缺少远程路线在出发前拒绝，采集信用为零。单独核对该任务只有接管、只读扫描和停车动作，保留旧任务及原始日志后结清这个未执行的路线意图；随后登记已实测路线并启动新的材料任务。新任务已通过分段路线进入当前竖井，自动采集与陶瓦加工的整体实机验收仍在进行。

验证：相关 87 项专项回归通过，完整 decision-runtime **3743 项测试全部通过，0 失败、0 错误、0 跳过**；材料后台可重复打包与隔离导入通过，已热更新至运行实例。没有修改或重启宿主、引擎。逻辑检查和安装不代表整张地图或新管线的完整实机验收。

证据：

- `work/upgrade-26.2-642/current-dry-clay-two-columns-v2/result.json`
- `work/upgrade-26.2-642/current-dry-clay-return-and-green8/clay-compaction.json`
- `work/upgrade-26.2-642/current-dry-clay-native-green8-print/map-result.json`
- `work/upgrade-26.2-642/native-dry-clay-installation/pre-dispatch-refusal-settlement.json`
- `work/upgrade-26.2-642/precommit-validation/native-dry-clay-route-python-full.{json,log}`
