# 小岛户外补光 CLI

`decision-runtime/lighting_cli.py` 直接调用现有 Kit RPC；无需截屏、按键、模型或宿主重启。范围是指定框内的户外地面；不会宣称室内、洞穴或整座岛已全部完成。

## 入口与保护

```bash
python -B lighting_cli.py --game-dir /Applications/.minecraft/versions/26.1.2 \
  --min 760802 60 797750 --max 760822 142 797770 --max-torches 8 \
  --protect-box 760810 64 797761 760826 186 797771 \
  --protect-box 761024 -64 797631 761151 319 797759 \
  --out /absolute/path/island-lighting/rocket-batch-001
```

角色应已在框内高空保护停靠点（例 Y140），满血、充足食物、飞行与 PvE 防护开启。每个扫描框至多 50,000 格；分小框执行，不扩大为一次全岛扫描。上例只是已调查区域的调用形式，仍需当前区块加载和实时扫描通过。

`--protect-box` 可重复，min/max 为包含边界的整数坐标。或使用 `--protect-file /absolute/path/protected.json`，内容为 `[{"min":[X,Y,Z],"max":[X,Y,Z]}]`。掩码同时检查支撑方块和火把目标，允许安全飞越其上空。Python 注入入口为 `LightingRun(client, low, high, max_torches, out, initial, protected=boxes)`。

## 验证与复用

- 实时 scan 必须完成、匹配 world_session，并具有两种已知客户端范围 `scan_entity_scope` 之一；未知 scope、缺失实体列表、未完成帧不允许投放。
- 候选仅显式支持草地、泥土、普通沙/红沙及石材地面；实测固体、无液体、无方块实体、可刷僵尸且方块光照不足。木材、耕地、作物、容器、液体及未知材质不放。已有草丛也不破坏。
- 规划只判断所扫框中的净空；每次执行在目标精确一列重新扫到主世界 Y319，拒绝高于规划框的屋顶。临放前再查实际光照、支撑、目标净空和实体。
- 优先同高净空路线。高低不平地面用原列升高、高空水平转移、目标列下降；每段仍验证真实方块与实体扫掠，并核对实际到达。
- 每次只有一次普通交互；完成证据是两个独立后续帧均见精确火把且背包总火把减少 1，**不是专用服务器方块 ACK**。
- 不确定交互保存到共享 `automation/lighting-intents/`，同世界同坐标阻止重放，即使换输出目录也不会绕过。
- 现有顶部 HUD 显示“岛屿补光 已核实数量/本批预算”和已扫区域暗点；不刷聊天。`report.json` 包含 placed、progress、after、remaining_risk、remaining_unprotected_risk 与排除掩码。
- 暗点来自此次扫描，可能含受保护或被屋顶覆盖的地面；仅僵尸方块光照模型，不能保证所有怪物种类都不会出现。最终安全停靠必须有原生 parking 租约与到达证据。

已运行相关 Python 回归；实际投放验收由唯一游戏控制者执行并保存原始证据。

## 10 月 2 日实测修复

实际前 3 批已核实放置 12 个火把后发现：保护正在打怪时即报错，停靠租约异步发布还可能短暂混有新 revision 与旧 materials lease。

- 补光和高空停靠前等待现有防护最多 20 秒，只观察和保活，不发攻击、走位或交互；保护结束再继续。手动接管、世界变化、低生命或安全锁仍立即中止。
- `finish()` 只调用一次；之后最多 4 秒只读观察。仅相同 world/task/lease、原 revision 或原 revision+1、原生 `controller_finished / KEEP_PVE_GUARD`、有效 parking 租约与实际到达共同成立才记录完成。
- 外部租约、继续增长的 revision、手动接管、锁开启或世界切换不会被当成发布延迟；超时保留失败，不重发 cleanup 或旧火把。
- 健康防护忙时 `MaterialClient.finish()` 的错误离线回退由共享客户端修复处理，本 CLI 不绕过安全停靠证明。

保护等待可能移动角色，不能继续沿用之前的点击站位。临放前最多 3 次重新校验：先等待保护，确认实际站位；近距离使用即时 AIR/实体扫掠重新靠近，无法直达才转高空；重新查支撑列、光照、库存与目标实体。在写 interaction intent 前最后再核对站位、防护状态、所持火把和数量。重复移位、路径阻挡或位置越出授权框时停止，不生成新放置 intent、不点击旧目标。历史未知 intent 保留，不按一般 error 自动清除。


可以用 `--movement-bounds MIN_X MIN_Y MIN_Z MAX_X MAX_Y MAX_Z` 显式授权比投放 tile 更大的走位框；Python 对应 `LightingRun(..., movement_bounds={"min":[...],"max":[...]})`。默认与投放框相同。防护轻微搬出 tile 后，可以在授权框内重新到位；候选、目标和放置 intent 仍只能在原投放框内。整体走位授权框不当成一次扫描套 50,000 格上限，每个实际走位扫掠仍单独限额、验证加载方块和实体，并使用原生 air_only 导航。
