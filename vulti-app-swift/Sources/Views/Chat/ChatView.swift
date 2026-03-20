import SwiftUI

/// Chat column (416px in agent detail panel).
/// Matches ChatView.svelte: context hints, streaming, typing indicator,
/// virtual message window, session management.
struct ChatView: View {
    let agentId: String
    var channel: String = "main"
    /// If provided, auto-send this message on first appear when there are no existing messages.
    var initialMessage: String? = nil
    @Environment(AppState.self) private var app
    @State private var ws = WebSocketManager()
    @State private var input = ""
    @State private var sessionId: String?
    @State private var didSendInitial = false
    @State private var recentSessions: [GatewayClient.SessionResponse] = []
    @State private var isLoadingSessions = false

    // Chat context hints per tab (matches original)
    static let tabHints: [String: String] = [
        "home": "Ask your agent to create a custom home view with any widget",
        "profile": "Ask about editing name, role, personality, or description",
        "connections": "Ask about connecting services or managing API access",
        "skills": "Ask about installing skills or creating custom ones",
        "actions": "Ask about scheduling cron jobs or setting up rules",
        "wallet": "Ask about payment setup or crypto vaults",
        "analytics": "Ask about usage stats, costs, or activity trends",
    ]

    var body: some View {
        VStack(spacing: 0) {
            // Session header with dropdown
            sessionHeaderBar
            Divider()

            // Messages area
            if ws.messages.isEmpty && !ws.isStreaming {
                Spacer()
                Text("Start a conversation with \(agentId)")
                    .font(.system(size: 13))
                    .foregroundStyle(VultiTheme.inkMuted)
                    .multilineTextAlignment(.center)
                    .padding()
                Spacer()
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 8) {
                            ForEach(ws.messages) { msg in
                                MessageBubble(message: msg)
                                    .id(msg.id)
                            }

                            // Streaming content (replace semantics)
                            if ws.isStreaming && !ws.streamingContent.isEmpty {
                                HStack(alignment: .top, spacing: 8) {
                                    ZStack {
                                        RoundedRectangle(cornerRadius: 8)
                                            .fill(VultiTheme.paperWarm)
                                            .frame(width: 28, height: 28)
                                        Image(systemName: "cpu")
                                            .font(.system(size: 12))
                                            .foregroundStyle(VultiTheme.inkDim)
                                    }
                                    MarkdownMessageView(
                                        content: ws.streamingContent,
                                        isUser: false
                                    )
                                        .padding(.horizontal, 14)
                                        .padding(.vertical, 10)
                                        .background(VultiTheme.paperWarm, in: RoundedRectangle(cornerRadius: 12))
                                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(VultiTheme.border))
                                    Spacer(minLength: 60)
                                }
                                .id("streaming")
                            }

                            // Typing indicator (3 bouncing dots)
                            if ws.isTyping {
                                TypingIndicator()
                                    .id("typing")
                            }
                        }
                        .padding(12)
                    }
                    .onChange(of: ws.messages.count) {
                        withAnimation {
                            proxy.scrollTo(ws.messages.last?.id ?? "streaming", anchor: .bottom)
                        }
                    }
                    .onChange(of: ws.streamingContent) {
                        proxy.scrollTo("streaming", anchor: .bottom)
                    }
                }
            }

            Divider()

            // Input area (Enter to send)
            HStack(alignment: .center, spacing: 8) {
                TextField("Message \(agentId)...", text: $input, axis: .vertical)
                    .textFieldStyle(.vulti)
                    .lineLimit(1...5)
                    .onSubmit { sendMessage() }

                Button { sendMessage() } label: {
                    Text("Send")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(VultiTheme.rainbowGradient, in: RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
                .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty)
                .opacity(input.trimmingCharacters(in: .whitespaces).isEmpty ? 0.5 : 1.0)
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 16)
        }
        .onAppear {
            loadSessions()
            if let initialMessage, !didSendInitial, ws.messages.isEmpty {
                didSendInitial = true
                autoSend(initialMessage)
            }
        }
    }

    // MARK: - Session Header Bar

    private var sessionHeaderBar: some View {
        HStack {
            // Session menu
            Menu {
                Button {
                    startNewSession()
                } label: {
                    Label("New Session", systemImage: "plus")
                }

                if !recentSessions.isEmpty {
                    Divider()

                    ForEach(recentSessions) { session in
                        Button {
                            switchToSession(session)
                        } label: {
                            sessionMenuItemLabel(session)
                        }
                    }
                }
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "bubble.left.and.bubble.right")
                        .font(.system(size: 11))
                    if let sessionId {
                        Text(truncatedSessionId(sessionId))
                            .font(.system(size: 12, weight: .medium))
                    } else {
                        Text("New Session")
                            .font(.system(size: 12, weight: .medium))
                    }
                    Image(systemName: "chevron.down")
                        .font(.system(size: 8, weight: .semibold))
                }
                .foregroundStyle(VultiTheme.inkSoft)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()

            Spacer()

            // New session button
            Button {
                startNewSession()
            } label: {
                HStack(spacing: 3) {
                    Image(systemName: "plus")
                        .font(.system(size: 10))
                    Text("New")
                        .font(.system(size: 12))
                }
                .foregroundStyle(VultiTheme.inkDim)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    // MARK: - Session Menu Item

    private func sessionMenuItemLabel(_ session: GatewayClient.SessionResponse) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(truncatedSessionId(session.id))
                    .font(.system(size: 12, weight: .medium))
                if session.id == sessionId {
                    Image(systemName: "checkmark")
                        .font(.system(size: 10))
                }
                Spacer()
                if let preview = session.preview, !preview.isEmpty {
                    Text(preview)
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkDim)
                        .lineLimit(1)
                }
            }
            if let date = session.createdAt {
                Text(formatSessionDate(date))
                    .font(.system(size: 10))
                    .foregroundStyle(VultiTheme.inkDim)
            }
        }
    }

    // MARK: - Session Actions

    private func loadSessions() {
        isLoadingSessions = true
        Task {
            recentSessions = (try? await app.client.listSessions(agentId: agentId)) ?? []
            isLoadingSessions = false
        }
    }

    private func startNewSession() {
        ws.disconnect()
        ws.messages.removeAll()
        ws.streamingContent = ""
        sessionId = nil
        loadSessions()
    }

    private func switchToSession(_ session: GatewayClient.SessionResponse) {
        guard session.id != sessionId else { return }

        // Disconnect current
        ws.disconnect()
        ws.messages.removeAll()
        ws.streamingContent = ""

        // Set new session
        sessionId = session.id

        // Load messages from gateway
        Task {
            let history = (try? await app.client.getHistory(session.id)) ?? []
            ws.messages = history.map { msg in
                ChatMessage(
                    messageId: msg.id ?? UUID().uuidString,
                    type: "message",
                    role: msg.role,
                    content: msg.content
                )
            }

            // Reconnect WebSocket to this session
            ws.connect(sessionId: session.id)
        }
    }

    private func deleteSession(_ session: GatewayClient.SessionResponse) {
        let wasActive = session.id == sessionId

        // Delete from gateway
        Task { try? await app.client.deleteSession(session.id) }

        // If it was the active session, start fresh
        if wasActive {
            startNewSession()
        } else {
            loadSessions()
        }
    }

    // MARK: - Helpers

    private func truncatedSessionId(_ id: String) -> String {
        if id.count > 12 {
            return String(id.prefix(12)) + "..."
        }
        return id
    }

    private func formatSessionDate(_ dateString: String) -> String {
        // Try ISO8601 parsing
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: dateString) {
            let relative = RelativeDateTimeFormatter()
            relative.unitsStyle = .abbreviated
            return relative.localizedString(for: date, relativeTo: Date())
        }
        // Fallback: try without fractional seconds
        formatter.formatOptions = [.withInternetDateTime]
        if let date = formatter.date(from: dateString) {
            let relative = RelativeDateTimeFormatter()
            relative.unitsStyle = .abbreviated
            return relative.localizedString(for: date, relativeTo: Date())
        }
        return dateString
    }

    /// Auto-send a message (used for onboarding initial prompts).
    private func autoSend(_ text: String) {
        // Optimistic user message
        ws.messages.append(ChatMessage(
            messageId: UUID().uuidString,
            type: "message",
            role: "user",
            content: text
        ))

        Task {
            // Create session via gateway (associates agentId)
            let sessionName = channel != "main" ? "onboard:\(channel)" : nil
            do {
                let session = try await app.client.createSession(agentId: agentId, name: sessionName)
                sessionId = session.id
                ws.connect(sessionId: session.id)
                try? await Task.sleep(for: .milliseconds(300))
            } catch {
                ws.messages.append(ChatMessage(
                    messageId: UUID().uuidString, type: "error", role: "system",
                    content: "Failed to create session: \(error.localizedDescription)"
                ))
                return
            }

            let payload: [String: String] = ["type": "message", "content": text]
            if let data = try? JSONEncoder().encode(payload),
               let json = String(data: data, encoding: .utf8) {
                try? await ws.send(json)
            }
        }
    }

    private func sendMessage() {
        let text = input.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        input = ""

        // Optimistic user message
        ws.messages.append(ChatMessage(
            messageId: UUID().uuidString,
            type: "message",
            role: "user",
            content: text
        ))

        Task {
            // Create session via gateway if needed (associates agentId server-side)
            if sessionId == nil {
                do {
                    let session = try await app.client.createSession(agentId: agentId)
                    sessionId = session.id
                    ws.connect(sessionId: session.id)
                    // Brief delay for WS to open
                    try? await Task.sleep(for: .milliseconds(200))
                } catch {
                    ws.messages.append(ChatMessage(
                        messageId: UUID().uuidString,
                        type: "error",
                        role: "system",
                        content: "Failed to create session: \(error.localizedDescription)"
                    ))
                    return
                }
            }

            let payload: [String: String] = ["type": "message", "content": text]
            if let data = try? JSONEncoder().encode(payload),
               let json = String(data: data, encoding: .utf8) {
                try? await ws.send(json)
            }
        }
    }
}

struct MessageBubble: View {
    let message: ChatMessage
    var isUser: Bool { message.role == "user" }
    var isError: Bool { message.type == "error" }

    var body: some View {
        HStack {
            if isUser { Spacer(minLength: 60) }

            if !isUser {
                // Agent avatar (28x28 matching Tauri h-7 w-7)
                ZStack {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(VultiTheme.paperWarm)
                        .frame(width: 28, height: 28)
                    Image(systemName: "cpu")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                }
            }

            MarkdownMessageView(
                content: message.content ?? "",
                isUser: isUser
            )
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background {
                    if isError {
                        RoundedRectangle(cornerRadius: 12)
                            .fill(Color.red.opacity(0.1))
                    } else if isUser {
                        RoundedRectangle(cornerRadius: 12)
                            .fill(VultiTheme.rainbowGradient)
                    } else {
                        RoundedRectangle(cornerRadius: 12)
                            .fill(VultiTheme.paperWarm)
                            .overlay(RoundedRectangle(cornerRadius: 12).stroke(VultiTheme.border))
                    }
                }

            if !isUser { Spacer(minLength: 60) }
        }
    }
}

/// Typing indicator: 3 bouncing dots (matches original 0ms, 150ms, 300ms delays)
struct TypingIndicator: View {
    @State private var phase = 0

    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .fill(.secondary)
                    .frame(width: 6, height: 6)
                    .offset(y: phase == i ? -4 : 0)
            }
        }
        .padding(10)
        .background(VultiTheme.paperWarm, in: RoundedRectangle(cornerRadius: 10))
        .onAppear {
            withAnimation(.easeInOut(duration: 0.4).repeatForever(autoreverses: true)) {
                phase = 2
            }
        }
    }
}
