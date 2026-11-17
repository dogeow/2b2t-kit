import SwiftUI
import Translation

struct LanguagePair: Hashable {
    let source: String
    let target: String

    init(source: String, target: String) {
        self.source = Locale.Language(identifier: source).minimalIdentifier
        self.target = Locale.Language(identifier: target).minimalIdentifier
    }

    var sourceLanguage: Locale.Language { Locale.Language(identifier: source) }
    var targetLanguage: Locale.Language { Locale.Language(identifier: target) }
    var convertsChineseScript: Bool {
        sourceLanguage.languageCode?.identifier == "zh" && targetLanguage.languageCode?.identifier == "zh"
            && sourceLanguage.script != targetLanguage.script
    }

    var label: String { "\(Self.name(source)) → \(Self.name(target))" }

    func availability(using availability: LanguageAvailability = LanguageAvailability()) async -> LanguageAvailability.Status {
        await availability.status(from: sourceLanguage, to: targetLanguage)
    }

    static let commonLanguages = ["en", "zh", "zh-TW", "ja", "ko", "fr", "de", "es", "it", "pt",
                                  "ru", "ar", "hi", "th", "vi", "id", "uk", "pl", "nl", "tr"]

    static func name(_ tag: String) -> String {
        let language = Locale.Language(identifier: tag)
        if language.languageCode?.identifier == "zh" {
            return language.script?.identifier == "Hant" ? "繁体中文" : "简体中文"
        }
        return Locale(identifier: "zh-Hans").localizedString(forIdentifier: tag) ?? tag
    }
}

struct LanguagePackDownload: Identifiable {
    let id = UUID()
    let pair: LanguagePair
}

struct LanguagePicker: View {
    let title: String
    @Binding var selection: String
    let languages: [String]

    var body: some View {
        Picker(title, selection: $selection) {
            ForEach(languages, id: \.self) { tag in
                Text(LanguagePair.name(tag)).tag(tag)
            }
        }.frame(maxWidth: 240)
    }
}

struct LanguagePackView: View {
    @ObservedObject var model: TranslatorModel
    @Binding var target: String
    @State private var systemLanguages: [String] = []
    @State private var rows: [PackRow] = []
    @State private var loadedTarget: String?
    @State private var refresh = 0

    private struct PackRow: Identifiable {
        let pair: LanguagePair
        let status: LanguageAvailability.Status
        var id: String { pair.source }
    }

    private struct RefreshKey: Equatable {
        let target: String
        let manual: Int
        let service: Int
    }

    private var languages: [String] {
        var tags = Set(LanguagePair.commonLanguages)
        tags.formUnion(systemLanguages)
        tags.insert(target)
        if let missing = model.missingPack {
            tags.insert(missing.source)
            tags.insert(missing.target)
        }
        return tags.sorted { LanguagePair.name($0).localizedStandardCompare(LanguagePair.name($1)) == .orderedAscending }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                LanguagePicker(title: "译文语言", selection: $target, languages: languages)
                Spacer()
                Button("刷新状态", systemImage: "arrow.clockwise") { refresh += 1 }
            }
            Text("切换游戏的翻译目标前，可在这里下载将要使用的语言包。")
                .font(.callout).foregroundStyle(.secondary)
            if loadedTarget == target {
                List(rows) { row in
                    HStack {
                        Text(LanguagePair.name(row.pair.source))
                        Spacer()
                        if model.packDownload?.pair == row.pair {
                            ProgressView().controlSize(.small)
                            Text("正在准备").foregroundStyle(.secondary)
                        } else if row.pair.convertsChineseScript {
                            Label("可直接转换", systemImage: "checkmark.circle").foregroundStyle(.secondary)
                        } else {
                            switch row.status {
                            case .installed:
                                Label("已就绪", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                            case .supported:
                                Text("未下载").foregroundStyle(.secondary)
                                Button("下载") { model.prepareLanguages(row.pair) }
                                    .disabled(model.packDownload != nil)
                                    .accessibilityLabel("下载\(LanguagePair.name(row.pair.source))语言包")
                            case .unsupported:
                                Text("系统不支持").foregroundStyle(.secondary)
                            @unknown default:
                                Text("状态未知").foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            } else {
                ProgressView("正在读取语言包状态…").frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            if !model.packDownloadNotice.isEmpty {
                Text(model.packDownloadNotice).font(.callout).textSelection(.enabled)
            }
        }
        .padding(16)
        .task(id: RefreshKey(target: target, manual: refresh, service: model.packRevision)) {
            await loadRows(for: target)
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            refresh += 1
        }
    }

    private func loadRows(for selectedTarget: String) async {
        let availability = LanguageAvailability()
        let supportedTags = await availability.supportedLanguages.map(\.minimalIdentifier)
        guard !Task.isCancelled else { return }
        systemLanguages = supportedTags
        let targetLanguage = Locale.Language(identifier: selectedTarget)
        var loaded: [PackRow] = []
        for source in languages {
            let pair = LanguagePair(source: source, target: selectedTarget)
            guard pair.sourceLanguage.maximalIdentifier != targetLanguage.maximalIdentifier else { continue }
            let status = pair.convertsChineseScript ? .installed : await pair.availability(using: availability)
            guard !Task.isCancelled else { return }
            loaded.append(PackRow(pair: pair, status: status))
        }
        if let missing = model.missingPack, let index = loaded.firstIndex(where: { $0.pair == missing }) {
            loaded.insert(loaded.remove(at: index), at: 0)
        }
        rows = loaded
        loadedTarget = selectedTarget
    }
}

struct LanguagePackPreparation: View {
    let download: LanguagePackDownload
    @ObservedObject var model: TranslatorModel

    var body: some View {
        Color.clear.frame(width: 1, height: 1)
            .translationTask(source: download.pair.sourceLanguage, target: download.pair.targetLanguage) { session in
                do {
                    try await session.prepareTranslation()
                    let installed = await download.pair.availability() == .installed
                    guard !Task.isCancelled else { return }
                    model.finishPreparation(download, installed: installed)
                } catch {
                    guard !Task.isCancelled else { return }
                    model.finishPreparation(download, installed: false,
                                            error: "语言包准备失败：\(error.localizedDescription)")
                }
            }
            .task {
                try? await Task.sleep(for: .seconds(300))
                guard !Task.isCancelled else { return }
                model.finishPreparation(download, installed: false)
            }
    }
}
