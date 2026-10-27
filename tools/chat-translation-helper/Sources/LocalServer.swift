import Foundation
import Network

final class LocalServer {
    typealias Completion = (HTTPReply) -> Void
    let port: UInt16
    let onRequest: (ParsedRequest, @escaping Completion) -> Void
    let onState: (String, Bool) -> Void
    private let queue = DispatchQueue(label: "dev.minecraft.bilingual.http")
    private var listener: NWListener?
    private var clients: [UUID: HTTPConnection] = [:]

    init(port: UInt16 = 8765, onState: @escaping (String, Bool) -> Void, onRequest: @escaping (ParsedRequest, @escaping Completion) -> Void) {
        self.port = port; self.onRequest = onRequest; self.onState = onState
    }

    func start() {
        queue.async { [self] in
            do {
                let parameters = NWParameters.tcp
                parameters.requiredLocalEndpoint = .hostPort(host: NWEndpoint.Host("127.0.0.1"), port: NWEndpoint.Port(rawValue: port)!)
                let listener = try NWListener(using: parameters)
                self.listener = listener
                listener.stateUpdateHandler = { [weak self] state in
                    guard let self else { return }
                    switch state {
                    case .ready: self.onState("正在监听 127.0.0.1:\(self.port)", true)
                    case .failed(let error): self.onState("服务启动失败：\(error.localizedDescription)", false)
                    case .cancelled: self.onState("服务已停止", false)
                    default: break
                    }
                }
                listener.newConnectionHandler = { [weak self] connection in
                    guard let self else { connection.cancel(); return }
                    guard self.clients.count < 64 else { connection.cancel(); return }
                    let id = UUID()
                    let client = HTTPConnection(connection: connection, port: self.port, queue: self.queue, onRequest: self.onRequest) { [weak self] in
                        self?.clients.removeValue(forKey: id)
                    }
                    self.clients[id] = client
                    client.start()
                }
                listener.start(queue: queue)
            } catch { onState("服务启动失败：\(error.localizedDescription)", false) }
        }
    }

    func stop() {
        queue.async { [self] in
            listener?.cancel(); listener = nil
            for client in Array(clients.values) { client.close() }
            clients.removeAll()
        }
    }
}

private final class HTTPConnection {
    let connection: NWConnection
    let port: UInt16
    let queue: DispatchQueue
    let onRequest: (ParsedRequest, @escaping LocalServer.Completion) -> Void
    let onClose: () -> Void
    var buffer = Data()
    var finished = false
    var dispatched = false
    var timer: DispatchWorkItem?

    init(connection: NWConnection, port: UInt16, queue: DispatchQueue, onRequest: @escaping (ParsedRequest, @escaping LocalServer.Completion) -> Void, onClose: @escaping () -> Void) {
        self.connection = connection; self.port = port; self.queue = queue
        self.onRequest = onRequest; self.onClose = onClose
    }

    func start() {
        connection.stateUpdateHandler = { [weak self] state in
            if case .failed = state { self?.close() }
            if case .cancelled = state { self?.close() }
        }
        connection.start(queue: queue)
        setDeadline(seconds: 5, failure: HTTPFailure(408, "receive_timeout", "Request was not received within 5 seconds."))
        receive()
    }

    func setDeadline(seconds: Double, failure: HTTPFailure) {
        timer?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.send(failure.reply) }
        timer = work; queue.asyncAfter(deadline: .now() + seconds, execute: work)
    }

    func receive() {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, complete, error in
            guard let self, !self.finished, !self.dispatched else { return }
            if let data { self.buffer.append(data) }
            do {
                if let request = try HTTPParser.parse(self.buffer, port: self.port) {
                    self.dispatched = true
                    self.setDeadline(seconds: 27, failure: HTTPFailure(504, "translation_timeout", "Translation exceeded the local deadline."))
                    self.onRequest(request) { [weak self] reply in
                        guard let self else { return }
                        self.queue.async { self.send(reply) }
                    }
                } else if complete || error != nil { self.close() }
                else { self.receive() }
            } catch let failure as HTTPFailure { self.send(failure.reply) }
            catch { self.send(HTTPFailure(400, "bad_request", "Cannot parse request.").reply) }
        }
    }

    func send(_ reply: HTTPReply) {
        guard !finished else { return }
        finished = true; timer?.cancel(); timer = nil
        connection.send(content: reply.encoded, completion: .contentProcessed { [weak self] _ in
            guard let self else { return }
            self.connection.cancel(); self.onClose()
        })
    }

    func close() {
        guard !finished else { return }
        finished = true; timer?.cancel(); timer = nil
        connection.cancel(); onClose()
    }
}
