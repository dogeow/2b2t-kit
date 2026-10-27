import Foundation

struct TranslationJob: Identifiable {
    let id = UUID()
    let request: TranslationRequest
    let prepareOnly: Bool
    let completion: (HTTPReply) -> Void
}

/// One view/session per language pair, rather than a new view for every chat line.
final class TranslationWorkerMailbox: Identifiable {
    let id = UUID()
    let source: String
    let target: String
    let jobs: AsyncStream<TranslationJob>
    let continuation: AsyncStream<TranslationJob>.Continuation
    init(source: String, target: String) {
        self.source = source; self.target = target
        var output: AsyncStream<TranslationJob>.Continuation!
        jobs = AsyncStream(bufferingPolicy: .bufferingNewest(1)) { output = $0 }
        continuation = output
    }
}
