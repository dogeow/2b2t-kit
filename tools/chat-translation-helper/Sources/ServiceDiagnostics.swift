import Foundation

/// The HTTP listener can answer health requests even when AppKit is busy.
final class ServiceDiagnostics {
    private let lock = NSLock()
    private var state: [String: Any] = [
        "status": "ok", "service": "Minecraft Bilingual Helper", "version": "1.0.4",
        "engine": "Apple Translation", "autoLanguagePolicy": "english_chinese",
        "requiresLanguagePreparation": true, "busy": false, "queueDepth": 0,
        "lastError": [String: String](), "sessionCreations": 0, "sessionStarts": 0,
        "completedJobs": 0, "failedJobs": 0
    ]

    func update(busy: Bool, queued: Int, lastError: [String: String], sessions: Int,
                starts: Int = 0, completed: Int = 0, failed: Int = 0,
                stops: Int = 0, window: [String: Bool] = [:]) {
        lock.lock(); defer { lock.unlock() }
        state["busy"] = busy; state["queueDepth"] = queued
        state["lastError"] = lastError; state["sessionCreations"] = sessions
        state["sessionStarts"] = starts; state["completedJobs"] = completed; state["failedJobs"] = failed
        state["sessionStops"] = stops; state["window"] = window
        state["progressAt"] = Int(Date().timeIntervalSince1970 * 1000)
    }

    func reply() -> HTTPReply {
        lock.lock(); let snapshot = state; lock.unlock()
        return .json(200, snapshot)
    }
}

final class TranslationRequestRouter {
    let diagnostics: ServiceDiagnostics
    let translate: (TranslationRequest, @escaping (HTTPReply) -> Void) -> Void
    init(diagnostics: ServiceDiagnostics, translate: @escaping (TranslationRequest, @escaping (HTTPReply) -> Void) -> Void) {
        self.diagnostics = diagnostics; self.translate = translate
    }
    func handle(_ request: ParsedRequest, completion: @escaping (HTTPReply) -> Void) {
        switch request {
        case .health: completion(diagnostics.reply())
        case .translate(let request): translate(request, completion)
        }
    }
}
