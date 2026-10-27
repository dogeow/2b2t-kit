import AppKit
import SwiftUI
import Translation

@MainActor final class TranslatorModel: ObservableObject {
    @Published var serverStatus = "正在启动本地服务…"
    @Published var listening = false
    var status = "先选择语言并下载语言包，再开始游戏。"
    var active: TranslationJob?
    @Published var workers: [TranslationWorkerMailbox] = []
    var queued = 0
    var translated = 0
    @Published var testInput = "Hello! Where is the nearest village?"
    @Published var testOutput = ""
    @Published var source = "en"
    @Published var target = "zh-Hans"
    @Published var preparing = false
    private var pending: [TranslationJob] = []
    private var deadlines: [UUID: Task<Void, Never>] = [:]
    private var server: LocalServer?
    private var lastFailure: [String: String] = [:]
    private let diagnostics = ServiceDiagnostics()
    private var activity: NSObjectProtocol?
    private var sessionCreations = 0
    private var sessionStarts = 0
    private var sessionStops = 0
    private var failedJobs = 0
    private var windowState: [String: Bool] = [:]
    private var installedPairs: Set<String> = []

    func start() {
        guard server == nil else { return }
        activity = ProcessInfo.processInfo.beginActivity(options: .userInitiatedAllowingIdleSystemSleep,
                                                         reason: "Minecraft local chat translation service")
        let router = TranslationRequestRouter(diagnostics: diagnostics) { [weak self] request, completion in
            Task { @MainActor in
                guard let self else { completion(HTTPFailure(503, "unavailable", "Helper is unavailable.").reply); return }
                self.enqueue(request, prepareOnly: false, completion: completion)
            }
        }
        server = LocalServer(onState: { [weak self] message, ready in
            Task { @MainActor in self?.serverStatus = message; self?.listening = ready }
        }, onRequest: router.handle)
        server?.start()
    }

    func enqueue(_ request: TranslationRequest, prepareOnly: Bool, completion: @escaping (HTTPReply) -> Void) {
        // Preserve filtered messages immediately, even if the language worker is busy.
        if !prepareOnly, LanguageIdentity.preservesDeathMessage(request.text),
           let unchanged = LanguageIdentity.unchangedTranslation(for: request) {
            completion(.translated(unchanged))
            return
        }
        let resolved: TranslationRequest
        if !prepareOnly, request.from == "auto" {
            guard let source = LanguageIdentity.resolvedSource(for: request) else {
                completion(.translated(TranslationResult(translation: request.text, sourceLanguage: "und",
                                                        targetLanguage: request.to, id: request.id)))
                return
            }
            resolved = TranslationRequest(text: request.text, from: source, to: request.to, id: request.id)
        } else { resolved = request }
        let canonical = TranslationRequest(text: resolved.text,
                from: resolved.from == "auto" ? "auto" : Locale.Language(identifier: resolved.from).minimalIdentifier,
                to: Locale.Language(identifier: resolved.to).minimalIdentifier, id: resolved.id)
        guard pending.count < 32 else { completion(HTTPFailure(429, "queue_full", "Translation queue is full; keep the original message.").reply); return }
        let job = TranslationJob(request: canonical, prepareOnly: prepareOnly, completion: completion)
        pending.append(job)
        deadlines[job.id] = Task { [weak self] in
            try? await Task.sleep(for: .seconds(prepareOnly ? 300 : 25))
            guard !Task.isCancelled, let self else { return }
            self.finish(job.id, reply: HTTPFailure(504, "translation_timeout", prepareOnly ? "Language preparation timed out. Try again in the helper." : "Translation timed out. Open the helper to check language models.").reply)
        }
        advance()
    }

    private func advance() {
        queued = pending.count
        publishDiagnostics()
        guard active == nil, !pending.isEmpty else { return }
        let job = pending.removeFirst()
        active = job
        queued = pending.count
        publishDiagnostics()
        if job.prepareOnly {
            status = "正在准备语言包，请完成系统提示…"
            dispatch(job)
        } else {
            if let unchanged = LanguageIdentity.chineseScriptTranslation(for: job.request) ?? LanguageIdentity.unchangedTranslation(for: job.request) {
                finish(job.id, reply: .translated(unchanged))
                return
            }
            let pair = job.request.from + "→" + job.request.to
            if installedPairs.contains(pair) {
                status = "正在翻译…"
                dispatch(job)
                return
            }
            status = "正在检查语言包…"
            // Gate before mounting translationTask: constructing its session may
            // initiate framework preparation even before the action is invoked.
            Task { [weak self] in
                guard let self else { return }
                do {
                    let availability = LanguageAvailability()
                    let target = Locale.Language(identifier: job.request.to)
                    let status: LanguageAvailability.Status
                    if job.request.from == "auto" {
                        status = try await availability.status(for: job.request.text, to: target)
                    } else {
                        status = await availability.status(from: Locale.Language(identifier: job.request.from), to: target)
                    }
                    guard self.active?.id == job.id else { return }
                    switch status {
                    case .installed:
                        self.installedPairs.insert(pair)
                        self.status = "正在翻译…"
                        self.dispatch(job)
                    case .supported:
                        throw HTTPFailure(503, "language_not_installed", "未安装 \(job.request.from) → \(job.request.to) 语言包；请在助手中准备此语言对。")
                    case .unsupported:
                        throw HTTPFailure(400, "unsupported_language_pair", "Apple Translation 不支持这组语言，或原文已经是目标语言。")
                    @unknown default:
                        throw HTTPFailure(503, "language_unavailable", "Language availability is unknown.")
                    }
                } catch let failure as HTTPFailure {
                    self.finish(job.id, reply: failure.reply)
                } catch {
                    self.finish(job.id, reply: HTTPFailure(503, "language_check_failed", error.localizedDescription).reply)
                }
            }
        }
    }

    func finish(_ id: UUID, reply: HTTPReply) {
        let job: TranslationJob
        if let current = active, current.id == id {
            job = current; active = nil
            if reply.status != 200 {
                installedPairs.remove(current.request.from + "→" + current.request.to)
                if let index = workers.firstIndex(where: { $0.source == current.request.from && $0.target == current.request.to }) {
                    workers[index].continuation.finish(); workers.remove(at: index)
                }
            }
        } else if let index = pending.firstIndex(where: { $0.id == id }) {
            job = pending.remove(at: index)
        } else { return }
        deadlines.removeValue(forKey: id)?.cancel()
        if reply.status == 200 {
            if job.prepareOnly { status = "语言包已就绪，可以开始游戏。" }
            else { translated += 1; status = "翻译服务正常" }
        } else {
            failedJobs += 1
            let body = (try? JSONSerialization.jsonObject(with: reply.body)) as? [String: Any]
            lastFailure = ["code": body?["error"] as? String ?? "unknown", "source": job.request.from, "target": job.request.to]
            status = "\(body?["message"] as? String ?? "翻译失败")"
        }
        publishDiagnostics()
        job.completion(reply)
        // The next job reuses the healthy language-pair session.
        Task { @MainActor [weak self] in
            await Task.yield()
            self?.advance()
        }
    }

    private func publishDiagnostics() {
        diagnostics.update(busy: active != nil, queued: pending.count, lastError: lastFailure, sessions: sessionCreations,
                           starts: sessionStarts, completed: translated, failed: failedJobs,
                           stops: sessionStops, window: windowState)
    }

    func workerDidStart() { sessionStarts += 1; publishDiagnostics() }
    func workerDidStop() { sessionStops += 1; publishDiagnostics() }
    func windowChanged(_ window: NSWindow) {
        windowState = ["exists": true, "visible": window.isVisible, "miniaturized": window.isMiniaturized]
        publishDiagnostics()
    }

    private func dispatch(_ job: TranslationJob) {
        var mailbox = workers.first { $0.source == job.request.from && $0.target == job.request.to }
        if mailbox == nil {
            if workers.count >= 4 { workers.removeFirst().continuation.finish() }
            let created = TranslationWorkerMailbox(source: job.request.from, target: job.request.to)
            workers.append(created); mailbox = created; sessionCreations += 1
        }
        publishDiagnostics()
        mailbox?.continuation.yield(job)
    }

    func prepareLanguages() {
        guard !preparing else { return }
        preparing = true
        enqueue(TranslationRequest(text: "Language preparation", from: source, to: target, id: nil), prepareOnly: true) { [weak self] _ in
            self?.preparing = false
        }
    }

    func runTest() {
        let request = TranslationRequest(text: testInput, from: source, to: target, id: "manual-test")
        do { try request.validate() }
        catch let failure as HTTPFailure { testOutput = failure.message; return }
        catch { return }
        testOutput = "正在翻译…"
        enqueue(request, prepareOnly: false) { [weak self] reply in
            if let response = try? JSONDecoder().decode(TranslationResult.self, from: reply.body) {
                self?.testOutput = response.translation
            } else {
                let body = (try? JSONSerialization.jsonObject(with: reply.body)) as? [String: Any]
                self?.testOutput = body?["message"] as? String ?? "翻译失败"
            }
        }
    }
}

struct TranslationWorker: View {
    let mailbox: TranslationWorkerMailbox
    @ObservedObject var model: TranslatorModel
    private var configuration: TranslationSession.Configuration {
        .init(source: mailbox.source == "auto" ? nil : Locale.Language(identifier: mailbox.source), target: Locale.Language(identifier: mailbox.target))
    }
    var body: some View {
        Color.clear.frame(width: 1, height: 1)
            .translationTask(configuration) { session in
                model.workerDidStart()
                defer { model.workerDidStop() }
                for await job in mailbox.jobs {
                    guard !Task.isCancelled else { return }
                    guard model.active?.id == job.id else { continue }
                    do {
                        if job.prepareOnly {
                            try await session.prepareTranslation()
                            guard !Task.isCancelled else { return }
                            model.finish(job.id, reply: .json(200, ["status": "prepared"]))
                        } else {
                            let result = try await session.translate(job.request.text)
                            guard !Task.isCancelled else { return }
                            model.finish(job.id, reply: .translated(TranslationResult(translation: result.targetText, sourceLanguage: result.sourceLanguage.minimalIdentifier, targetLanguage: result.targetLanguage.minimalIdentifier, id: job.request.id)))
                        }
                    } catch is CancellationError {
                        return
                    } catch {
                        model.finish(job.id, reply: HTTPFailure(503, "translation_failed", error.localizedDescription).reply)
                        return
                    }
                }
            }
    }
}

struct ContentView: View {
    @ObservedObject var model: TranslatorModel
    let languages = [("en", "英语"), ("zh-Hans", "简体中文"), ("zh-Hant", "繁体中文"), ("ja", "日语"), ("ko", "韩语"), ("fr", "法语"), ("de", "德语"), ("es", "西班牙语"), ("it", "意大利语"), ("pt", "葡萄牙语"), ("ru", "俄语"), ("ar", "阿拉伯语"), ("hi", "印地语"), ("th", "泰语"), ("vi", "越南语"), ("id", "印度尼西亚语"), ("uk", "乌克兰语"), ("pl", "波兰语"), ("nl", "荷兰语"), ("tr", "土耳其语")]
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(spacing: 12) {
                Image(systemName: "character.bubble.fill").font(.system(size: 35)).foregroundStyle(.green)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Minecraft 双语翻译助手").font(.title2.bold())
                    Text("Apple Translation · 本机翻译 · 无需 API Key").foregroundStyle(.secondary)
                }
                Spacer()
                Circle().fill(model.listening ? .green : .orange).frame(width: 9, height: 9)
            }
            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    Text(model.serverStatus).font(.system(.body, design: .monospaced)).textSelection(.enabled)
                    Text("游戏默认显示原文和译文。关闭窗口会最小化到 Dock，让本地翻译继续运行；退出请按 ⌘Q。")
                        .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    HStack { Label("已翻译 \(model.translated) 条", systemImage: "checkmark.bubble"); Spacer(); Text("等待：\(model.queued)") }.font(.caption).foregroundStyle(.secondary)
                }.padding(8)
            }
            HStack {
                Picker("原文", selection: $model.source) { ForEach(languages, id: \.0) { Text($0.1).tag($0.0) } }.frame(width: 225)
                Image(systemName: "arrow.right")
                Picker("译文", selection: $model.target) { ForEach(languages, id: \.0) { Text($0.1).tag($0.0) } }.frame(width: 225)
            }
            HStack {
                Button(model.preparing ? "正在准备…" : "下载 / 准备语言包") { model.prepareLanguages() }
                    .disabled(model.preparing || model.source == model.target)
                Text("首次下载需联网；已安装语言包可在本机翻译。")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text(model.status).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading).fixedSize(horizontal: false, vertical: true)
            Divider()
            Text("手动测试").font(.headline)
            TextEditor(text: $model.testInput).font(.body).frame(height: 72).padding(5).overlay(RoundedRectangle(cornerRadius: 6).stroke(.quaternary))
            HStack {
                Button("翻译测试") { model.runTest() }.buttonStyle(.borderedProminent).disabled(model.testInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Spacer()
                Text("游戏请求使用自己的语言设置，默认自动检测 → 简体中文。")
                    .font(.caption).foregroundStyle(.secondary)
            }
            ScrollView { Text(model.testOutput.isEmpty ? "译文会显示在这里" : model.testOutput).frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled) }
                .frame(minHeight: 55, maxHeight: 90).padding(10).background(.quaternary.opacity(0.35), in: RoundedRectangle(cornerRadius: 6))
            Text("聊天内容不写入日志；HTTP 仅接受本机 127.0.0.1 的非浏览器请求。支持的语言以系统实际可用情况为准。")
                .font(.caption).foregroundStyle(.tertiary).fixedSize(horizontal: false, vertical: true)
        }
        .padding(24).frame(width: 650)
        .background(alignment: .topLeading) {
            ForEach(model.workers) { mailbox in TranslationWorker(mailbox: mailbox, model: model).id(mailbox.id) }
        }
        .onAppear { model.start() }
        .onReceive(Timer.publish(every: 1, on: .main, in: .common).autoconnect()) { _ in model.objectWillChange.send() }
    }
}

@MainActor final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private var helperWindow: NSWindow?
    private weak var model: TranslatorModel?

    func attach(_ window: NSWindow, model: TranslatorModel) {
        helperWindow = window; self.model = model
        window.isReleasedWhenClosed = false
        window.delegate = self
        if let close = window.standardWindowButton(.closeButton) {
            close.target = self; close.action = #selector(minimizeServiceWindow(_:))
        }
        model.windowChanged(window)
    }
    @objc private func minimizeServiceWindow(_ sender: Any?) {
        guard let window = helperWindow else { return }
        window.miniaturize(nil)
        model?.windowChanged(window)
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        sender.miniaturize(nil)
        model?.windowChanged(sender)
        return false
    }
    func windowDidMiniaturize(_ notification: Notification) {
        if let window = notification.object as? NSWindow { model?.windowChanged(window) }
    }
    func windowDidDeminiaturize(_ notification: Notification) {
        if let window = notification.object as? NSWindow { model?.windowChanged(window) }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        guard let window = helperWindow ?? sender.windows.first else { return false }
        window.deminiaturize(nil); window.makeKeyAndOrderFront(nil); model?.windowChanged(window)
        return true
    }
}

private struct HelperWindowAttachment: NSViewRepresentable {
    let connect: (NSWindow) -> Void
    final class AttachmentView: NSView {
        var connect: ((NSWindow) -> Void)?
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            if let window { connect?(window) }
        }
    }
    func makeNSView(context: Context) -> AttachmentView {
        let view = AttachmentView(); view.connect = connect; return view
    }
    func updateNSView(_ view: AttachmentView, context: Context) {
        view.connect = connect
        if let window = view.window { connect(window) }
    }
}

@main struct MinecraftTranslationHelperApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var model = TranslatorModel()
    var body: some Scene {
        Window("Minecraft 双语翻译助手", id: "main") {
            ContentView(model: model).background(HelperWindowAttachment { window in
                delegate.attach(window, model: model)
            }.frame(width: 0, height: 0))
        }
            .windowResizability(.contentSize)
    }
}
