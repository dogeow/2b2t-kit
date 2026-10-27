# Kit 聊天翻译与防刷屏

适用于 Minecraft Java **26.2 + Fabric**，已经集成到原 `2b2t-kit` 项目。使用 Apple Translation 本机翻译，不需要 API Key。macOS 翻译助手要求 macOS 15 及以上；本次构建为 Apple Silicon。

## 使用

1. 安装包含本功能的 Kit 主包并完整重启 Minecraft。主包包含界面和 Mixin，`/twob2tkit reload` 无法加载新增界面。
2. 打开 Kit 的 **设置 → 聊天翻译与防刷屏**（功能列表名称为“聊天翻译”），也可搜索“翻译”“mct”“按需”，或输入本地命令 **`/mct`**。
3. 点击 **启动翻译服务**；已运行时复用助手。需要准备语言包时点击 **打开助手 / 准备语言包**。助手关闭按钮会将窗口最小化，保持服务运行。

配置保存在当前游戏目录 `config/twob2tkit/chat-translation.json`，不改原有工程、路线与自动化配置。

开启 **按需翻译** 后，收到消息时不自动翻译。打开聊天界面，点击消息文字或旁边的 **[翻译]** 即可处理该条消息；原有链接继续保留原行为，可用旁边的按钮翻译。失败后可点 **[重试]**。本地命令 `/mct manual`、`/mct auto` 分别切换按需与自动模式，`/mct start` 启动服务。

包含独立单词 `died` 的消息按用户偏好保留原文，不添加翻译。自动检测不确定时按英语或中文处理。

默认显示：

```text
<Steve> Where is the nearest village?
↳ 最近的村庄在哪里？
```

原文先正常显示，译文完成后补入同一条聊天记录。保留原文的组件样式、点击事件、签名及消息删除行为。清空、删除、换服或关闭翻译之后，过期结果不会重新出现。翻译失败保留原文，错误提示每分钟最多一次。

## 防刷屏

- 默认开启，独立于翻译开关生效。
- 同一玩家在 **15 秒**固定窗口内连续发相同内容，第二次起隐藏重复消息并跳过翻译，第三次起本地屏蔽该玩家本次连接的全部后续消息。其他玩家插话不会清零该玩家的计数；该玩家发不同内容或超出窗口则重新计数。
- 检测忽略大小写、格式颜色、多余空白和零宽字符。玩家身份来自消息的玩家资料；只有服务器文本时，仅匹配玩家列表中已知名字的标准 `<name>` 或 `name: 内容` 格式。无法可靠识别作者的服务器通知不用于自动屏蔽。
- 自动服务器屏蔽只用普通玩家的个人忽略命令，不使用管理员的 mute/ban/kick。
- 服务器公开 `ignore add` 子命令时，优先使用添加语义；EssentialsX 的 `/ignore 玩家` 是切换语义，因此只在公开 `essentials:ignore`、查询名单并收到可识别的官方中/英文回复、确认尚未屏蔽时发送一次。
- 不支持、权限不足、未知回复或查询超时时，仍然本地屏蔽，并显示可点击填入的 `/ignore 玩家`。服务器成功与否以服务器回复为准。查询超时后本次连接不再重试查询，避免误用迟到结果。命令排队限 16 人，每 2 秒最多开始处理一人，每位玩家每次连接只自动尝试一次。
- `/mct unblock 玩家` 或设置页“清空本地屏蔽记录”可解除本地屏蔽；服务器忽略名单按服务器说明手动解除。重新连接会清空本地会话屏蔽。

阈值、时间窗口、翻译开关、双语显示、目标语言、插件消息和自身消息均可在 Kit 设置页调整。默认翻译成简体中文，保留原文；自己的消息默认不重复翻译。

## 发出消息

“翻译后发送”默认关闭。打开后，含中文的普通聊天先翻译为所选目标语言（默认英语），再按输入顺序发送；斜杠命令不翻译。发送失败或因设置变化被取消时，不偷偷发送原文，会提示点击恢复原输入。换服后不发送旧连接中的内容。

也可用 `/mct translate 中文内容` 先看英语预览，点击填入输入框后自行发送。

## 验证记录

- Kit Java 25 / Minecraft 26.2 完整 `test jar verifyRuntimeEngineJar --offline`：2093 项测试，零失败。
- 翻译核心包含真实本地 HTTP 模拟测试：队列、缓存、去重、超时、断连、响应大小、显式直连、不跟随重定向与独立健康检查。
- 防刷屏测试覆盖连续重复、交错玩家、计时窗口、格式变化、解封、会话清理、容量上限和忽略名单的严格解析。
- 使用编译后的 Kit Java 客户端连接真实助手，中英双向均成功。
- 最终 macOS 助手已完成原生界面和真实 Apple 翻译测试，语言包缺失时保留原文并提示准备，不自动弹下载窗口。
- 尚未在重启后的真实游戏会话中验证新增界面与 Mixin，以及当前服务器的忽略命令返回。正在运行的旧 JVM 无法热加载本次主包改动。

助手只监听 `127.0.0.1:8765`。聊天不写入助手日志，模型下载完成后翻译在本机执行。Java 队列最多 64 个请求，缓存最多 256 条；请求超时 12 秒、含排队最长 20 秒，避免刷屏拖积过时消息。

## 源码与构建

功能源码已合入原项目 `2b2t-kit/src/client/java/dev/twob2tkit/chat`；助手源码在原项目 `tools/chat-translation-helper`。附带 `kit-chat-translation.patch` 便于审阅本次改动。

Kit 使用原项目构建命令。助手可执行 `bash helper/build.sh` 与 `bash helper/test.sh` 重建及测试。

参考：[Apple Translation](https://developer.apple.com/documentation/translation)、[Fabric 26.2 消息事件](https://github.com/FabricMC/fabric/blob/26.2/fabric-message-api-v1/src/client/java/net/fabricmc/fabric/api/client/message/v1/ClientReceiveMessageEvents.java)、[EssentialsX ignore 实现](https://github.com/EssentialsX/Essentials/blob/2.x/Essentials/src/main/java/com/earth2me/essentials/commands/Commandignore.java)。
