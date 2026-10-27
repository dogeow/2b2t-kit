# Minecraft 双语翻译助手（macOS）

使用 macOS 15 及以上自带的 Apple Translation 框架。随附 `.app` 为 Apple Silicon（arm64）构建。它仅监听 `127.0.0.1:8765`，为同一台 Mac 上的 Minecraft Fabric 客户端提供翻译。聊天内容不写入文件或日志，不需要 API Key。语言模型首次下载需要网络和用户确认；安装语言包后翻译在本机执行。

## 启动

1. 打开 `dist/Minecraft Bilingual Helper.app`。这是本机临时签名构建，不是经过 Apple 公证的发行版。
2. 选择常用原文语言（例如英语）与译文语言（默认简体中文），点击 **下载 / 准备语言包**，完成系统提示。
3. 点击 **翻译测试**，确认语言包可用。其他原文语言也应先在此准备。
4. 游玩时保持助手运行。关闭窗口只隐藏窗口，退出用 `⌘Q`。

界面语言选择只影响准备语言包和手动测试；每个游戏请求自行指定 `from` 和 `to`。游戏的默认设置为自动检测原文语言，译成简体中文，保留原文与译文。

含独立单词 `died` 的消息（忽略大小写，例如 `Steve died to polar bear`）直接返回原文，游戏不追加译文，也不调用语言包。`Diedrich` 等名字不会触发此规则。此规则可通过只更新助手生效，无需重启 Minecraft；已有聊天历史不变。

## 构建和检查

需要 macOS 15+ 与包含 macOS 15 SDK 的 Xcode Command Line Tools（`xcode-select --install`）。构建当前机器架构的 `.app`：

```sh
bash build.sh
bash test.sh
open "dist/Minecraft Bilingual Helper.app"
curl http://127.0.0.1:8765/health
curl --max-time 28 http://127.0.0.1:8765/translate \
  -H 'Content-Type: application/json' \
  --data '{"text":"Hello world!","from":"auto","to":"zh-Hans","id":"demo"}'
```

## HTTP 协议

- `GET /health`：监听正常返回 200。此状态表示服务存活，不保证任意语言模型已安装。
- `POST /translate`：JSON 请求 `{ "text": "Hello!", "from": "auto", "to": "zh-Hans", "id": "optional-string" }`。
- 成功返回 200：`{ "translation": "你好！", "sourceLanguage": "en", "targetLanguage": "zh-Hans", "id": "optional-string" }`。
- 错误返回相应 HTTP 状态与 `{ "error": "language_not_installed", "message": "…" }`。400 为无效输入或不支持语言，429 为队列满，503 为语言包未安装或系统翻译暂不可用，504 为超时。
- 每条输入最多 4096 字符 / 12288 UTF-8 字节，整个请求 body 最多 16 KB；最多 32 条等待翻译，最多 64 个连接。请求接收超时 5 秒，单条翻译包含排队共 25 秒。
- 仅接受 `Host: 127.0.0.1:8765`；拒绝 `Origin`、`Referer` 与 `Sec-Fetch-*` 请求头，不启用 CORS；不接受 chunked 编码、重复请求头、HTTP pipelining。Java HTTP 客户端应发送已知长度的 JSON body。
- 本机普通进程可调用此服务。服务并不是认证边界；不要用端口转发将它暴露到网络。

源语言与目标语言相同且文字系统相同时直接返回原文；自动检测由系统 NaturalLanguage 完成，不按字母或文字外观猜测语言。简体与繁体中文不会被当成同一种文字系统而直接跳过。语言对不受支持、语言包缺失或文本太短无法识别时可能失败；游戏应保留原文，不影响正常聊天。

实现使用 Apple 官方 [TranslationSession](https://developer.apple.com/documentation/translation/translationsession) 与 [translationTask](https://developer.apple.com/documentation/swiftui/view/translationtask(_:action:))。首次准备通过 `prepareTranslation()` 提供系统下载确认，网络翻译请求只处理已安装的语言对。

自动识别先解析源语言，再用同一语言对检查语言包和执行翻译，避免两次识别不一致。按用户偏好，自动识别限定为英语、简体中文与繁体中文；不确定时，含汉字的按中文处理，其余默认英语。其他语言须明确指定源语言。简繁转换直接在本机处理，不需要额外翻译语言包。简繁同形的中文片段按简体处理，含真实繁体字的消息仍保留繁体语言判断。`/health` 的 `lastError` 仅提供错误代码及源/目标语言，不包含聊天正文。
