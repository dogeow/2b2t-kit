# 分区补光接入 Kit CLI

`lighting_regions_cli.py` 把单批补光和跨区导航接成固定 journal 的本地流程，不调用模型、截图或按键。现有入口 `kit_cli.py lighting` 支持 `run/resume/audit/status/pause/stop`。没有宿主或引擎 API 变化。

## 调用

```bash
python -B kit_cli.py --game-dir /Applications/.minecraft/versions/26.1.2 lighting run \
  --profile /absolute/path/lighting-profile.json
python -B kit_cli.py --game-dir /Applications/.minecraft/versions/26.1.2 lighting status \
  --profile /absolute/path/lighting-profile.json
```

初次可以指定 `--out /absolute/path/journal`，之后服务器和维度的 registry 固定该目录与规范化 profile；换目录、改名字或新 profile 不能绕过未决任务。示例 profile 的坐标仅为格式示例，必须改成玩家明确授权的实际范围。

```json
{
  "schema": 1,
  "authorized": true,
  "server": "example.invalid",
  "dimension": "minecraft:overworld",
  "batch_torches": 8,
  "max_batches_per_region": 8,
  "movement_bounds": {"min": [0, 60, 0], "max": [100, 142, 100]},
  "protected": [{"min": [40, 64, 40], "max": [55, 120, 55]}],
  "regions": [
    {"name": "庭院", "min": [0, 60, 0], "max": [20, 142, 20]},
    {"name": "沙地", "min": [21, 60, 0], "max": [41, 142, 20]}
  ]
}
```

每个 region 一次扫描不超过 50,000 格。显式移动框可更大，但必须覆盖全部 region；每次实际 `air_only` 导航仍受移动框、真实净空和实体检查限制。范围、数量、名字都不硬编码个人岛屿。保护 mask 同时保护支撑与火把目标。

## 流程和真实状态

本地 flock 防同区域 worker 并发；开始前核对实际原生 lease、server、dimension、锁、手动操作、满血、食物与飞行保护。跨区复用现有 `_travel`，每批复用 `LightingRun`，有实际 `park_native_confirmed` 才记录批次已结束、清除 pending。顶端 HUD 沿用补光进度，最后复核时显示“补光复核”。

缺火把在创建原生批次前停为 `waiting_materials`，补货后 `resume`。显式 `run` 可创建下一轮真实复查与补光，旧批次记录不删除。`pause/stop` 写本地控制请求，不发送外部聊天；正在进行的原请求由已有输入暂停/急停和原生控制权处理。

任务末尾重新到每个 profile region 扫当前光照，分别保存真实暗点、保护暗点、候选数、观察时间。队列处理完不等于全島完成；`coverage_complete` 只表示配置的框都被顺序重新扫描，`goal_complete` 始终为 false。剩余暗点时状态是 `audited_with_remaining_risk`。这是普通僵尸几何和方块光照模型，涵盖加载区块、非原子观察；不保证所有怪物或未登记区域，也不擅自处理建筑内、树冠下或洞穴。

## 中断与未知动作

每个原生批次启动前保存 `pending`，启动后保存 task/world/lease 与原请求身份。健康损失、手动接管、外部 revision、断线和未知火把结果都保留原 pending。`resume` 不会重放未决批次、旧火把或清理动作。未知 intent 的通用 error 不能自动清除。

若原动作或安全停靠无法确认，本地 worker 保持 flock 和 heartbeat，只读观察原任务；防护结束不等于导航结束。只有已经实际停在原高空点、原请求终止且保护/lease 已验证时，才允许一次安全收尾；若迟到原生 parking 已明确成立，只记录观察。手动、世界或 lease 更换让出，低血量走已有安全锁逻辑，不自动重连。未知状态可能需要玩家或维护者读取原证据处理；不能以一次新输出目录绕过。强制杀掉进程仍由原生监督策略接管，不承诺任意未知位置均能保持在线。

代码和隔离测试完成后才安装；本项文档不代表多人服已验收。
