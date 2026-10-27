# 当前世界水洞线索、有限探路与荧光墨囊等待

主世界收尾缺少荧光墨囊时，先读 Kit 仓库记录和当前服务器、维度、世界指纹对应的 Bobby 缓存。`cached_cave_water` 只从有完整区块和有效方块调色板的缓存中提取低层水及上方空气线索，缓存不计库存，也不证明服务器当前有水、空气路线或发光鱿鱼。实际操作前必须重新扫描服务器已加载区块并核对完整格数。

本次已在既有滴水石矿洞附近实测到流水洞。`dry_cave_probe` 采用交替两列、最多 32 块的短探路，保留当前站立列和支撑；实际清理 31 块普通石料，每块均有原生移除回执，19 个圆石和 12 个花岗岩全部入包。随后 `dry_cave_connection` 按完整实测路线清理恰好 7 块普通石头，保留液体、容器、落沙、照明和保护区域。两次运行各完成 2 块和 5 块移除；原中断路线没有被标为完成或重放。

一次普通僵尸碰伤及短暂着火触发了导航停止。守卫清除威胁、火结束、生命恢复 20 后，单独保存原因、连续健康观察、当前威胁扫描及原移动回执，正常交接租约，从实际停止点新建剩余五块计划。没有扩大通用恢复规则来自动放行未知受伤，也没有发生健康退出后自动重连。

窄通道中的一次实际碰撞停止保留原回执，再核对当前位置，重新居中并改用较短空气段；没有把石头或水当空气。`glow_cave_hunt.spawn_wait_poses` 从已实测的双格空气连通图选择位置，与每格候选水均相距至少 25 格、至多 96 格，避免站在水边阻止自然生成。发光鱿鱼只通过当前世界、服务器、维度、时间均相符的原生已加载实体记录确认；尚未看到实体不等于已有材料。

荧光展示框合成增加精确批量配方：仅接受一个普通展示框和一个荧光墨囊、产出一个荧光展示框。九次批量规划保留第十个普通框，输入位置、配方身份和产出数都有回归覆盖。真实合成和摆放仍须另有服务端库存及实体验收，不能以规划或测试通过代替。

本阶段对应验证：`test_glow_cave_hunt`、`test_dry_cave_connection`、`test_loaded_squid_survey` 共 8 项通过；`test_furnishing_stack_recipes`、`test_stack_recipe`、`test_material_manufacture` 共 54 项通过。工作器新包完成源码哈希、归档检查和隔离导入，安装以独立回执为准。

证据目录位于 `work/upgrade-26.2-642/`：

- `overworld-31-block-dry-probe-001/ordinary-natural-dry-probe/probe.json`
- `overworld-targeted7-water-cave-connection-001/exact-seven-dry-wall-connection/connection.json`
- `overworld-targeted-remaining5-water-connection-001/exact-five-dry-wall-connection/connection.json`
- `handled-zombie-fire-resolved-owned-handoff-001/resolved-known-zombie-fire-proof.json`
- `flowing-water-first-wait-readonly-lower-cave-001/actual-lower-water-result.json`
- `actual-lower-connected-water-glow-hunt-001/hunt.json`
- `cached-water-and-glow-frame-batch-worker-002/build-proof.json`

现有一个荧光墨囊已经正常合成，并用于原图 `[761011.03125,67.5,797834.5]` 的空荧光展示框；实体 UUID、朝向、旋转和内容均匹配。此项已完成，其余八个尚待真实墨囊，不能因为计划了九个就一并计为完成。证据为 `villa-carried-glow-frames-after-cave-001/original-empty-glow-frame-00/frame.json`。

一次穿门后的八格空气段在门边实际碰撞停止。`projection_air_exit.leave` 增加有界的 `max_straight` 参数；恢复从真实停止点重新实测完整地板、正常短步行居中，再使用两格空气段，保留原停止回执。相关出口与空气路线 31 项回归通过，实机已退出房屋；该工作器的独立热安装回执仍须另行核对。

后续实测家旁自然洞道 `[760977,65,797914]` 可通到 `[761040,17,797852]`。完整服务器读取覆盖 268804 格，沿原空气洞道到达，没有拆改院子或开新洞。大水域实测水格 6171、水源 6092，其中黑暗低层水格 4980；这些是实际地形信息，不是荧光墨囊入包证据。

一次空气航段经过岩浆上方后受到岩浆接触及残余火焰伤害。只检查脚部与头部空气不足以保证临时飞行设置恢复后的安全；`glow_cave_hunt.component` 现在排除岩浆、明火、燃烧篝火、岩浆块和刺伤植物周围的身体与脚底缓冲，同时要求缓冲范围也已被观察。明确审计火已结束、生命恢复、具体威胁后，仅沿完整新扫描的干燥身体通道向远离岩浆的一侧退离；没有重新发送原中断航段。

`cached_cave_water` 增加显式水源数量与水量排序，仍保留缓存仅作线索的边界。`spawn_viewpoints` 按 25 至 32 格范围内、上方有连通干燥空气的黑暗水格估计可采收区域；可要求候选点脚下具有实际实心、非液体、非容器地面。没有要求玩家必须远离每一格水，也不把所有深层封闭水体都计为可从岸边采收。新站点仍须逐段实际空气扫描和抵达后地面实测。

相关 Python 分组 43 项通过；`supported-density-and-heat-safe-worker-007/installed-and-verified.json` 确认 323 个源码文件已热安装并逐一核对，未重启游戏。地图画在当前世界 `4a7b94fe-e4d0-4252-a879-0ae73f25cd49` 再次通过 16512/16512 实物核验，持有地图 67938 的图案像素匹配 16384/16384；地理元数据及协议像素新鲜度不因此被伪造成已验证。
