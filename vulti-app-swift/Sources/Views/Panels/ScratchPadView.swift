import SwiftUI

// MARK: - Drill-down target enum

/// Known detail views a widget can drill into via the "drill" field in WidgetData.
enum DrillTarget: String {
    case role, soul, user, memories, connections, skills, actions, wallet, analytics

    var contextLabel: String { rawValue }
}

// MARK: - Pane Tab

enum PaneTab: String, CaseIterable {
    case chat = "Chat"
    case home = "Home"
}

// MARK: - ScratchPadView

/// Agent-driven scratch pad with two tabs:
///   - Chat: per-session widgets (starts blank, fills during conversation)
///   - Home: persistent default dashboard (9 default widgets, user can curate)
struct ScratchPadView: View {
    let agentId: String
    let sessionId: String?
    @Binding var expandedWidget: DrillTarget?
    @Binding var hasContent: Bool

    @Environment(AppState.self) private var app

    @State private var activeTab: PaneTab = .home
    @State private var chatWidgets: [PaneWidget] = []
    @State private var homeWidgets: [PaneWidget] = []
    @State private var pollTimer: Timer?
    @State private var deletedIds: Set<String> = []
    @State private var suppressPoll = false
    @State private var draggingWidget: PaneWidget?

    private var widgets: [PaneWidget] {
        activeTab == .chat ? chatWidgets : homeWidgets
    }

    var body: some View {
        Group {
            if let drill = expandedWidget {
                drillDownView(for: drill)
            } else {
                VStack(spacing: 0) {
                    tabHeader
                    Divider()
                    widgetList
                }
            }
        }
        .onAppear {
            Task { await loadWidgets() }
            startPolling()
        }
        .onDisappear {
            stopPolling()
        }
        .onChange(of: sessionId) {
            // Session changed — reset chat widgets and reload
            chatWidgets = []
            deletedIds.removeAll()
            Task { await loadWidgetsForced() }
        }
    }

    // MARK: - Tab Header

    private var tabHeader: some View {
        HStack(spacing: 0) {
            ForEach(PaneTab.allCases, id: \.self) { tab in
                Button {
                    withAnimation(.easeInOut(duration: 0.15)) { activeTab = tab }
                } label: {
                    Text(tab.rawValue)
                        .font(.system(size: 12, weight: activeTab == tab ? .semibold : .regular))
                        .foregroundStyle(activeTab == tab ? VultiTheme.primary : VultiTheme.inkMuted)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                }
                .buttonStyle(.plain)
            }

            Spacer()

            if activeTab == .home {
                Button {
                    resetDefaults()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.counterclockwise")
                            .font(.system(size: 10, weight: .medium))
                        Text("Reset Defaults")
                            .font(.system(size: 11, weight: .medium))
                    }
                    .foregroundStyle(VultiTheme.inkMuted)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(VultiTheme.border.opacity(0.3), in: Capsule())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 4)
    }

    // MARK: - Widget List

    /// Group widgets into rows based on their size field.
    /// "half" widgets pair into 2-column rows; everything else gets its own row.
    private func buildRows(from list: [PaneWidget]) -> [[PaneWidget]] {
        var rows: [[PaneWidget]] = []
        var pending: [PaneWidget] = [] // accumulates half-width widgets
        for w in list {
            let sz = w.data.size ?? "large"
            if sz == "half" {
                pending.append(w)
                if pending.count == 2 {
                    rows.append(pending)
                    pending = []
                }
            } else {
                if !pending.isEmpty { rows.append(pending); pending = [] }
                rows.append([w])
            }
        }
        if !pending.isEmpty { rows.append(pending) }
        return rows
    }

    private var widgetList: some View {
        ScrollView {
            if widgets.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: activeTab == .chat ? "bubble.left.and.text.bubble.right" : "square.grid.2x2")
                        .font(.system(size: 24))
                        .foregroundStyle(VultiTheme.inkMuted.opacity(0.5))
                    Text(activeTab == .chat
                         ? "Chat widgets will appear here as you talk"
                         : "No home widgets")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                }
                .frame(maxWidth: .infinity, minHeight: 200)
                .padding(.top, 40)
            } else {
                let rows = buildRows(from: widgets)
                LazyVStack(spacing: 10) {
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                        if row.count > 1 {
                            HStack(spacing: 10) {
                                ForEach(row) { widget in
                                    widgetCard(widget)
                                        .frame(maxWidth: .infinity)
                                        .opacity(draggingWidget?.id == widget.id ? 0.4 : 1.0)
                                        .onDrag {
                                            draggingWidget = widget
                                            suppressPoll = true
                                            return NSItemProvider(object: widget.id as NSString)
                                        }
                                        .onDrop(of: [.text], delegate: WidgetDropDelegate(
                                            targetWidget: widget,
                                            widgets: activeTab == .chat ? $chatWidgets : $homeWidgets,
                                            draggingWidget: $draggingWidget,
                                            onReorder: saveOrder
                                        ))
                                }
                            }
                        } else if let widget = row.first {
                            widgetCard(widget)
                                .opacity(draggingWidget?.id == widget.id ? 0.4 : 1.0)
                                .onDrag {
                                    draggingWidget = widget
                                    suppressPoll = true
                                    return NSItemProvider(object: widget.id as NSString)
                                }
                                .onDrop(of: [.text], delegate: WidgetDropDelegate(
                                    targetWidget: widget,
                                    widgets: activeTab == .chat ? $chatWidgets : $homeWidgets,
                                    draggingWidget: $draggingWidget,
                                    onReorder: saveOrder
                                ))
                        }
                    }
                }
                .padding(16)
                .animation(.spring(duration: 0.25), value: widgets.map(\.id))
            }
        }
    }

    // MARK: - Widget Card

    private func widgetCard(_ widget: PaneWidget) -> some View {
        let drillTarget = widget.data.drill.flatMap { DrillTarget(rawValue: $0) }

        return VStack(alignment: .leading, spacing: 0) {
            // Top bar: drag handle (left) + close button (right)
            HStack(spacing: 0) {
                VStack(spacing: 2.5) {
                    ForEach(0..<3, id: \.self) { _ in
                        RoundedRectangle(cornerRadius: 0.5)
                            .fill(VultiTheme.inkMuted.opacity(0.4))
                            .frame(width: 14, height: 1.5)
                    }
                }
                .frame(width: 28, height: 28)
                .contentShape(Rectangle())

                Spacer()

                Button {
                    removeWidget(widget)
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(VultiTheme.inkMuted.opacity(0.5))
                        .frame(width: 20, height: 20)
                        .background(VultiTheme.border.opacity(0.3), in: Circle())
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 10)
            .padding(.top, 8)

            // Title row with optional drill chevron
            if let title = widget.title {
                HStack(spacing: 8) {
                    Text(title)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(VultiTheme.inkSoft)
                    Spacer()
                    if drillTarget != nil {
                        Image(systemName: "chevron.right")
                            .font(.system(size: 11))
                            .foregroundStyle(VultiTheme.inkMuted)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, widget.type == .empty ? 10 : 6)
            }

            // Widget content
            if widget.type != .empty {
                widgetBody(widget)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 16)
                    .padding(.bottom, 14)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(VultiTheme.border.opacity(0.5)))
        .contentShape(Rectangle())
        .onTapGesture {
            if let target = drillTarget {
                withAnimation(.easeInOut(duration: 0.2)) {
                    expandedWidget = target
                }
            }
        }
    }

    // MARK: - Delete

    private func removeWidget(_ widget: PaneWidget) {
        let widgetId = widget.id
        deletedIds.insert(widgetId)
        suppressPoll = true
        withAnimation(.easeOut(duration: 0.2)) {
            if activeTab == .chat {
                chatWidgets.removeAll { $0.id == widgetId }
            } else {
                homeWidgets.removeAll { $0.id == widgetId }
            }
        }
        Task {
            try? await app.client.removePaneWidget(agentId: agentId, widgetId: widgetId)
            try? await Task.sleep(for: .milliseconds(500))
            suppressPoll = false
        }
    }

    // MARK: - Reset Defaults (Home tab only)

    private func resetDefaults() {
        suppressPoll = true
        deletedIds.removeAll()
        withAnimation(.spring(duration: 0.3)) { homeWidgets = [] }
        Task {
            do {
                _ = try await app.client.resetDefaultWidgets(agentId: agentId)
                try? await Task.sleep(for: .milliseconds(200))
                await loadWidgetsForced()
            } catch {}
            suppressPoll = false
        }
    }

    // MARK: - Reorder

    private func saveOrder() {
        let ids = widgets.map(\.id)
        suppressPoll = true
        Task {
            try? await app.client.reorderPaneWidgets(agentId: agentId, widgetIds: ids)
            try? await Task.sleep(for: .milliseconds(200))
            await loadWidgetsForced()
            suppressPoll = false
            draggingWidget = nil
        }
    }

    // MARK: - Widget Body

    @ViewBuilder
    private func widgetBody(_ widget: PaneWidget) -> some View {
        switch widget.type {
        case .markdown:
            MarkdownWidgetContent(data: widget.data)
        case .kv:
            // Special rendering for wallet widget with card/vault data
            if widget.data.cardLast4 != nil || widget.data.vaultId != nil {
                WalletWidgetContent(data: widget.data)
            } else {
                KvWidgetContent(data: widget.data)
            }
        case .table:
            TableWidgetContent(data: widget.data)
        case .image:
            ImageWidgetContent(data: widget.data)
        case .status:
            StatusWidgetContent(data: widget.data)
        case .statGrid:
            StatGridWidgetContent(data: widget.data)
        case .barChart:
            BarChartWidgetContent(data: widget.data)
        case .progress:
            ProgressWidgetContent(data: widget.data)
        case .button:
            ButtonWidgetContent(data: widget.data, onSend: { msg in sendChatMessage(msg) })
        case .form:
            FormWidgetContent(data: widget.data, onSend: { msg in sendChatMessage(msg) })
        case .toggleList:
            ToggleListWidgetContent(data: widget.data, onSend: { msg in sendChatMessage(msg) })
        case .actionList:
            ActionListWidgetContent(data: widget.data, onSend: { msg in sendChatMessage(msg) })
        case .empty:
            EmptyView()
        case .profile:
            ProfileCardContent(data: widget.data, agentId: agentId, onDrill: { target in
                withAnimation(.easeInOut(duration: 0.2)) { expandedWidget = target }
            })
        }
    }

    // MARK: - Drill-Down View

    @ViewBuilder
    private func drillDownView(for target: DrillTarget) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    expandedWidget = nil
                }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 11, weight: .medium))
                    Text("Back")
                        .font(.system(size: 13, weight: .medium))
                }
                .foregroundStyle(VultiTheme.primary)
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            Divider()

            ScrollView {
                drillDownContent(for: target)
                    .padding(24)
            }
        }
    }

    @ViewBuilder
    private func drillDownContent(for target: DrillTarget) -> some View {
        switch target {
        case .role:
            RoleEditorView(agentId: agentId)
        case .soul:
            AgentProfileTab(agentId: agentId, initialSubtab: "Soul")
        case .user:
            AgentProfileTab(agentId: agentId, initialSubtab: "User")
        case .memories:
            AgentProfileTab(agentId: agentId, initialSubtab: "Memories")
        case .connections:
            AgentConnectionsTab(agentId: agentId)
        case .skills:
            AgentSkillsTab(agentId: agentId)
        case .actions:
            AgentActionsTab(agentId: agentId)
        case .wallet:
            AgentWalletTab(agentId: agentId)
        case .analytics:
            AgentAnalyticsTab(agentId: agentId)
        }
    }

    // MARK: - Data Loading

    private func loadWidgets() async {
        guard !suppressPoll else { return }
        await loadWidgetsForced()
    }

    private func loadWidgetsForced() async {
        do {
            let sid = sessionId
            let pane = try await app.client.getPaneWidgets(agentId: agentId, sessionId: sid)

            if let tabs = pane.tabs {
                // Home widgets
                let homeAll = (tabs["home"] ?? []).compactMap { $0.toPaneWidget() }
                let filteredHome = deletedIds.isEmpty ? homeAll : homeAll.filter { !deletedIds.contains($0.id) }
                if Set(filteredHome.map(\.id)) != Set(homeWidgets.map(\.id))
                    || filteredHome.map(\.id) != homeWidgets.map(\.id) {
                    withAnimation(.spring(duration: 0.3)) { homeWidgets = filteredHome }
                }

                // Chat widgets
                let chatAll = (tabs["chat"] ?? []).compactMap { $0.toPaneWidget() }
                let filteredChat = deletedIds.isEmpty ? chatAll : chatAll.filter { !deletedIds.contains($0.id) }
                let hadChatWidgets = !chatWidgets.isEmpty
                if Set(filteredChat.map(\.id)) != Set(chatWidgets.map(\.id))
                    || filteredChat.map(\.id) != chatWidgets.map(\.id) {
                    withAnimation(.spring(duration: 0.3)) { chatWidgets = filteredChat }
                }
                // Auto-switch to Chat tab when agent adds the first chat widget
                if !hadChatWidgets && !filteredChat.isEmpty {
                    withAnimation(.easeInOut(duration: 0.2)) { activeTab = .chat }
                }
            }

            if (!homeWidgets.isEmpty || !chatWidgets.isEmpty) && !hasContent {
                hasContent = true
            }
        } catch {
            // No widgets available yet
        }
    }

    // MARK: - Polling

    private func startPolling() {
        pollTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { _ in
            Task { await loadWidgets() }
        }
    }

    private func stopPolling() {
        pollTimer?.invalidate()
        pollTimer = nil
    }

    // MARK: - Chat Integration

    private func sendChatMessage(_ message: String) {
        NotificationCenter.default.post(
            name: .scratchPadMessage,
            object: nil,
            userInfo: ["message": message, "agentId": agentId]
        )
    }
}

// MARK: - Drop Delegate for Drag Reorder

struct WidgetDropDelegate: DropDelegate {
    let targetWidget: PaneWidget
    @Binding var widgets: [PaneWidget]
    @Binding var draggingWidget: PaneWidget?
    let onReorder: () -> Void

    func performDrop(info: DropInfo) -> Bool {
        draggingWidget = nil
        onReorder()
        return true
    }

    func dropEntered(info: DropInfo) {
        guard let dragging = draggingWidget,
              dragging.id != targetWidget.id,
              let fromIndex = widgets.firstIndex(where: { $0.id == dragging.id }),
              let toIndex = widgets.firstIndex(where: { $0.id == targetWidget.id })
        else { return }

        withAnimation(.spring(duration: 0.2)) {
            widgets.move(fromOffsets: IndexSet(integer: fromIndex), toOffset: toIndex > fromIndex ? toIndex + 1 : toIndex)
        }
    }

    func dropUpdated(info: DropInfo) -> DropProposal? {
        DropProposal(operation: .move)
    }
}

// MARK: - Notification Name

extension Notification.Name {
    static let scratchPadMessage = Notification.Name("scratchPadMessage")
    static let chatSessionChanged = Notification.Name("chatSessionChanged")
}

// MARK: - Profile Card Widget

struct ProfileCardContent: View {
    let data: WidgetData
    let agentId: String
    var onDrill: ((DrillTarget) -> Void)?

    @Environment(AppState.self) private var app

    private var agent: GatewayClient.AgentResponse? {
        app.agent(byId: agentId)
    }

    var body: some View {
        VStack(spacing: 14) {
            // Avatar + name + role row
            HStack(spacing: 12) {
                if let agent {
                    AgentAvatar(agent: agent, size: 44)
                } else {
                    // Fallback avatar
                    RoundedRectangle(cornerRadius: 8)
                        .fill(VultiTheme.paperWarm)
                        .frame(width: 44, height: 44)
                        .overlay(Text(String(agentId.prefix(1)).uppercased())
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(VultiTheme.inkDim))
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(agent?.name ?? agentId)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(VultiTheme.inkSoft)
                    if let role = data.role ?? agent?.role, !role.isEmpty {
                        Text(role)
                            .font(.system(size: 12))
                            .foregroundStyle(VultiTheme.inkMuted)
                    }
                }
                Spacer()
            }

            // Drill links row
            HStack(spacing: 0) {
                drillLink("Soul", icon: "sparkles", count: (data.hasSoul ?? false) ? nil : 0, target: .soul)
                Divider().frame(height: 20).padding(.horizontal, 8)
                drillLink("User", icon: "person", count: data.userCount, target: .user)
                Divider().frame(height: 20).padding(.horizontal, 8)
                drillLink("Memories", icon: "brain", count: data.memoryCount, target: .memories)
                Spacer()
            }
        }
    }

    private func drillLink(_ title: String, icon: String, count: Int?, target: DrillTarget) -> some View {
        Button {
            onDrill?(target)
        } label: {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 11))
                Text(title)
                    .font(.system(size: 12, weight: .medium))
                if let c = count, c > 0 {
                    Text("(\(c))")
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkDim)
                } else if count == 0 {
                    // Empty indicator
                    Circle()
                        .fill(VultiTheme.inkMuted.opacity(0.3))
                        .frame(width: 5, height: 5)
                }
                Image(systemName: "chevron.right")
                    .font(.system(size: 9))
                    .foregroundStyle(VultiTheme.inkMuted)
            }
            .foregroundStyle(VultiTheme.primary)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Credit Card Visual

struct CreditCardVisual: View {
    let name: String
    let last4: String
    let expiry: String

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Chip
            HStack {
                RoundedRectangle(cornerRadius: 3)
                    .fill(LinearGradient(colors: [.yellow.opacity(0.7), .orange.opacity(0.5)], startPoint: .topLeading, endPoint: .bottomTrailing))
                    .frame(width: 30, height: 22)
                    .overlay(
                        HStack(spacing: 2) {
                            ForEach(0..<3, id: \.self) { _ in
                                RoundedRectangle(cornerRadius: 0.5)
                                    .fill(.white.opacity(0.3))
                                    .frame(width: 1, height: 14)
                            }
                        }
                    )
                Spacer()
                Text("CREDIT")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(.white.opacity(0.5))
            }

            Spacer()

            // Card number
            Text("\u{2022}\u{2022}\u{2022}\u{2022}  \u{2022}\u{2022}\u{2022}\u{2022}  \u{2022}\u{2022}\u{2022}\u{2022}  \(last4)")
                .font(.system(size: 16, weight: .medium, design: .monospaced))
                .foregroundStyle(.white.opacity(0.9))
                .tracking(2)

            Spacer()

            // Name + expiry
            HStack {
                Text(name.uppercased())
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.white.opacity(0.8))
                    .lineLimit(1)
                Spacer()
                VStack(alignment: .trailing, spacing: 1) {
                    Text("VALID THRU")
                        .font(.system(size: 6, weight: .medium))
                        .foregroundStyle(.white.opacity(0.4))
                    Text(expiry)
                        .font(.system(size: 11, weight: .medium, design: .monospaced))
                        .foregroundStyle(.white.opacity(0.8))
                }
            }
        }
        .padding(16)
        .frame(height: 140)
        .background(
            LinearGradient(
                colors: [Color(red: 0.15, green: 0.1, blue: 0.35), Color(red: 0.25, green: 0.15, blue: 0.5)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 12)
        )
    }
}

// MARK: - Vault Visual

struct VaultVisual: View {
    let name: String
    let vaultId: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "shield.checkered")
                .font(.system(size: 24))
                .foregroundStyle(.green)

            VStack(alignment: .leading, spacing: 3) {
                Text(name)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(VultiTheme.inkSoft)
                Text(truncate(vaultId))
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(VultiTheme.inkMuted)
                    .lineLimit(1)
            }
            Spacer()
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.green)
                .font(.system(size: 16))
        }
        .padding(12)
        .background(VultiTheme.paperDeep.opacity(0.8), in: RoundedRectangle(cornerRadius: 10))
    }

    private func truncate(_ id: String) -> String {
        guard id.count > 16 else { return id }
        return String(id.prefix(8)) + "..." + String(id.suffix(6))
    }
}

// MARK: - Wallet Widget Content

struct WalletWidgetContent: View {
    let data: WidgetData

    var body: some View {
        VStack(spacing: 12) {
            if let last4 = data.cardLast4, !last4.isEmpty {
                CreditCardVisual(
                    name: data.cardName ?? "",
                    last4: last4,
                    expiry: data.cardExpiry ?? ""
                )
            }
            if let vid = data.vaultId, !vid.isEmpty {
                VaultVisual(
                    name: data.vaultName ?? "Vault",
                    vaultId: vid
                )
            }
            if data.cardLast4 == nil && data.vaultId == nil {
                HStack {
                    Image(systemName: "creditcard")
                        .font(.system(size: 20))
                        .foregroundStyle(VultiTheme.inkMuted.opacity(0.4))
                    Text("No card or vault set up")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                    Spacer()
                }
            }
        }
    }
}

// MARK: - Role Editor (standalone, no existing tab view)

struct RoleEditorView: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var role: String = ""
    @State private var draft: String = ""
    @State private var isEditing = false
    @State private var isSaving = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("ROLE")
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(VultiTheme.inkMuted)

            if isEditing {
                TextField("Agent role (e.g. assistant, researcher, coder)", text: $draft)
                    .textFieldStyle(.vulti)

                HStack(spacing: 8) {
                    Button {
                        isSaving = true
                        Task {
                            _ = try? await app.client.updateAgent(
                                agentId, updates: ["role": draft]
                            )
                            role = draft
                            await app.refreshAgents()
                            isSaving = false
                            isEditing = false
                        }
                    } label: {
                        Text(isSaving ? "Saving..." : "Save")
                    }
                    .buttonStyle(.vultiPrimary)
                    .controlSize(.small)
                    .disabled(isSaving)

                    Button("Cancel") { isEditing = false }
                        .controlSize(.small)
                }
            } else {
                if role.isEmpty {
                    Text("No role defined")
                        .font(.system(size: 13))
                        .foregroundStyle(VultiTheme.inkDim)
                } else {
                    Text(role)
                        .font(.system(size: 13))
                        .foregroundStyle(VultiTheme.inkSoft)
                }

                Button {
                    draft = role
                    isEditing = true
                } label: {
                    Text("Edit")
                }
                .buttonStyle(.vultiSecondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .task {
            role = app.agent(byId: agentId)?.role ?? ""
        }
    }
}
