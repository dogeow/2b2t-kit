# 洞穴中射线受阻的苦力怕占用防卫目标

实机记录：2026-10-16 20:23，原生采集途经家中洞穴时，角色停在 Y12.87，多个苦力怕处于 Y6；防卫状态为“射线被挡，举盾等待 苦力怕”，同时 recent_attacker 记录骷髅，生命值降至 18.158667。随后用户手动移动接管，自动控制停止，没有重放未完成的 approach_block。

证据：`work/upgrade-26.2-642/current-cave-single-controller-001/006-lower-supported-approach-after-corridor/error.json` 保留原动作及未知回执；该动作没有计入到达、击杀或材料收获。

引擎 1.8.7：苦力怕连续 10 tick 无可用射线时，开启 100 tick 的反击窗口，只从原战斗会话中当前可攻击且确实最近攻击玩家的远程怪物中选目标。窗口跨越目标切换，避免下一 tick 又切回苦力怕而取消拉弓；反击目标也持续受阻时取消窗口。紧急苦力怕躲避仍在实际攻击之前执行，未解决的怪物记录照常保留。

新增 5 个状态序列回归，验证进入窗口、跨目标切换保持、目标失去当前可攻击证据、窗口到期和战斗结束清理，以及反击射线也受阻时回退。完整 Java 测试、jar 和 verifyRuntimeEngineJar 已通过；实机应用与作战效果单独记录，构建通过不表示已实机验收。

另加入 Python `wait_exact_idle_terminal`：原生只读扫描回执与 status 中 pending_scan 清理可能不在同一帧，交接前只观察等待原有严格证据条件满足，不重发请求、不自行关闭心跳。新增 2 个时序回归，相关 9 项 Python 测试通过。

已在当前多人世界热更新为 1.8.7，runtime_generation 从 1 到 2，世界会话保持 `6e19c938-9d25-43fa-8d5d-503fa087fef7`。证据：`work/upgrade-26.2-642/current-cave-single-controller-002/verified-live-hot-engine.json`。这是安装和连续性证明；尚未将构建验证等同于该反击场景的实机作战成功。
