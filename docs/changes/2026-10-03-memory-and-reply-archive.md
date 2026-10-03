# Minecraft 内存检查与旧回包归档

2026-10-03 的当前进程两次 vmmap 采样相隔约 8 分钟，物理占用 3.5 GiB → 3.4 GiB，峰值 3.5 GiB。jcmd 实测 Java 堆约 0.74 GiB，上限约 2.66 GiB。用户截图的 18.05 GB 未在这次进程复现，不能据此确认或排除长期泄漏。Bobby 配置视距 32、卸载延迟 60 秒；直方图含 3210 个 FakeChunk。Voxy 当前日志明确报当前系统不受支持，不能将本次占用归因于正在工作的 Voxy 渲染器。

另确认自动化目录积累约 8 GiB 历史回包，磁盘剩余约 400 MiB；游戏配置写入实际报 No space left on device。归档旧扫描证据与诊断内存是两件不同的事。

新增 `kit_cli.py replies` 默认只统计，`--apply` 才无损压缩七天前只读 scan JSON。每个 gzip 临时写入并 fsync，解压 SHA-256 校验，复查原文件 inode/大小/时间和全部字节，持久保存归档后才移除原 JSON。归档原位保存为 `reply-<id>.json.gz`；使用 `--restore reply-<id>.json` 可恢复，拒绝覆盖已有原文件。保留当前请求、被本地任务日志引用的请求、未完成扫描、未知状态、格式异常和操作回执。无游戏操作、断线、解锁、任务重放或成功状态改写。

已执行首批 10000 个旧扫描回包归档：原始 1334242094 bytes，压缩 61866730 bytes，回收 1272375364 bytes。磁盘其余空间变化可能包含系统释放 swap，不归功于本工具。

调用示例：

```sh
python kit_cli.py --game-dir /Applications/.minecraft/versions/26.1.2 replies
python kit_cli.py --game-dir /Applications/.minecraft/versions/26.1.2 replies --apply --max-files 2000
python kit_cli.py --game-dir /Applications/.minecraft/versions/26.1.2 replies --restore reply-REQUEST_ID.json
```

安全行为有回归覆盖：仅统计、不丢字节、保护任务引用和操作回执、扫描后原文件改变、校验失败、磁盘满、批量限额与恢复路径/覆盖保护。
