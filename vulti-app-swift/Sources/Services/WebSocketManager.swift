import Foundation
import Observation

/// WebSocket manager with streaming, typing indicator, and auto-reconnect.
/// Matches ws.ts: chunk (replace semantics), message, typing, error, notification.
@Observable
final class WebSocketManager {
    var isConnected = false
    var isTyping = false
    var isStreaming = false
    var messages: [ChatMessage] = []
    var streamingContent = ""
    var activeToolCall: String? = nil  // e.g. "⚙️ web_search: \"crypto papers\""

    private var webSocket: URLSessionWebSocketTask?
    private var sessionId: String?
    private var reconnectTask: Task<Void, Never>?
    private var pendingSend: [String] = []
    private let baseURL = "ws://localhost:8080/ws"

    // MARK: - Connect (with token auth)

    func connect(sessionId: String) {
        disconnect()
        self.sessionId = sessionId

        var urlString = "\(baseURL)/\(sessionId)"
        if let token = VultiHome.webToken() {
            urlString += "?token=\(token)"
        }
        guard let url = URL(string: urlString) else { return }

        let session = URLSession(configuration: .default)
        webSocket = session.webSocketTask(with: url)
        webSocket?.resume()
        isConnected = true

        // Flush any buffered messages
        for msg in pendingSend {
            Task { try? await send(msg) }
        }
        pendingSend.removeAll()

        receiveLoop()
    }

    func disconnect() {
        reconnectTask?.cancel()
        reconnectTask = nil
        // Preserve any in-flight streaming content as a completed message
        if isStreaming && !streamingContent.isEmpty {
            messages.append(ChatMessage(
                messageId: UUID().uuidString,
                type: "message",
                role: "assistant",
                content: streamingContent
            ))
            streamingContent = ""
        }
        webSocket?.cancel(with: .normalClosure, reason: nil)
        webSocket = nil
        isConnected = false
        isTyping = false
        isStreaming = false
    }

    // MARK: - Send (buffers if not connected)

    func send(_ text: String) async throws {
        guard let ws = webSocket, isConnected else {
            pendingSend.append(text)
            return
        }
        try await ws.send(.string(text))
    }

    // MARK: - Receive loop with message type handling

    private func receiveLoop() {
        webSocket?.receive { [weak self] result in
            guard let self else { return }

            switch result {
            case .success(let msg):
                let data: Data
                switch msg {
                case .string(let text): data = text.data(using: .utf8) ?? Data()
                case .data(let d): data = d
                @unknown default: data = Data()
                }

                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    Task { @MainActor in self.handleMessage(json) }
                }
                self.receiveLoop()

            case .failure:
                Task { @MainActor in
                    // If we were streaming, save partial content as a message
                    if self.isStreaming && !self.streamingContent.isEmpty {
                        let msg = ChatMessage(
                            messageId: UUID().uuidString,
                            type: "message",
                            role: "assistant",
                            content: self.streamingContent
                        )
                        self.messages.append(msg)
                        self.streamingContent = ""
                    }
                    self.isConnected = false
                    self.isTyping = false
                    self.isStreaming = false
                    self.scheduleReconnect()
                }
            }
        }
    }

    // MARK: - Message type dispatch (matches ws.ts protocol)

    @MainActor
    private func handleMessage(_ json: [String: Any]) {
        let type = json["type"] as? String ?? ""

        switch type {
        case "chunk":
            // Replace semantics — content is full accumulated text
            isStreaming = true
            isTyping = false
            activeToolCall = nil
            streamingContent = json["content"] as? String ?? ""

        case "message":
            // Complete message — ends streaming
            isStreaming = false
            isTyping = false
            activeToolCall = nil
            let content = json["content"] as? String ?? streamingContent
            streamingContent = ""
            let msg = ChatMessage(
                messageId: json["message_id"] as? String ?? UUID().uuidString,
                type: "message",
                role: json["role"] as? String ?? "assistant",
                content: content,
                agentId: json["agent_id"] as? String,
                timestamp: json["timestamp"] as? String
            )
            messages.append(msg)

        case "tool_use":
            let name = json["name"] as? String ?? "tool"
            let emoji = json["emoji"] as? String ?? "⚙️"
            let preview = json["preview"] as? String ?? ""
            activeToolCall = preview.isEmpty ? "\(emoji) \(name)" : "\(emoji) \(name): \(preview)"

        case "typing":
            isTyping = json["active"] as? Bool ?? true

        case "error":
            isStreaming = false
            isTyping = false
            let msg = ChatMessage(
                messageId: UUID().uuidString,
                type: "error",
                role: "system",
                content: json["message"] as? String ?? json["content"] as? String ?? "Unknown error"
            )
            messages.append(msg)

        case "notification":
            // Notifications handled separately via AppState
            break

        default:
            break
        }
    }

    // MARK: - Auto-reconnect (2s delay — matches original)

    private func scheduleReconnect() {
        guard let sessionId else { return }
        reconnectTask?.cancel()
        reconnectTask = Task {
            try? await Task.sleep(for: .seconds(2))
            guard !Task.isCancelled else { return }
            self.connect(sessionId: sessionId)
        }
    }
}
