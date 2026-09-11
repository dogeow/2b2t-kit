# Minecraft 本地事件调度

平时不调用模型；状态变化先交给规则。未知故障唤起 GPT-5.3-Codex-Spark，复杂故障进入桌面 Codex 事件队列，目标是用户指定的现有任务。独立 CLI 主模型路径已停用。Grok 当前额度已耗尽，这版不自动改走付费 xAI API。

当前版本完成“发现异常 → 去重与过滤 → Spark 诊断 → 桌面待投递队列 / 事件收件箱”。桌面实际投递由单独开关控制，启用前需要完成用户批准的连接验收。它保持只读：现有 Kit 继续负责动作和保命，调度层不会依据模型文本直接重启任务、挖方块、取箱子、发服务器聊天或热换代码。自动执行模型建议还需要任务授权和可撤销动作协议，不能把本版称为全自动游戏伙伴。

## 运行

```sh
python3 install.py
python3 companion.py status --state-dir "$HOME/Library/Application Support/MinecraftCompanion"
python3 companion.py pause --state-dir "$HOME/Library/Application Support/MinecraftCompanion"
python3 companion.py resume --state-dir "$HOME/Library/Application Support/MinecraftCompanion"
```

安装后登录 macOS 自动运行。`pause` 暂停派发并取消待处理请求；已经开始的只读模型分析可能完成，但不会再升级，也不会控制游戏。

## 事件处理

- macOS kqueue 监听 Kit 状态目录和挖矿日志目录，已有状态心跳约每秒一次。检测延迟通常受这个心跳频率限制。
- 建造、混凝土制作、砍树、导航的结束或无进展，以及挖矿日志中的停止/部分故障会生成结构化事件。
- 缺料、手动停止、完成、断线和危险由规则分类，零模型调用。危险仍由游戏内防护处理，不等外部分析。
- 相同故障与现场去重。每小时默认最多 4 次 Spark、1 次桌面 Codex 唤醒；模型错误后退避 1 小时，不循环刷额度。额度可在 config.json 修改。
- 新进程不会重放启动前的旧日志；崩溃时未确认完成的模型请求不自动重试。事件存入 SQLite，保留诊断证据。
- 只把有限的任务状态送给模型，不发送公共聊天、箱子内容、账户文件或完整日志。

## 文件

运行目录：`~/Library/Application Support/MinecraftCompanion/`

- `service-status.json`：服务心跳、队列和本小时模型调用数。
- `inbox.md` / `inbox.json`：诊断收件箱。
- `events.jsonl` / `events.sqlite3`：事件与去重记录。
- `decisions.jsonl`：规则/模型结果与 Token 用量。
- `config.json`：模型、调用限额、心跳位置。

Spark 通过本地 stdio Codex App Server 按事件发起短会话，空闲不运行推理。复杂异常通过当前 App 的本机 IPC 交给指定桌面任务，作为非用户指令的外部数据，沿用任务的模型和工具权限。适配器固定当前 App 版本；版本不符、目标任务不可用或结果不确定时保留队列，不降级为可信用户文本，也不改用 CLI 主模型。桌面任务忙时等待，投递结果不确定时不自动重试。普通 ChatGPT 聊天区不接入这条自动链路。

## 验证

`python3 -m unittest discover -v` 检查故障分流、去重、暂停、旧事件、迟到现场、调用上限以及 Spark 到主模型的分派。模型端到端验证使用隔离的事件回放，不修改玩家世界。
