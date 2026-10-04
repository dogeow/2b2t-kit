# 已知空气导航终态的安全归档

`lighting reconcile-known-travel` 只读取原件、归档证据并将原 pending 改为等待显式续跑。它不发送游戏请求，不执行救援、不重放导航、不自动恢复任务，也不增加区域完成或放置信用。

```bash
python kit_cli.py --game-dir /Applications/.minecraft/versions/26.1.2 lighting reconcile-known-travel \
  --profile <原补光profile.json> --out <原补光out目录> \
  --travel-evidence <保留证据目录/manifest.json>
```

仅支持原进入阶段的 AirOnly 导航出现精确 `WAITING`：`air-only path changed; no blocks were excavated`。宿主已清理命名回包时，必须有新请求发出前保存的同请求 ID 原生 status 和原 mailbox，以及精确终态事件。它们须匹配世界、控制版本、原 task/lease、角色、投影模型、原 profile、campaign、cursor 和全部历史。原进入阶段不得有交互、挖掘、放置意图、目标工作报告或库存变化。

接纳前须另外已经完成同属原 task/lease 的安全维护。模块只接受：一次独立完整身体柱观察，以及再次完整身体柱扫描、一个原生停车目标更新和一次至多 31 格的同 X/Z 垂直 AirOnly 上升。全部须有精确 DONE 回执，完整真实服务器扫描的格数／版本／实体范围正确，上升身体范围内没有方块或实体，实际停稳净高至少 20 格。新鲜扫描必须来自含真实服务器区块检查修复的宿主 2026.10.4.1 或更新版本。

原扫描 DONE 回包构造时可能保留 `pending_scan` 元数据。只对同 ID／世界／版本、完整格数、`reading_complete=false`、`reply_write_state=not_submitted` 的扫描回包允许这项残留；其后状态及当前停车仍必须没有 pending。它不允许把未完成扫描或未知回包转换为完成。

须先有三个不同时间的稳定上升帧，再显式 SIGINT 旧的只读等待进程并证实进程已结束。之后等待原 owner 的真实 `heartbeat_lost`／`KEEP_PVE_GUARD` 回执，以及三个稳定 PARK 帧和两次当前同属停车复核。复制的回执须与 automation 目录下的原生规范回执逐字节相同。KEEP 分支中的 `confirmed=false` 与 `server_survival_verified=false` 按现有原语保留；成功依据精确原生 KEEP 和当前 PARK 组合，不能由本地断言伪造。

原终态至维护开始期间只容许钻石剑／弓各一次耐久损耗，作为原有保护防御的独立事实保存；其它完整槽位、物品数、附魔／组件／潜影盒元数据及装备均不能变化。维护开始后全部完整背包与装备必须不变。原生途中同属高空停车点重设可以保留，但仍须实际上升位置、原始目标、净高与当前 PARK 都通过确认。

所有原件哈希和源 batch 对应文件重新核对；未知、缺失、漂移、外来 owner、未决 mailbox／意图、仍存活旧进程、低健康或人工接管均拒绝。归档保留旧导航未完成、区域未完成、零放置信用，原 cursor、dispatch_sequence、批次、累计火把及定向选择原样保留。之后需要操作者另行决定是否 `resume`。

本轮实件只读模拟：00369／region64 的原请求 `materials-c3381b18e48e`，新上升 `materials-d7743320de44`，原世界 46、原 task/lease，原 native WAITING 版本 1487；维护 DONE 1488、KEEP/PARK 1489。完整 1536 格柱地面高度 77，实际停稳 Y101.352、净高 24.352。模拟拦截全部归档写入，确认 cursor64、205 个历史批次、累计 222 个已验证火把保留。源码修改期间没有游戏调用或安装。
