# Nimble 与 Clef Flash 的 Minecraft Kit 实验

用户于 2026-10-06 明确要求两个模型均做实验。当前状态：原 Nimble 下载继续，
Clef Flash 下载已启动，自动离线对比程序正在等待模型安装，尚无实测结论。
Ollama 0.35.1；网络优先直连，启动检查确认 32 条 Ollama 连接全部使用 DIRECT。

实验目录：`work/live-20261004/decision-model-pair-001/`。
共同数据集为 `cases.json`：20 个历史及构造的 Kit 状态，每个模型测试两轮。
第二轮反转选项顺序，以检查排序敏感性。两个模型依次加载，沿用服务器
`OLLAMA_MAX_LOADED_MODELS=1`，不同时运行两个推理实例。

案例覆盖健康退出锁、手动接管、未知回执、原木 77/78 数量不符、防护缺失、
安全高空停留、固定树催熟与砍伐、旁侧站位、树根格重叠及正上方站位、
当前地图证据是否充分。正确答案人工固定；这些小样本不能证明无人值守安全。

使用相同 `/v1/systemone` 请求与答案校验，记录决策正确率、首次未加载模型
请求的延迟、后续中位延迟与 P95、Ollama 进程 RSS 采样峰值，以及 API 报告
的模型/GPU 分配。首次延迟包含模型加载，不代表操作系统文件缓存也为冷态。
RSS 与 API 分配数值也不等于完整 Metal 物理内存占用。

Clef Flash 另外使用用户此前提供的两个历史截图，区分 Minecraft 断开连接界面
和自动化进度日志。这是视觉能力补充测试，不直接计入两个模型的 JSON 对比。
它不能证明树冠导航或当前场景操作能力。

模型下载由 `pull-clef.py`（Clef）及原 Nimble 下载进程执行，保留原下载回执。
`compare.py` 等待安装成功后自动测试。一个模型失败会保存原因并继续测试另一个，
不自动替换模型或重放下载。下载或推理未完成时不能填写成功结果。
下载中断时须检查原进程及实际错误；只有直连证实失败后才允许尝试代理。

输出包括 `nimble-results.json`、`clef-flash-results.json`、各模型摘要、
`clef-flash-vision-results.json`、`comparison-summary.json` 和实时进度文件。

目前没有向游戏发送任何动作，没有解除健康锁。实机实验仍待本次健康恢复授权。
恢复后，须先安装已准备的旁侧站位修复，核对新世界、库存、防护及手动接管，
确认旧动作控制器停止后，再由一个 Kit 控制器执行经验证的受限动作，比较两个
模型的选择及对应原生动作结果。离线决策正确不能直接计作实机操作成功。

官方接口：

- [Nimble](https://ollama.com/library/nimble)
- [Clef Flash](https://ollama.com/library/clef-flash)
