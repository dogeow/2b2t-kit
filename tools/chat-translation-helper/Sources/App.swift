import AppKit
import SwiftUI
import Translation

@MainActor final class TranslatorModel: ObservableObject {
    @Published var serverStatus = "正在启动本地服务…"
    @Published var listening = false
    var active: TranslationJob?
    @Published var workers: [TranslationWorkerMailbox] = []
    var queued = 0
    var translated = 0
    @Published var testInput = "Hello! Where is the nearest village?"
    @Published var testOutput = ""
    @Published var source = "en"
    @Published var target = "zh"
    @Published private(set) var missingPack: LanguagePair?
    @Published private(set) var packDownload: LanguagePackDownload?
    @Published private(set) var packDownloadNotice = ""
    @Published private(set) var packRevision = 0
    private var testID: String?
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
    private var installedPairs: Set<LanguagePair> = []

    func start() {
        guard server == nil else { return }
        activity = ProcessInfo.processInfo.beginActivity(options: .userInitiatedAllowingIdleSystemSleep,
                                                         reason: "Minecraft local chat translation service")
        let router = TranslationRequestRouter(diagnostics: diagnostics) { [weak self] request, completion in
            Task { @MainActor in
                guard let self else { completion(HTTPFailure(503, "unavailable", "Helper is unavailable.").reply); return }
                self.enqueue(request, completion: completion)
            }
        }
        server = LocalServer(onState: { [weak self] message, ready in
            Task { @MainActor in self?.serverStatus = message; self?.listening = ready }
        }, onRequest: router.handle)
        server?.start()
    }

    func enqueue(_ request: TranslationRequest, completion: @escaping (HTTPReply) -> Void) {
        // Preserve filtered messages immediately, even if the language worker is busy.
        if LanguageIdentity.preservesDeathMessage(request.text),
           let unchanged = LanguageIdentity.unchangedTranslation(for: request) {
            completion(.translated(unchanged))
            return
        }
        let resolved: TranslationRequest
        if request.from == "auto" {
            guard let source = LanguageIdentity.resolvedSource(for: request) else {
                completion(.translated(TranslationResult(translation: request.text, sourceLanguage: "und",
                                                        targetLanguage: request.to, id: request.id)))
                return
            }
            resolved = TranslationRequest(text: request.text, from: source, to: request.to, id: request.id)
        } else { resolved = request }
        let canonical = TranslationRequest(text: resolved.text,
                from: Locale.Language(identifier: resolved.from).minimalIdentifier,
                to: Locale.Language(identifier: resolved.to).minimalIdentifier, id: resolved.id)
        guard pending.count < 32 else { completion(HTTPFailure(429, "queue_full", "Translation queue is full; keep the original message.").reply); return }
        let job = TranslationJob(request: canonical, completion: completion)
        pending.append(job)
        deadlines[job.id] = Task { [weak self] in
            try? await Task.sleep(for: .seconds(25))
            guard !Task.isCancelled, let self else { return }
            self.finish(job.id, reply: HTTPFailure(504, "translation_timeout", "Translation timed out. Open the helper to check language models.").reply)
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
        if let unchanged = LanguageIdentity.chineseScriptTranslation(for: job.request) ?? LanguageIdentity.unchangedTranslation(for: job.request) {
            finish(job.id, reply: .translated(unchanged))
            return
        }
        let pair = LanguagePair(source: job.request.from, target: job.request.to)
        if installedPairs.contains(pair) {
            dispatch(job)
            return
        }
        Task { [weak self] in
            guard let self else { return }
            let availability = await pair.availability()
            guard self.active?.id == job.id else { return }
            switch availability {
            case .installed:
                self.installedPairs.insert(pair)
                if self.missingPack == pair {
                    self.missingPack = nil
                    self.packRevision += 1
                }
                self.dispatch(job)
            case .supported:
                if self.missingPack != pair {
                    self.missingPack = pair
                    self.packRevision += 1
                }
                self.finish(job.id, reply: HTTPFailure(503, "language_not_installed",
                    "未安装 \(pair.label) 语言包。请打开助手的「语言包管理」下载。").reply)
            case .unsupported:
                self.finish(job.id, reply: HTTPFailure(400, "unsupported_language_pair",
                    "当前 macOS 不支持 \(pair.label)。").reply)
            @unknown default:
                self.finish(job.id, reply: HTTPFailure(503, "language_unavailable", "无法获取语言包状态。").reply)
            }
        }
    }

    func finish(_ id: UUID, reply: HTTPReply) {
        let job: TranslationJob
        if let current = active, current.id == id {
            job = current; active = nil
            if reply.status != 200 {
                installedPairs.remove(LanguagePair(source: current.request.from, target: current.request.to))
                if let index = workers.firstIndex(where: { $0.source == current.request.from && $0.target == current.request.to }) {
                    workers[index].continuation.finish(); workers.remove(at: index)
                }
            }
        } else if let index = pending.firstIndex(where: { $0.id == id }) {
            job = pending.remove(at: index)
        } else { return }
        deadlines.removeValue(forKey: id)?.cancel()
        if reply.status == 200 {
            translated += 1
        } else {
            failedJobs += 1
            let body = (try? JSONSerialization.jsonObject(with: reply.body)) as? [String: Any]
            lastFailure = ["code": body?["error"] as? String ?? "unknown", "source": job.request.from, "target": job.request.to]
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

    func prepareLanguages(_ pair: LanguagePair) {
        guard packDownload == nil else { return }
        packDownloadNotice = "正在准备 \(pair.label)，请按 macOS 提示操作。"
        packDownload = LanguagePackDownload(pair: pair)
    }

    func finishPreparation(_ download: LanguagePackDownload, installed: Bool, error: String? = nil) {
        guard packDownload?.id == download.id else { return }
        packDownload = nil
        if installed {
            if missingPack == download.pair { missingPack = nil }
            packDownloadNotice = "\(download.pair.label) 已可翻译。"
        } else {
            packDownloadNotice = error ?? "请等待 macOS 完成下载，然后刷新语言包状态。"
        }
        packRevision += 1
    }

    func runTest() {
        let id = UUID().uuidString
        testID = id
        let request = TranslationRequest(text: testInput, from: source, to: target, id: id)
        do { try request.validate() }
        catch let failure as HTTPFailure { testOutput = failure.message; return }
        catch { return }
        testOutput = "正在翻译…"
        enqueue(request) { [weak self] reply in
            guard let self, self.testID == id else { return }
            if let response = try? JSONDecoder().decode(TranslationResult.self, from: reply.body) {
                self.testOutput = response.translation
            } else {
                let body = (try? JSONSerialization.jsonObject(with: reply.body)) as? [String: Any]
                self.testOutput = body?["message"] as? String ?? "翻译失败"
            }
        }
    }

    func resetTestOutput() {
        testID = nil
        testOutput = ""
    }
}

struct TranslationWorker: View {
    let mailbox: TranslationWorkerMailbox
    @ObservedObject var model: TranslatorModel
    private var configuration: TranslationSession.Configuration {
        .init(source: Locale.Language(identifier: mailbox.source), target: Locale.Language(identifier: mailbox.target))
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
                        let result = try await session.translate(job.request.text)
                        guard !Task.isCancelled else { return }
                        model.finish(job.id, reply: .translated(TranslationResult(translation: result.targetText, sourceLanguage: result.sourceLanguage.minimalIdentifier, targetLanguage: result.targetLanguage.minimalIdentifier, id: job.request.id)))
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
    @State private var tab = "packs"
    @State private var packTarget = "zh"

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
            if let pair = model.missingPack {
                HStack {
                    Label("最近缺少语言包：\(pair.label)", systemImage: "arrow.down.circle")
                    Spacer()
                    Button("查看语言包") {
                        packTarget = pair.target
                        tab = "packs"
                    }
                }.font(.callout)
            }
            TabView(selection: $tab) {
                LanguagePackView(model: model, target: $packTarget)
                    .tabItem { Label("语言包管理", systemImage: "arrow.down.circle") }.tag("packs")
                testPane
                    .tabItem { Label("翻译测试", systemImage: "text.bubble") }.tag("test")
            }
            .frame(height: 380)
        }
        .padding(24).frame(width: 650)
        .background(alignment: .topLeading) {
            ForEach(model.workers) { mailbox in TranslationWorker(mailbox: mailbox, model: model).id(mailbox.id) }
            if let download = model.packDownload {
                LanguagePackPreparation(download: download, model: model).id(download.id)
            }
        }
        .onChange(of: model.source) { model.resetTestOutput() }
        .onChange(of: model.target) { model.resetTestOutput() }
        .onReceive(Timer.publish(every: 1, on: .main, in: .common).autoconnect()) { _ in model.objectWillChange.send() }
    }
    private var testPane: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                LanguagePicker(title: "原文", selection: $model.source, languages: LanguagePair.commonLanguages)
                Image(systemName: "arrow.right")
                LanguagePicker(title: "译文", selection: $model.target, languages: LanguagePair.commonLanguages)
            }
            TextEditor(text: $model.testInput).font(.body).frame(height: 82)
                .padding(5).overlay(RoundedRectangle(cornerRadius: 6).stroke(.quaternary))
            Button("翻译测试") { model.runTest() }.buttonStyle(.borderedProminent)
                .disabled(model.testInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            ScrollView {
                Text(model.testOutput.isEmpty ? "译文会显示在这里" : model.testOutput)
                    .frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
            }
            .padding(10).background(.quaternary.opacity(0.35), in: RoundedRectangle(cornerRadius: 6))
            Text("测试语言只用于助手。游戏的翻译目标在 /mct 设置里选择。")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(16)
    }

}

@MainActor final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    let model = TranslatorModel()
    private var helperWindow: NSWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        model.start()
    }

    func attach(_ window: NSWindow) {
        helperWindow = window
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
        model.windowChanged(window)
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        sender.miniaturize(nil)
        model.windowChanged(sender)
        return false
    }
    func windowDidMiniaturize(_ notification: Notification) {
        if let window = notification.object as? NSWindow { model.windowChanged(window) }
    }
    func windowDidDeminiaturize(_ notification: Notification) {
        if let window = notification.object as? NSWindow { model.windowChanged(window) }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        guard let window = helperWindow ?? sender.windows.first else { return false }
        window.deminiaturize(nil); window.makeKeyAndOrderFront(nil); model.windowChanged(window)
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
    var body: some Scene {
        Window("Minecraft 双语翻译助手", id: "main") {
            ContentView(model: delegate.model).background(HelperWindowAttachment { window in
                delegate.attach(window)
            }.frame(width: 0, height: 0))
        }
            .windowResizability(.contentSize)
    }
}
