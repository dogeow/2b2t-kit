import Foundation

struct TranslationRequest: Codable {
    let text: String
    let from: String
    let to: String
    let id: String?

    func validate() throws {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              text.count <= 4096, text.utf8.count <= 12288 else {
            throw HTTPFailure(400, "invalid_text", "text must contain 1–4096 characters (at most 12288 UTF-8 bytes).")
        }
        let pattern = "^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$"
        guard (from == "auto" || from.range(of: pattern, options: .regularExpression) != nil),
              to.range(of: pattern, options: .regularExpression) != nil,
              from.count <= 40, to.count <= 40, (id?.utf8.count ?? 0) <= 128 else {
            throw HTTPFailure(400, "invalid_language", "Use a BCP-47 language tag; from may also be auto. id must be at most 128 bytes.")
        }
    }
}

struct TranslationResult: Codable {
    let translation: String
    let sourceLanguage: String
    let targetLanguage: String
    let id: String?
}

struct HTTPFailure: Error {
    let status: Int
    let code: String
    let message: String
    init(_ status: Int, _ code: String, _ message: String) {
        self.status = status; self.code = code; self.message = message
    }
    var reply: HTTPReply { .json(status, ["error": code, "message": message]) }
}

struct HTTPReply {
    let status: Int
    let body: Data
    static func json(_ status: Int = 200, _ value: [String: Any]) -> HTTPReply {
        HTTPReply(status: status, body: (try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])) ?? Data("{}".utf8))
    }
    static func translated(_ result: TranslationResult) -> HTTPReply {
        HTTPReply(status: 200, body: (try? JSONEncoder().encode(result)) ?? Data("{}".utf8))
    }
    var encoded: Data {
        let reasons = [200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed", 408: "Request Timeout", 411: "Length Required", 413: "Content Too Large", 415: "Unsupported Media Type", 429: "Too Many Requests", 500: "Internal Server Error", 503: "Service Unavailable", 504: "Gateway Timeout"]
        let header = "HTTP/1.1 \(status) \(reasons[status] ?? "Error")\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: \(body.count)\r\nConnection: close\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n\r\n"
        return Data(header.utf8) + body
    }
}

enum ParsedRequest {
    case health
    case translate(TranslationRequest)
}

enum HTTPParser {
    static let maxHeaderBytes = 8192
    static let maxBodyBytes = 16384

    /// nil means more bytes are needed. Every connection handles exactly one request.
    static func parse(_ data: Data, port: UInt16) throws -> ParsedRequest? {
        guard let split = data.range(of: Data("\r\n\r\n".utf8)) else {
            if data.count > maxHeaderBytes { throw HTTPFailure(413, "headers_too_large", "Headers exceed 8192 bytes.") }
            return nil
        }
        guard split.lowerBound <= maxHeaderBytes,
              let header = String(data: data[..<split.lowerBound], encoding: .utf8) else {
            throw HTTPFailure(400, "invalid_headers", "Invalid HTTP headers.")
        }
        let lines = header.components(separatedBy: "\r\n")
        let parts = (lines.first ?? "").split(separator: " ", omittingEmptySubsequences: false)
        guard parts.count == 3, parts[2] == "HTTP/1.1" || parts[2] == "HTTP/1.0" else {
            throw HTTPFailure(400, "invalid_request", "Expected an HTTP/1.x request.")
        }
        var headers: [String: String] = [:]
        for line in lines.dropFirst() {
            guard let colon = line.firstIndex(of: ":"), !line.hasPrefix(" "), !line.hasPrefix("\t") else {
                throw HTTPFailure(400, "invalid_headers", "Invalid header line.")
            }
            let name = String(line[..<colon]).lowercased()
            guard !name.isEmpty, name.range(of: "^[a-z0-9-]+$", options: .regularExpression) != nil,
                  headers[name] == nil else {
                throw HTTPFailure(400, "invalid_headers", "Repeated or invalid header.")
            }
            headers[name] = line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces)
        }
        guard headers["host"] == "127.0.0.1:\(port)" else {
            throw HTTPFailure(403, "invalid_host", "Only the literal loopback host is accepted.")
        }
        guard headers["origin"] == nil, !headers.keys.contains(where: { $0.hasPrefix("sec-fetch-") }), headers["referer"] == nil else {
            throw HTTPFailure(403, "browser_request_rejected", "Browser-originated requests are not accepted.")
        }
        guard headers["transfer-encoding"] == nil else {
            throw HTTPFailure(400, "unsupported_encoding", "Transfer-Encoding is not supported.")
        }
        let method = String(parts[0]), path = String(parts[1])
        guard path == "/health" || path == "/translate" else { throw HTTPFailure(404, "not_found", "Unknown path.") }
        guard (path == "/health" && method == "GET") || (path == "/translate" && method == "POST") else {
            throw HTTPFailure(405, "method_not_allowed", "Use GET /health or POST /translate.")
        }
        if path == "/translate" && headers["content-length"] == nil {
            throw HTTPFailure(411, "length_required", "Content-Length is required.")
        }
        let lengthText = headers["content-length"] ?? "0"
        guard !lengthText.isEmpty, lengthText.allSatisfy({ $0.isASCII && $0.isNumber }), let length = Int(lengthText), length >= 0 else {
            throw HTTPFailure(400, "invalid_length", "Invalid Content-Length.")
        }
        guard length <= maxBodyBytes else { throw HTTPFailure(413, "body_too_large", "Body exceeds 16384 bytes.") }
        let actual = data.count - split.upperBound
        guard actual <= length else { throw HTTPFailure(400, "extra_data", "Pipelined requests and trailing data are not accepted.") }
        guard actual == length else { return nil }
        if path == "/health" {
            guard length == 0 else { throw HTTPFailure(400, "unexpected_body", "GET /health has no body.") }
            return .health
        }
        guard headers["content-type"]?.lowercased().split(separator: ";").first?.trimmingCharacters(in: .whitespaces) == "application/json" else {
            throw HTTPFailure(415, "content_type_required", "Use Content-Type: application/json.")
        }
        let request: TranslationRequest
        do { request = try JSONDecoder().decode(TranslationRequest.self, from: data[split.upperBound...]) }
        catch { throw HTTPFailure(400, "invalid_json", "Expected JSON with text, from, to, and optional string id.") }
        try request.validate()
        return .translate(request)
    }
}
