import Foundation

var passed = 0
func check(_ condition: @autoclosure () -> Bool, _ name: String) {
    guard condition() else { fatalError("FAIL: \(name)") }
    passed += 1
}
func wire(_ body: String, headers: String = "", length: String? = nil, host: String = "127.0.0.1:8765") -> Data {
    Data("POST /translate HTTP/1.1\r\nHost: \(host)\r\nContent-Type: application/json\r\nContent-Length: \(length ?? String(body.utf8.count))\r\n\(headers)\r\n\(body)".utf8)
}
func rejects(_ data: Data, status: Int, _ name: String) {
    do { _ = try HTTPParser.parse(data, port: 8765); fatalError("FAIL: accepted \(name)") }
    catch let error as HTTPFailure { check(error.status == status, "\(name): status \(error.status)") }
    catch { fatalError("FAIL: unexpected error \(name): \(error)") }
}
let body = #"{"text":"Hello 世界 👋","from":"auto","to":"zh-Hans","id":"chat-7"}"#
if case .translate(let request)? = try HTTPParser.parse(wire(body), port: 8765) {
    check(request.text == "Hello 世界 👋" && request.id == "chat-7", "UTF-8 JSON round trip")
} else { fatalError("Expected translation") }
let complete = wire(body)
for prefix in [1, 30, complete.count - 1] {
    let parsed = try HTTPParser.parse(Data(complete.prefix(prefix)), port: 8765)
    check(parsed == nil, "fragmented request \(prefix)")
}
if case .health? = try HTTPParser.parse(Data("GET /health HTTP/1.1\r\nHost: 127.0.0.1:8765\r\n\r\n".utf8), port: 8765) { passed += 1 }
else { fatalError("Expected health") }
rejects(wire(body, headers: "Origin: https://evil.example\r\n"), status: 403, "cross-origin request")
rejects(wire(body, headers: "Origin: null\r\n"), status: 403, "opaque-origin request")
rejects(wire(body, headers: "Sec-Fetch-Site: none\r\n"), status: 403, "browser request")
rejects(wire(body, host: "rebind.example:8765"), status: 403, "DNS rebinding host")
rejects(wire(body, headers: "Content-Length: 5\r\n"), status: 400, "duplicate length")
rejects(wire(body, headers: "Transfer-Encoding: chunked\r\n"), status: 400, "chunked body")
rejects(wire(body, length: "-1"), status: 400, "negative length")
rejects(wire(body, length: "16385"), status: 413, "oversized body")
rejects(wire(body) + Data("GET /health HTTP/1.1\r\n\r\n".utf8), status: 400, "pipelining")
rejects(wire(#"{"text":" ","from":"auto","to":"zh-Hans"}"#), status: 400, "empty text")
rejects(wire(#"{"text":"hi","from":"../../en","to":"zh-Hans"}"#), status: 400, "invalid language tag")
rejects(wire(#"{"text":"hi","from":"auto","to":"auto"}"#), status: 400, "automatic target")
rejects(wire("{broken"), status: 400, "invalid JSON")
rejects(Data(repeating: 65, count: 8193), status: 413, "oversized headers")
let result = TranslationResult(translation: "你好 👋", sourceLanguage: "en", targetLanguage: "zh-Hans", id: "7")
let reply = HTTPReply.translated(result)
let decoded = try JSONDecoder().decode(TranslationResult.self, from: reply.body)
check(decoded.translation == result.translation && decoded.id == "7", "JSON response contract")
let responseText = String(decoding: reply.encoded, as: UTF8.self)
check(responseText.contains("Content-Length: \(reply.body.count)\r\n"), "response UTF-8 content length")
check(responseText.contains("Connection: close\r\n") && !responseText.contains("Access-Control-Allow-Origin"), "response close and no CORS")
func identity(_ text: String, _ from: String, _ to: String) -> TranslationResult? {
    LanguageIdentity.unchangedTranslation(for: TranslationRequest(text: text, from: from, to: to, id: "identity"))
}
let unchanged = identity("Hello there!", "en", "en")
check(unchanged?.translation == "Hello there!" && unchanged?.id == "identity", "explicit same language preserves original and id")
check(identity("Hello there!", "en-US", "en-GB") != nil, "English region variants")
check(identity("Hello there!", "EN-us", "en") != nil, "case normalization")
check(identity("Hello! Where is the nearest village?", "auto", "en") != nil, "auto English same language")
check(identity("Hola, ¿dónde está el pueblo más cercano?", "es", "en") == nil, "explicit Spanish stays authoritative")
check(identity("Привет, где находится ближайшая деревня?", "ru", "en") == nil, "explicit Russian stays authoritative")
check(identity("我们一起探索村庄吧。", "zh-Hans", "zh-Hant") == nil, "explicit simplified to traditional is not an identity")
check(identity("我們一起探索村莊吧。", "zh-TW", "zh-CN") == nil, "Chinese region scripts remain distinct")
check(identity("我們一起探索村莊吧。", "auto", "zh-Hans") == nil, "auto traditional to simplified is not an identity")
check(identity("你好，朋友。", "zh-CN", "zh-Hans") != nil, "same Chinese script aliases")
check(identity("Dobar dan.", "sr-Latn", "sr-Cyrl") == nil, "other writing systems remain distinct")
for text in ["11KatriWon died", "BBblock225 died to polar bear", "forRealChicken died", "Steve DIED.", "[died]", "玩家 died！"] {
    let preserved = identity(text, "auto", "zh-Hans")
    check(preserved?.translation == text && preserved?.id == "identity", "death message preserves original and id: \(text)")
}
for text in ["Diedrich found a village", "undied", "died_player", "player_died", "died123", "你好died世界"] {
    check(!LanguageIdentity.preservesDeathMessage(text), "do not filter substrings: \(text)")
}
check(identity("The iron farm needs three villagers.", "en", "zh-Hans") == nil, "ordinary English still needs translation")
check(LanguageIdentity.resolvedSource(for: TranslationRequest(text: "你好", from: "auto", to: "en", id: nil)) == "zh-Hans", "shared Han glyphs use Simplified source")
check(LanguageIdentity.resolvedSource(for: TranslationRequest(text: "我們一起探索村莊吧。", from: "auto", to: "en", id: nil)) == "zh-Hant", "real Traditional glyphs retain their writing system")
for text in ["hi", "GG", "lol"] {
    check(LanguageIdentity.resolvedSource(for: TranslationRequest(text: text, from: "auto", to: "zh-Hans", id: nil)) == "en", "ambiguous short Latin fragment defaults to English: \(text)")
}
check(LanguageIdentity.resolvedSource(for: TranslationRequest(text: "hi", from: "en", to: "zh-Hans", id: nil)) == "en", "explicit short-message language remains authoritative")
for text in ["A faluban sok ember él.", "Witaj na serwerze Minecraft.", "Hello friend"] {
    check(LanguageIdentity.resolvedSource(for: TranslationRequest(text: text, from: "auto", to: "zh-Hans", id: nil)) == "en", "automatic mode follows English/Chinese-only user preference: \(text)")
}
let scriptResult = LanguageIdentity.chineseScriptTranslation(for: TranslationRequest(text: "我們一起探索村莊吧。", from: "zh-Hant", to: "zh-Hans", id: "script"))
check(scriptResult?.translation == "我们一起探索村庄吧。" && scriptResult?.id == "script", "Chinese script conversion needs no extra language pair")
// A held translation must not prevent health responses on the network queue.
// The main test thread deliberately waits synchronously, as a busy UI might.
let ready = DispatchSemaphore(value: 0)
let translationSeen = DispatchSemaphore(value: 0)
let responseSeen = DispatchSemaphore(value: 0)
let diagnostics = ServiceDiagnostics()
let router = TranslationRequestRouter(diagnostics: diagnostics) { _, _ in translationSeen.signal() }
let testPort = UInt16.random(in: 20000...60000)
let local = LocalServer(port: testPort, onState: { _, isReady in if isReady { ready.signal() } }, onRequest: router.handle)
local.start()
check(ready.wait(timeout: .now() + 5) == .success, "test listener ready")
let session = URLSession(configuration: .ephemeral)
var translationRequest = URLRequest(url: URL(string: "http://127.0.0.1:\(testPort)/translate")!)
translationRequest.httpMethod = "POST"
translationRequest.httpBody = Data(#"{"text":"hello world","from":"en","to":"zh-Hans"}"#.utf8)
translationRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
let heldTask = session.dataTask(with: translationRequest) { _, _, _ in }
heldTask.resume()
check(translationSeen.wait(timeout: .now() + 3) == .success, "translation dispatched and intentionally held")
var healthStatus = 0
session.dataTask(with: URL(string: "http://127.0.0.1:\(testPort)/health")!) { _, response, _ in
    healthStatus = (response as? HTTPURLResponse)?.statusCode ?? 0
    responseSeen.signal()
}.resume()
check(responseSeen.wait(timeout: .now() + 2) == .success && healthStatus == 200, "health stays responsive while translation and main thread are held")
heldTask.cancel(); session.invalidateAndCancel(); local.stop()
print("PASS: \(passed) protocol, language and independent health checks")
