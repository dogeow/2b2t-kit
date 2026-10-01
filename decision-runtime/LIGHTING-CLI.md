# 室外照明 CLI

`lighting_cli.py` 是可直接导入的 Python helper 与独立 CLI，复用 `MaterialClient` 的世界、控制版本和 PvE 防护租约，不调用 AI、菜单或模拟按键。它提取室外照明试点的确定性流程；洞穴路线尚未实现，报告始终明确 `cave_routes_completed: false`。

目前只在明确框选区域中的天然草方块上放置普通火把。该草地必须被原生详细扫描确认为实体、无液体、无方块实体、普通僵尸可生成几何，且实际 `spawn_block_light` 不超过当前维度阈值。上方至扫描顶界必须完全是 AIR。候选影响范围仅用于排序，不推断火把后的光照或消除风险；每次放置后重新扫描实际光照。

`--min/--max` 是完整列扫描范围，包含地面至高处停驻的整个身体空间，坐标为包含两端的整数。每次范围最多 50,000 格，Y 为 -64..319。顶界减 2 是停驻高度，候选地面至停驻必须有至少 20 格空隙。大区域应拆成多个明确小框；CLI 不隐式扩张范围。当前实现后续移动仅沿同一工作高度的 AIR 走廊，所以台阶或洞穴应另行规划。

离线规划必须显式提供已保存的原生 `details=true` 扫描；只读取指定文件，完全不读取、连接或控制游戏：

```bash
python3 lighting_cli.py --plan-only --scan /absolute/path/full-column-scan.json \
  --min 761025 60 797860 --max 761045 144 797884 \
  --max-torches 8 --out /absolute/path/lighting-plan
```

输出 `plan.json` 为单次历史观察的候选短表，并不证明当前场景或工作完成。程序接口为 `plan(saved_scan, low, high, max_torches, start=None)`；`candidates`、`cardinal_route`、`compress_route` 和 `later_torch_frame` 可分别复用。

实际执行入口如下。`--game-dir` 要指向包含 `config/twob2tkit/automation` 的实际实例目录；此命令是使用说明，本次开发不执行游戏动作。

```bash
python3 lighting_cli.py \
  --game-dir /Applications/.minecraft/versions/26.1.2 \
  --min 761025 60 797860 --max 761045 144 797884 \
  --max-torches 8 --out /absolute/path/lighting-run
```

开始时必须已经在框内高处防护停驻，满血、食物至少 18、PvE guard 与 Flight 开启、无手动接管和其它正在工作的任务。扫描确认真实服务器已加载区块；屋顶、完整移动身体包围盒、当前扫描包围盒相交的实体都需检查。正常 `navigate air_only` 再次检查原生身体扫掠；同高度路径压缩为转角与终点，避免每格导航。

放置仅使用一次普通 `interact`，指定支持方块精确状态、上表面与火把手持物。该交互回复不是专用服务端放置 ACK。证明必须在两个时间递增的后续原生快照中同时看到精确目标 `Block{minecraft:torch}` 和全部 36 背包槽中火把总数精确减 1。`report.json`、方块和库存帧保留证据。

交互前在游戏 automation 目录的 `lighting-intents/` 写入意图。结果超时、受伤或接管导致结果不明时不重复交互；同世界、同框存在未核实意图会阻止新一轮工作。应先人工核查该记录与实际目标，不能只换输出目录绕过它。CLI 不自动清除或推定这些记录。

收尾先验证当前列至高处停驻的 AIR 身体空间，原生 park 租约与到达，再释放物资 heartbeat。无法证明停驻时保存错误并保留防护续租最多 60 秒用于接管，后续由原生 watchdog 安全策略处理；这不算照明成功。手动接管或世界变更不再发动作。`bounded_run_finished` 仅表示限定流程结束，剩余风险数来自最终扫描，并不等同于房屋、火箭、村庄或洞穴全部完成。

离线验证：

```bash
python3 -m unittest test_lighting_cli -v
```
