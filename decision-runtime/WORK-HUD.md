# 顶部作业进度

Kit 1.9.98 在游戏顶部合并显示一行 `作业 · 完成数/目标数 · 当前步骤`。混凝土、沙砾、投影建造使用各自真实计数；未设数量上限的功能仅显示已完成数。砍树按确认完成的整棵树计数，种田、喂养、钓鱼、挖矿和目的地指引显示对应状态。防护或回血期间保留数量并替换步骤。打开菜单、F1、切换世界或手动接管时不会保留旧任务。

Jade 的公开 `OverlayRenderer.animation.rect/expectedRect` 已包含界面缩放。作业栏读取这两个实际矩形，取两者下边界并留 6 个 GUI 像素空隙；不修改 Jade 配置。提示过高时隐藏作业栏，避免盖住提示或准星。可选 API 不兼容时也隐藏，而非猜测位置。没有目标提示时正常使用顶部空位。

## 脚本接入

使用现有 MaterialClient，继续通过原有控制接口工作，不需要截图或按键：

```python
client.start_progress('混凝土制作', 800, done=0, phase='补充原料')
client.set_progress(phase='凝固并回收')
# 只有服务器反馈和实际物品收回均通过核对后才累计。
client.advance_progress(verified_count)
client.set_progress(phase='存放成品')
```

`shore_concrete.convert(..., on_progress=client.advance_progress)` 在每小批精确核对后累计；外层配额不会被每批 8 块的临时配额替换。存箱不减少已完成数。finish 先显示安全收尾并在退出时清理自己的显示。

显示文件 `config/twob2tkit/automation/job-progress.json` 仅包含标题、阶段、数量、世界/控制会话及更新时间，不包含凭据。约每 250 ms 原子更新，5 秒失效；仅当前监督任务及控制版本匹配时接受。宿主复用现有状态快照，渲染过程不读磁盘、不扫描世界；文件异常不影响游戏动作或防护。快照能力字段为 `job_hud_protocol: 1`。

安装涉及宿主界面，需要完整重启。后续任务进度更新自动生效。
