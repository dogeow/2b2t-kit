# 材料任务直接调用

Kit 1.9.106 增加材料任务独立接口，启动、查询、暂停、继续和取消均不再需要打开 Kit 菜单。现有菜单和接口复用同一个后台生命周期。

直接命令：

```text
python kit_cli.py materials start --projection
python kit_cli.py materials start --item minecraft:white_concrete --count 64
python kit_cli.py materials status
python kit_cli.py materials pause --job-id <任务编号>
python kit_cli.py materials resume --job-id <任务编号>
python kit_cli.py materials cancel --job-id <任务编号>
```

新接口使用 material-task-request.json 和按请求编号保存的回执，与方块操作的 request.json 分离。返回真实 pid/process_alive；accepted 仅表示命令已接受，不能当作施工完成。身份、世界、版本号、时效、手动移动、健康锁和当前锁定投影都在原生端复核。暂停/取消必须指定准确任务编号，不清除健康锁。超时不重发，旧客户端请求不会在重启后重播。

本轮 509 项 Python 回归、1130 项 Java 测试通过。已安装后通过命令实际启动当前星舰，返回 material-job-f8d287fa-9ba0-441e-92f5-6f19d6446dc1、真实 PID23535；状态查询已从接口读取。整艘完成仍以世界方块全量核验为准。

HMCL 启动经验：同一应用标识可能留有多个启动器实例。先核实真实进程，复用原窗口；鼠标操作未生效时，已验证 Tab 聚焦启动按钮后 Enter 能触发真实启动。只清理本轮明确创建且无子进程的重复启动器，不能批量结束 Java。
