# Kit 本地模型与游戏帧接入

宿主 2026.10.7.2；引擎 1.7.83/API 3 保持兼容。菜单与截图接口需要完整重启；已在
HMCL 的 26.1.2 隔离实例安装并实机核对。原有配置和工程回执均保留。

## 实现

- Kit 启动本地 Python 决策服务，复用或启动官方 Ollama 服务；固定通过 loopback
  调用 System One。没有自动下载、桌面依赖或模型生成代码。
- 两个模型使用共享权重的 `kit-clef-flash` / `kit-nimble` 别名；通过 `num_ctx`
  配置上下文，`keep_alive=-1` 维持驻留，服务关闭时释放自己管理的模型。
- 常驻状态每五秒刷新；推理共享互斥，配置切换不会与既有推理并发。Kit 仅管理
  两个明确的别名，不根据 `kit-` 前缀卸载用户的其它模型。
- 原生 `decision_screenshot` 输出当前游戏帧和时间、世界、控制版本、尺寸及 SHA256。
  固定使用原尺寸读取，再在后台缩到最多 640×360，兼容不能整除的窗口尺寸。
  Python 拒绝过期、错误范围、符号链接或摘要不符的图片。
- 复用已有 Advisor：候选动作由 Kit 提供，模型返回后再核对状态；等待期间维持
  已有监督心跳。常驻服务自身不操作角色。
- 本地菜单启用会接通投影材料批次选择；云端 Jev 的逐世界启用要求保持原有行为。

提示词版本 `minecraft-stage-v2` 明确区分目标、观察和候选动作，先考虑携带资源，
再考虑已验证库存与采集。禁止根据计时或预测确认施工完成。覆盖范围仍限于本地
控制器已经提供的能力；地图画验收继续依赖实际服务器方块及最终地图像素。

## 验证与证据

Java 全套测试 **1776/1776**，`jar` 和 `verifyRuntimeEngineJar` 通过。Python 的
本地模型、Advisor、投影建议、材料后端及发布检查共 **168/168**；没有将历史全套 Python
基线中的既有失败列为此次通过。

实机证据位于 `work/live-20261004/local-ai-integration-20261007/`：

- `clef-stage-eval-001/summary.json`：8 类、32 个固定阶段样例，32/32；耗时中位数约 2.3 秒。
- `nimble-stage-eval-001/summary.json`：相同样例 32/32；耗时中位数约 2.0 秒，模型分配约 8.73 GB。
- `native-image-test-002/image-proof.json`：原生游戏帧 640×359；模型正确返回 `world`，耗时 5911 ms。
- `live-advisor-equip-001/verified.json`：Clef Flash 选择 `equip_planks`，原生快捷栏切换到 5，背包数量守恒。

固定样例不等同于任意任务成功率；图片分类和快捷栏选择也不等同于无人值守建造验收。

## 调用文档

见 [只开 Minecraft 的调用方式](../usage/只开Minecraft的调用方式.md)。当前实例已保留
60 FPS、模拟距离 5、渲染距离 5，并实测 Java `-Xmx3072m`。持续驻留 Clef Flash
4096 上下文预热报告约 9.75 GB 模型分配，图片调用后实测约 10.83 GB，仍需考虑
18 GiB 机器的整体内存余量。当前常驻 Clef Flash，Nimble 仅作为菜单中的另一选项。

参考：[System One](https://docs.ollama.com/api/systemone)、
[从已有模型创建别名](https://docs.ollama.com/api/create)。
