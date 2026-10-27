# Harness² + Minecraft Kit

本地部署位于相邻的 `harness2/`，官方版本固定为
`1cfe254e8d25b15f37048c3730134686abe60335`，Python 3.12 独立环境，包版本 0.1.0。
官方示例与本接口在 macOS 实际通过；上游完整 benchmark 文档仍以 Linux 为目标，未验证其全部 benchmark。

## 中文界面

双击同目录的 `打开Harness工作台.command`，会启动本地服务并打开浏览器。
已运行时直接访问 `http://127.0.0.1:18768`。终端窗口保持打开；关闭终端会停止服务。
无需打开 Codex 聊天窗口，模型分析仍调用已登录的 Codex 命令行。

界面可以填写中文任务、选择历史/当前快照、本地检查或 Codex 改进，
并查看各阶段答复、完整模型请求与反思原文。本地检查只执行固定规则，
只有 Codex 改进会解读任务文本；发送快照前须在本次运行勾选许可。
目前仅接入刷铁机诊断，不会自动完成其他建筑或接管游戏。

## 工作方式

Codex 提出诊断策略 → Harness² 在同一份不可变现场证据上进行 Propose–Probe–Compose →
输出下一步交接单 → 当前 Codex 根据最新游戏状态，通过已有 Kit 唯一控制器操作。

这个版本实现的是**诊断与交接**。不会自动执行交接单，也没有宣称刷铁机施工或产铁完成。
模型只能修改隔离目录中的说明和诊断检查列表；模型代码不会被执行。
所有探测均为本地确定性检查，不能模拟 Minecraft 物理，也不能证明未观察到的游戏效果。
项目内 `project-library/` 保存 Harness² 自身的实验记录，不修改 Codex 个人记忆或 Notion。

## 命令

从 `2b2t-kit/` 执行，使用 `../harness2/.venv/bin/python`：

```sh
# 只读获取当前连接/健康/村民及历史施工记录，不发送游戏动作
../harness2/.venv/bin/python integrations/harness2/minecraft_harness.py capture \
  --output work/harness2-iron-farm-20261019/snapshot.json

# 完全本地诊断，不调用模型
../harness2/.venv/bin/python integrations/harness2/minecraft_harness.py probe \
  --snapshot work/harness2-iron-farm-20261019/snapshot.json \
  --output work/harness2-iron-farm-20261019/local-handoff.json

# 仅在明确授权发送该快照给已登录的 Codex/ChatGPT 后执行
../harness2/.venv/bin/python integrations/harness2/minecraft_harness.py run \
  --snapshot work/harness2-iron-farm-20261019/snapshot.json \
  --output work/harness2-iron-farm-20261019/iteration-1 \
  --allow-snapshot-upload

../harness2/.venv/bin/python -m unittest discover -s integrations/harness2/tests -v
```

模型调用使用现有 ChatGPT 登录，保留用户配置的模型，禁用用户配置加载，使用只读沙箱；
不会启动上游默认的无沙箱 Codex benchmark 启动器，也不配置 Google Cloud 或额外 API 密钥。
优先使用桌面应用自带的新版 Codex 原生程序；缺少时回退到 Homebrew 原生程序，避免损坏的 Node 启动脚本。
当前桌面执行器为 0.163.0-alpha.10.2，原 Homebrew 0.142.2 无法运行用户当前配置的模型。
验收会拒绝“模型编辑均失败但上游保留基础方案仍显示任务成功”的结果。

每个输出目录绑定一份快照，快照变化必须使用新目录；旧动作回执保持原样。
现场变化后必须重新采集，冻结快照只能用于诊断，不能作为执行授权或当前场景证明。

## 当前验收

- 官方 demo：两个任务、两种递归模式，0 失败。
- 接口测试：10 项通过，包含真正 Harness² 顺序递归流程的离线替身测试。
- 已使用真实 Kit 快照生成本地刷铁机交接单。
- 真实 Codex 迭代已通过：3 个编辑/合并阶段均收到并接受真实答复，另完成一次反思调用。结果见 `work/harness2-iron-farm-20261019/iteration-2/integration-validation.json`。
- 已采纳的六项诊断检查保存在 `work/harness2-adopted/iron-farm.json`，后续新任务自动复用；这不授权执行任何游戏动作。
- 本轮反思返回 `NO_ENTRY`，未将未经充分证明的通用经验写入经验库。
- 没有重启游戏、替换 Mod、移动角色或放置方块。

## 实机闭环与查看方式（2026-10-19）

平时可直接在 Codex 对话中交代施工目标。网页 `http://127.0.0.1:18768/` 是可选的透明记录入口，不需要在两个地方重复发任务。新增「Kit 实机采用与学习记录」展示发布策略、离线案例、历史实机验收、模型形成的经验及后续引用证据；旧版快照诊断单独标为历史记录。

实际动作仍由一个 Kit 控制器执行。`decision-runtime/harness_runtime.py` 读取已验证策略，产生与当前世界及任务绑定的短期计划，执行后写入本地回执。成功的封闭水源准备可进入学习队列；worker 在调用模型前复核完整原生回执和材料守恒，只发送最小化摘要。模型不能直接生成或执行任意游戏动作。无法处理的失败留给 Codex 修复，不自动重放。

`live_service.py` 是独立本地学习进程，使用独占锁，每小时最多处理两次学习尝试，失败不自动重试。它不负责施工、也不是开机自启。网页关闭不影响已启动进程；Codex 关闭也不等于获得新的施工授权。控制器源码的观察器改进在下次启动控制器时载入，不要求重启 Minecraft。

已验证一次实机应用：封闭水源 2→9、回收 4 块隔板、约 97.871 秒、52 次原生输入；保持水坝、诱饵入口和玩家满血。随后形成一条经验，后续真实模型请求已读取并引用。单次证据不证明速度提升、可重复性或实际产铁。
