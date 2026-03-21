import SwiftUI

/// Chat column (416px in agent detail panel).
/// Matches ChatView.svelte: context hints, streaming, typing indicator,
/// virtual message window, session management.
struct ChatView: View {
    let agentId: String
    /// When true, auto-resumes the latest session or triggers introspection on new sessions.
    var autoIntrospect: Bool = false
    /// Optional context label for what the user is viewing in the scratch pad (sent with messages)
    var viewingContext: String? = nil
    @Environment(AppState.self) private var app
    @State private var ws = WebSocketManager()
    @State private var input = ""
    @State private var sessionId: String?
    @State private var didAutoIntrospect = false
    @State private var recentSessions: [GatewayClient.SessionResponse] = []
    @State private var isLoadingSessions = false
    @State private var renameCount = 0  // tracks how many times we've auto-renamed

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
            let visibleMessages = ws.messages.filter { $0.content != "[status check]" }
            if visibleMessages.isEmpty && !ws.isStreaming {
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
                                // Hide introspect trigger messages
                                if msg.content != "[status check]" {
                                    MessageBubble(message: msg)
                                        .id(msg.id)
                                }
                            }

                            // Streaming content (replace semantics)
                            if ws.isStreaming && !ws.streamingContent.isEmpty {
                                HStack(alignment: .top, spacing: 8) {
                                    ThinkingAvatar()
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

                            // Typing indicator — agent avatar with spinning rainbow border
                            if ws.isTyping {
                                HStack {
                                    ThinkingAvatar()
                                    Spacer()
                                }
                                .id("typing")
                            }
                        }
                        .padding(12)
                    }
                    .onChange(of: ws.messages.count) {
                        withAnimation {
                            proxy.scrollTo(ws.messages.last?.id ?? "streaming", anchor: .bottom)
                        }
                        autoRenameIfNeeded()
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
            if autoIntrospect && !didAutoIntrospect {
                didAutoIntrospect = true
                Task {
                    // Wait for sessions to load
                    try? await Task.sleep(for: .milliseconds(400))
                    if let latest = recentSessions.first, isSessionFresh(latest) {
                        switchToSession(latest)
                    } else {
                        triggerIntrospect()
                    }
                }
            }
        }
        .onChange(of: sessionId) {
            // Notify scratch pad that the chat session changed
            if let sid = sessionId {
                NotificationCenter.default.post(
                    name: .chatSessionChanged,
                    object: nil,
                    userInfo: ["sessionId": sid, "agentId": agentId]
                )
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
                    Text(currentSessionLabel)
                        .font(.system(size: 12, weight: .medium))
                        .lineLimit(1)
                    Image(systemName: "chevron.down")
                        .font(.system(size: 8, weight: .semibold))
                }
                .foregroundStyle(VultiTheme.inkSoft)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()

            Spacer()

            // Delete current session
            if sessionId != nil {
                Button {
                    if let sid = sessionId {
                        Task { try? await app.client.deleteSession(sid) }
                        startNewSession()
                    }
                } label: {
                    Image(systemName: "trash")
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkDim)
                }
                .buttonStyle(.plain)
                .help("Delete session")
            }
        }
        .padding(.horizontal, 16)
        .frame(height: 40)
    }

    /// Display label for the current session — preview > name > truncated ID
    private var currentSessionLabel: String {
        if let sid = sessionId,
           let session = recentSessions.first(where: { $0.id == sid }) {
            return sessionDisplayName(session)
        }
        if sessionId != nil {
            return "Session"
        }
        return "New Session"
    }

    private func sessionDisplayName(_ session: GatewayClient.SessionResponse) -> String {
        if let name = session.name, !name.isEmpty, !name.hasPrefix("onboard:") {
            return name
        }
        if let preview = session.preview, !preview.isEmpty {
            return String(preview.prefix(40))
        }
        return truncatedSessionId(session.id)
    }

    // MARK: - Session Menu Item

    private func sessionMenuItemLabel(_ session: GatewayClient.SessionResponse) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(sessionDisplayName(session))
                    .font(.system(size: 12, weight: .medium))
                    .lineLimit(1)
                if let date = session.createdAt {
                    Text(formatSessionDate(date))
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkDim)
                }
            }
            Spacer()
            if session.id == sessionId {
                Image(systemName: "checkmark")
                    .font(.system(size: 10))
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
        renameCount = 0
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
        renameCount = 2 // don't auto-rename existing sessions

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

    /// Auto-rename session based on conversation content.
    /// Renames after the 1st assistant reply and again around the 6th message.
    private func autoRenameIfNeeded() {
        guard let sid = sessionId else { return }

        let assistantMessages = ws.messages.filter { $0.role == "assistant" }
        let totalMessages = ws.messages.count

        // First rename: when we get the first assistant reply
        // Second rename: after ~6 total messages for a better summary
        let shouldRename: Bool
        if renameCount == 0 && !assistantMessages.isEmpty {
            shouldRename = true
        } else if renameCount == 1 && totalMessages >= 6 {
            shouldRename = true
        } else {
            shouldRename = false
        }
        guard shouldRename else { return }

        // Build title from first user message + assistant context
        let title: String
        if renameCount == 0 {
            // First rename: use the user's first message (what they asked)
            if let firstUser = ws.messages.first(where: { $0.role == "user" }),
               let content = firstUser.content, !content.isEmpty {
                let cleaned = content
                    .components(separatedBy: .newlines).first ?? content
                title = String(cleaned.trimmingCharacters(in: .whitespaces).prefix(50))
            } else {
                return
            }
        } else {
            // Second rename: use the latest assistant reply's first line for evolved context
            guard let latest = assistantMessages.last,
                  let content = latest.content, !content.isEmpty else { return }
            let firstLine = content
                .components(separatedBy: .newlines)
                .first(where: { !$0.trimmingCharacters(in: .whitespaces).isEmpty })
                ?? content
            let cleaned = firstLine
                .replacingOccurrences(of: #"^[#*>\-\s]+"#, with: "", options: .regularExpression)
                .trimmingCharacters(in: .whitespaces)
            title = String(cleaned.prefix(50))
        }

        guard !title.isEmpty else { return }

        renameCount += 1
        Task {
            try? await app.client.renameSession(sid, name: title)
            loadSessions()
        }
    }

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

    /// Whether this agent is new (no role set yet) — determines hub_channel
    private var isNewAgent: Bool {
        (app.agent(byId: agentId)?.role ?? "").isEmpty
    }

    /// The hub_channel to send with messages — "onboard" for new agents, "introspect" for existing
    private var hubChannel: String {
        isNewAgent ? "onboard" : "introspect"
    }

    /// Trigger introspection — creates a new session and sends a hidden trigger message.
    private func triggerIntrospect() {
        Task {
            let dateStr = DateFormatter.localizedString(from: Date(), dateStyle: .medium, timeStyle: .none)
            let sessionName = isNewAgent ? "Onboarding" : "Check-in: \(dateStr)"
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

            let payload: [String: String] = [
                "type": "message",
                "content": "[status check]",
                "agent_id": agentId,
                "hub_channel": hubChannel,
            ]
            if let data = try? JSONEncoder().encode(payload),
               let json = String(data: data, encoding: .utf8) {
                ws.messages.append(ChatMessage(
                    messageId: UUID().uuidString,
                    type: "message",
                    role: "user",
                    content: "[status check]"
                ))
                try? await ws.send(json)
            }
            loadSessions()
        }
    }

    /// Check if a session is fresh enough to resume (< 24 hours old).
    private func isSessionFresh(_ session: GatewayClient.SessionResponse) -> Bool {
        let dateStr = session.updatedAt ?? session.createdAt ?? ""
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: dateStr) ?? ISO8601DateFormatter().date(from: dateStr)
        guard let date else { return false }
        return Date().timeIntervalSince(date) < 86400 // 24 hours
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
            let isFirstMessage = sessionId == nil
            if isFirstMessage {
                // Name the session from the first message (truncated)
                let sessionName = String(text.prefix(60))
                do {
                    let session = try await app.client.createSession(agentId: agentId, name: sessionName)
                    sessionId = session.id
                    ws.connect(sessionId: session.id)
                    // Brief delay for WS to open
                    try? await Task.sleep(for: .milliseconds(200))
                    // Refresh session list to show the new name
                    loadSessions()
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

            var payload: [String: String] = [
                "type": "message",
                "content": text,
                "agent_id": agentId,
                "hub_channel": hubChannel,
            ]
            if let ctx = viewingContext {
                payload["viewing_context"] = ctx
            }
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

/// Agent avatar with a spinning rainbow border to indicate thinking/streaming.
struct ThinkingAvatar: View {
    @State private var rotation: Double = 0

    var body: some View {
        ZStack {
            // Spinning rainbow border
            RoundedRectangle(cornerRadius: 10)
                .stroke(
                    AngularGradient(
                        colors: [
                            Color(hex: "#F28B6D"),  // coral
                            Color(hex: "#F0A84A"),  // amber
                            Color(hex: "#4AC6B7"),  // teal
                            Color(hex: "#F28B6D"),  // coral (wrap)
                        ],
                        center: .center,
                        angle: .degrees(rotation)
                    ),
                    lineWidth: 2.5
                )
                .frame(width: 32, height: 32)

            // Avatar background
            RoundedRectangle(cornerRadius: 8)
                .fill(VultiTheme.paperWarm)
                .frame(width: 26, height: 26)

            // Icon
            Image(systemName: "cpu")
                .font(.system(size: 12))
                .foregroundStyle(VultiTheme.inkDim)
        }
        .onAppear {
            withAnimation(.linear(duration: 1.5).repeatForever(autoreverses: false)) {
                rotation = 360
            }
        }
    }
}
