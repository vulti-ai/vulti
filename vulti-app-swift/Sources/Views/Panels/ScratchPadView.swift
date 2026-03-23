import SwiftUI

// MARK: - Drill-down target enum

/// Known detail views a widget can drill into via the "drill" field in WidgetData.
enum DrillTarget: String {
    case role, soul, user, memories, connections, skills, actions, jobs, rules, wallet, crypto, analytics

    var contextLabel: String { rawValue }
}

// MARK: - Pane Tab

enum PaneTab: String, CaseIterable {
    case chat = "Chat"
    case home = "ScratchPad"
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
    var onHide: (() -> Void)?

    @Environment(AppState.self) private var app

    @State private var activeTab: PaneTab = .home
    @State private var chatWidgets: [PaneWidget] = []
    @State private var homeWidgets: [PaneWidget] = []
    @State private var pollTimer: Timer?
    @State private var deletedIds: Set<String> = []
    @State private var suppressPoll = false
    @State private var draggingRowId: String?
    @State private var refreshTick: Int = 0
    @State private var hasSoulRevealed = false
    /// Cached rows — rebuilt when widgets change, reorderable by drag
    @State private var rows: [WidgetRow] = []

    private var isOnboarding: Bool {
        app.agent(byId: agentId)?.status == "onboarding"
    }

    private var availableTabs: [PaneTab] {
        isOnboarding ? [.chat] : PaneTab.allCases
    }

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
            if isOnboarding { activeTab = .chat }
            Task { await loadWidgets() }
            startPolling()
        }
        .onDisappear {
            stopPolling()
        }
        .onChange(of: sessionId) {
            chatWidgets = []
            deletedIds.removeAll()
            Task { await loadWidgetsForced() }
        }
        .onChange(of: homeWidgets.map(\.id)) { rebuildRows() }
        .onChange(of: chatWidgets.map(\.id)) { rebuildRows() }
        .onChange(of: activeTab) { rebuildRows() }
    }

    /// Rebuild rows only when the SET of widgets changes (added/removed).
    /// Preserves user's manual row order on reorder or tab switch.
    private func rebuildRows() {
        guard draggingRowId == nil else { return } // never during drag

        let currentWidgetIds = Set(rows.flatMap { $0.widgets.map(\.id) })
        let newWidgetIds = Set(widgets.map(\.id))

        // Only rebuild if widgets were added or removed
        if currentWidgetIds != newWidgetIds {
            rows = buildRows(from: widgets)
        }
    }

    // MARK: - Tab Header

    private var tabHeader: some View {
        HStack(spacing: 0) {
            ForEach(availableTabs, id: \.self) { tab in
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

            if let onHide {
                Button { onHide() } label: {
                    Text("Hide Panel")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(VultiTheme.primary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 4)
    }

    // MARK: - Widget List

    /// Canonical drill target for a widget (explicit or inferred).
    private func drillKey(_ w: PaneWidget) -> String {
        if let d = w.data.drill { return d }
        if w.type == .profile { return "profile" }
        let title = (w.title ?? "").lowercased()
        if title.contains("analytic") || title.contains("usage") { return "analytics" }
        if title.contains("connection") || title.contains("integration") { return "connections" }
        if title.contains("skill") { return "skills" }
        if title.contains("job") || title.contains("cron") { return "jobs" }
        if title.contains("rule") { return "rules" }
        if title.contains("wallet") || title.contains("card") || title.contains("credit") { return "wallet" }
        if title.contains("vault") || title.contains("crypto") { return "crypto" }
        return ""
    }

    /// Fixed row pairings: [left, right] drill keys.
    /// Row 1: Profile + Analytics
    /// Row 2: Connections + Skills
    /// Row 3: Jobs + Rules
    /// Row 4: Wallet (card) + Crypto (vault)
    private static let rowPairs: [[String]] = [
        ["profile", "analytics"],
        ["connections", "skills"],
        ["jobs", "rules"],
        ["wallet", "crypto"],
    ]

    private func buildRows(from list: [PaneWidget]) -> [WidgetRow] {
        // Index widgets by drill key
        var byKey: [String: PaneWidget] = [:]
        var unmatched: [PaneWidget] = []
        for w in list {
            let key = drillKey(w)
            if !key.isEmpty {
                byKey[key] = w
            } else {
                unmatched.append(w)
            }
        }

        var rawRows: [[PaneWidget]] = []

        // Build paired rows in canonical order
        for pair in Self.rowPairs {
            let left = byKey.removeValue(forKey: pair[0])
            let right = byKey.removeValue(forKey: pair[1])
            if let l = left, let r = right {
                rawRows.append([l, r])
            } else if let l = left {
                rawRows.append([l])
            } else if let r = right {
                rawRows.append([r])
            }
        }

        // Any remaining keyed widgets not in canonical pairs
        let remaining = byKey.values.sorted { ($0.title ?? "") < ($1.title ?? "") }
        var pending: [PaneWidget] = []
        for w in remaining {
            pending.append(w)
            if pending.count == 2 { rawRows.append(pending); pending = [] }
        }

        // Unmatched widgets (no drill key) — pair as half-width or full
        for w in unmatched {
            let sz = w.data.size ?? "large"
            if sz == "half" {
                pending.append(w)
                if pending.count == 2 { rawRows.append(pending); pending = [] }
            } else {
                if !pending.isEmpty { rawRows.append(pending); pending = [] }
                rawRows.append([w])
            }
        }
        if !pending.isEmpty { rawRows.append(pending) }

        return rawRows.map { WidgetRow(id: $0.first!.id, widgets: $0) }
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
                LazyVStack(spacing: 10) {
                    ForEach(rows) { row in
                        Group {
                            if row.widgets.count > 1 {
                                mergedWidgetCard(row.widgets)
                            } else {
                                widgetCard(row.widgets[0])
                            }
                        }
                        .opacity(draggingRowId == row.id ? 0.4 : 1.0)
                        .onDrag {
                            draggingRowId = row.id
                            suppressPoll = true
                            return NSItemProvider(object: row.id as NSString)
                        }
                        .onDrop(of: [.text], delegate: RowDropDelegate(
                            targetRow: row,
                            rows: $rows,
                            draggingRowId: $draggingRowId,
                            onReorder: saveRowOrder
                        ))
                    }

                    // Files widget as the last row
                    if activeTab == .home {
                        AgentFilesView(agentId: agentId)
                            .padding(12)
                            .background(VultiTheme.paperDeep.opacity(0.4), in: RoundedRectangle(cornerRadius: 10))
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(VultiTheme.border.opacity(0.3)))
                    }
                }
                .padding(16)
                .animation(.spring(duration: 0.25), value: rows.map(\.id))
            }
        }
    }

    // MARK: - Widget Card

    /// Infer drill target from widget title/content when `drill` field isn't set
    static func inferDrillTarget(for widget: PaneWidget) -> DrillTarget? {
        // Explicit drill field takes priority
        if let drill = widget.data.drill, let target = DrillTarget(rawValue: drill) {
            return target
        }
        // Auto-detect from title
        let title = (widget.title ?? "").lowercased()
        if title.contains("vault") || title.contains("crypto") || title.contains("bitcoin")
            || title.contains("ethereum") || title.contains("token") || title.contains("chain") {
            return .crypto
        }
        if title.contains("card") || title.contains("credit") || title.contains("debit")
            || title.contains("payment") {
            return .wallet
        }
        if title.contains("rule") { return .rules }
        if title.contains("job") || title.contains("cron") || title.contains("schedule") { return .jobs }
        if title.contains("skill") { return .skills }
        if title.contains("connection") || title.contains("integration") { return .connections }
        if title.contains("analytic") || title.contains("usage") { return .analytics }
        if title.contains("soul") || title.contains("personality") { return .soul }
        if title.contains("memor") { return .memories }
        return nil
    }

    /// Detect if a KV widget contains vault details (by title or entry keys)
    static func looksLikeVault(_ widget: PaneWidget) -> Bool {
        let title = (widget.title ?? "").lowercased()
        if title.contains("vault") { return true }
        let keys = Set((widget.data.entries ?? []).map { $0.key.lowercased() })
        return keys.contains("vault id") || keys.contains("party id") || (keys.contains("name") && keys.contains("security"))
    }

    /// Merged card — two widgets rendered side by side inside a single card container.
    private func mergedWidgetCard(_ row: [PaneWidget]) -> some View {
        let leftWidget = row[0]
        let rightWidget = row[1]
        let leftDrill = Self.inferDrillTarget(for: leftWidget)
        let rightDrill = Self.inferDrillTarget(for: rightWidget)

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
                    removeWidget(rightWidget)
                    removeWidget(leftWidget)
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

            // Content: two columns side by side
            HStack(alignment: .top, spacing: 0) {
                // Left column
                VStack(alignment: .leading, spacing: 8) {
                    // Title row with live dot + drill chevron
                    if let title = leftWidget.title, !title.isEmpty {
                        HStack(spacing: 6) {
                            Text(title)
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(VultiTheme.inkSoft)
                            Spacer()
                            if isLiveWidget(leftWidget) {
                                Circle().fill(.green).frame(width: 6, height: 6)
                            }
                            if leftDrill != nil {
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 10))
                                    .foregroundStyle(VultiTheme.inkMuted)
                            }
                        }
                    }
                    widgetBody(leftWidget)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .padding(14)
                .contentShape(Rectangle())
                .onTapGesture {
                    if let drill = leftDrill {
                        withAnimation(.easeInOut(duration: 0.2)) { expandedWidget = drill }
                    }
                }

                // Divider between columns
                Rectangle()
                    .fill(VultiTheme.border)
                    .frame(width: 1)

                // Right column
                VStack(alignment: .leading, spacing: 8) {
                    if let title = rightWidget.title, !title.isEmpty {
                        HStack(spacing: 6) {
                            Text(title)
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(VultiTheme.inkSoft)
                            Spacer()
                            if isLiveWidget(rightWidget) {
                                Circle().fill(.green).frame(width: 6, height: 6)
                            }
                            if rightDrill != nil {
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 10))
                                    .foregroundStyle(VultiTheme.inkMuted)
                            }
                        }
                    }
                    widgetBody(rightWidget)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .padding(14)
                .contentShape(Rectangle())
                .onTapGesture {
                    if let drill = rightDrill {
                        withAnimation(.easeInOut(duration: 0.2)) { expandedWidget = drill }
                    }
                }
            }
        }
        .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(VultiTheme.border.opacity(0.5)))
    }

    private func widgetCard(_ widget: PaneWidget) -> some View {
        let drillTarget = Self.inferDrillTarget(for: widget)

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

            // Title row with live dot + optional drill chevron
            if let title = widget.title {
                HStack(spacing: 8) {
                    Text(title)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(VultiTheme.inkSoft)
                    Spacer()
                    if isLiveWidget(widget) {
                        Circle().fill(.green).frame(width: 6, height: 6)
                    }
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
        }
    }

    /// Save row order — persists reordered rows to backend
    private func saveRowOrder() {
        let ids = rows.flatMap { $0.widgets.map(\.id) }
        suppressPoll = true
        Task {
            try? await app.client.reorderPaneWidgets(agentId: agentId, widgetIds: ids)
            // Sync the flat arrays to match new order (without triggering rebuild)
            let reordered = ids.compactMap { id in widgets.first { $0.id == id } }
            if activeTab == .chat {
                chatWidgets = reordered
            } else {
                homeWidgets = reordered
            }
            try? await Task.sleep(for: .milliseconds(300))
            suppressPoll = false
            draggingRowId = nil
        }
    }

    // MARK: - Live Indicator

    /// Returns true if this widget fetches live data from the API (vs static pane_widgets.json).
    private func isLiveWidget(_ widget: PaneWidget) -> Bool {
        let drill = widget.data.drill ?? ""
        if widget.type == .profile || drill == "profile" { return true }
        if drill == "connections" { return true }
        if drill == "analytics" { return true }
        if drill == "jobs" { return true }
        if drill == "rules" { return true }
        if drill == "skills" { return true }
        if drill == "wallet" || drill == "crypto" { return true }
        return false
    }

    // MARK: - Widget Body

    @ViewBuilder
    private func widgetBody(_ widget: PaneWidget) -> some View {
        // Every known widget type gets a live override that fetches from the API.
        // No widget should ever render stale data from pane_widgets.json.
        let drill = widget.data.drill ?? ""
        if widget.type == .profile || drill == "profile" {
            LiveProfileWidget(agentId: agentId, tick: refreshTick, onDrill: { target in
                withAnimation(.easeInOut(duration: 0.2)) { expandedWidget = target }
            })
        } else if drill == "connections" {
            LiveConnectionsWidget(agentId: agentId, tick: refreshTick)
        } else if drill == "analytics" {
            LiveAnalyticsWidget(agentId: agentId, tick: refreshTick)
        } else if drill == "jobs" {
            LiveJobsWidget(agentId: agentId, tick: refreshTick)
        } else if drill == "rules" {
            LiveRulesWidget(agentId: agentId, tick: refreshTick)
        } else if drill == "skills" {
            LiveSkillsWidget(agentId: agentId, tick: refreshTick)
        } else if drill == "wallet" || drill == "crypto" {
            LiveWalletWidget(agentId: agentId, tick: refreshTick)
        } else {
            staticWidgetBody(widget)
        }
    }

    @ViewBuilder
    private func staticWidgetBody(_ widget: PaneWidget) -> some View {
        switch widget.type {
        case .markdown:
            MarkdownWidgetContent(data: widget.data)
        case .kv:
            if widget.data.cardLast4 != nil || widget.data.vaultId != nil {
                WalletWidgetContent(data: widget.data)
            } else if Self.looksLikeVault(widget) {
                // Render vault KV entries as the green VaultVisual card
                VaultVisualFromKV(entries: widget.data.entries ?? [])
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
        case .actions, .jobs:
            AgentActionsTab(agentId: agentId, initialSubtab: "Jobs")
        case .rules:
            AgentActionsTab(agentId: agentId, initialSubtab: "Rules")
        case .wallet:
            AgentWalletTab(agentId: agentId)
        case .crypto:
            AgentWalletTab(agentId: agentId, initialSubtab: "Crypto")
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
                let hadHomeWidgets = !homeWidgets.isEmpty
                if Set(filteredHome.map(\.id)) != Set(homeWidgets.map(\.id))
                    || filteredHome.map(\.id) != homeWidgets.map(\.id) {
                    withAnimation(.spring(duration: 0.3)) { homeWidgets = filteredHome }
                }
                // Auto-switch to Home tab when agent creates home content for the first time
                if !hadHomeWidgets && !filteredHome.isEmpty {
                    withAnimation(.easeInOut(duration: 0.2)) { activeTab = .home }
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
                if !hadChatWidgets && !filteredChat.isEmpty && hadHomeWidgets {
                    withAnimation(.easeInOut(duration: 0.2)) { activeTab = .chat }
                }
            }

            // Bump tick so live widgets re-fetch data
            refreshTick += 1

            // Auto-switch to Home when soul first appears (agent finished setting up identity)
            if !hasSoulRevealed && activeTab == .chat {
                if let soul = try? await app.client.getSoul(agentId: agentId),
                   !soul.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    hasSoulRevealed = true
                    withAnimation(.easeInOut(duration: 0.2)) { activeTab = .home }
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

/// A row of 1-2 widgets, used as the unit for drag-reorder.
struct WidgetRow: Identifiable, Equatable {
    let id: String // first widget's ID
    var widgets: [PaneWidget]

    static func == (lhs: WidgetRow, rhs: WidgetRow) -> Bool {
        lhs.id == rhs.id
    }
}

struct RowDropDelegate: DropDelegate {
    let targetRow: WidgetRow
    @Binding var rows: [WidgetRow]
    @Binding var draggingRowId: String?
    let onReorder: () -> Void

    func performDrop(info: DropInfo) -> Bool {
        onReorder()
        draggingRowId = nil
        return true
    }

    func dropEntered(info: DropInfo) {
        guard let draggingId = draggingRowId,
              draggingId != targetRow.id,
              let fromIndex = rows.firstIndex(where: { $0.id == draggingId }),
              let toIndex = rows.firstIndex(where: { $0.id == targetRow.id })
        else { return }

        withAnimation(.spring(duration: 0.2)) {
            rows.move(fromOffsets: IndexSet(integer: fromIndex), toOffset: toIndex > fromIndex ? toIndex + 1 : toIndex)
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
                    if let role = agent?.role ?? data.role, !role.isEmpty {
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
        .task { await app.refreshAgents() }
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
    var cvv: String? = nil

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
                if let cvv, !cvv.isEmpty {
                    VStack(alignment: .trailing, spacing: 1) {
                        Text("CVV")
                            .font(.system(size: 6, weight: .medium))
                            .foregroundStyle(.white.opacity(0.4))
                        Text("\u{2022}\u{2022}\u{2022}")
                            .font(.system(size: 11, weight: .medium, design: .monospaced))
                            .foregroundStyle(.white.opacity(0.8))
                    }
                }
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
    var portfolioValue: String? = nil
    var chainCount: Int = 0
    var vaultType: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Top: shield icon + VAULT label
            HStack {
                Image(systemName: "shield.checkered")
                    .font(.system(size: 18))
                    .foregroundStyle(.green)
                Spacer()
                Text("VAULT")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(.white.opacity(0.5))
            }

            Spacer(minLength: 6)

            // Vault name
            Text(name)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.white.opacity(0.9))
                .lineLimit(1)

            // Vault ID
            if !vaultId.isEmpty {
                Text(truncate(vaultId))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.4))
                    .lineLimit(1)
                    .padding(.top, 1)
            }

            Spacer(minLength: 4)

            // Type + security
            HStack(spacing: 12) {
                if let type = vaultType, !type.isEmpty {
                    vaultDetail("Type", type)
                } else {
                    vaultDetail("Type", "Fast Vault")
                }
                vaultDetail("Security", "2-of-2 MPC")
            }

            Spacer(minLength: 4)

            // Portfolio value
            if let value = portfolioValue, !value.isEmpty {
                Text("$\(value)")
                    .font(.system(size: 18, weight: .bold, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.9))
                Spacer(minLength: 4)
            }

            // Bottom: status + chain count
            HStack {
                HStack(spacing: 4) {
                    Circle()
                        .fill(.green)
                        .frame(width: 6, height: 6)
                    Text("CONNECTED")
                        .font(.system(size: 7, weight: .medium))
                        .foregroundStyle(.white.opacity(0.5))
                }
                Spacer()
                if chainCount > 0 {
                    Text("\(chainCount) chains")
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(.white.opacity(0.5))
                }
            }
        }
        .padding(14)
        .frame(minHeight: 140)
        .background(
            LinearGradient(
                colors: [Color(red: 0.08, green: 0.18, blue: 0.12), Color(red: 0.12, green: 0.25, blue: 0.15)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 12)
        )
    }

    private func vaultDetail(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label)
                .font(.system(size: 7, weight: .medium))
                .foregroundStyle(.white.opacity(0.4))
            Text(value)
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.white.opacity(0.7))
        }
    }

    private func truncate(_ id: String) -> String {
        guard id.count > 16 else { return id }
        return String(id.prefix(8)) + "..." + String(id.suffix(6))
    }
}

/// Renders KV entries as a green vault card — extracts Name, ID, Type, Security, Party ID from entries.
struct VaultVisualFromKV: View {
    let entries: [KvEntry]

    private func value(for key: String) -> String {
        entries.first { $0.key.lowercased() == key.lowercased() }?.value ?? ""
    }

    var body: some View {
        let name = value(for: "Name")
        let vaultId = value(for: "ID")
        let type = value(for: "Type")
        let security = value(for: "Security")
        let partyId = value(for: "Party ID")
        let created = value(for: "Created")

        VStack(alignment: .leading, spacing: 0) {
            // Top: shield + VAULT label
            HStack {
                Image(systemName: "shield.checkered")
                    .font(.system(size: 18))
                    .foregroundStyle(.green)
                Spacer()
                Text("VAULT")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(.white.opacity(0.5))
            }

            Spacer(minLength: 8)

            // Vault name
            if !name.isEmpty {
                Text(name)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.9))
                    .lineLimit(1)
            }

            // Vault ID
            if !vaultId.isEmpty {
                Text(vaultId)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.white.opacity(0.4))
                    .lineLimit(1)
                    .padding(.top, 2)
            }

            Spacer(minLength: 6)

            // Details
            VStack(alignment: .leading, spacing: 4) {
                if !type.isEmpty {
                    kvRow("Type", type)
                }
                if !security.isEmpty {
                    kvRow("Security", security)
                }
                if !partyId.isEmpty {
                    kvRow("Party ID", partyId)
                }
                if !created.isEmpty {
                    kvRow("Created", created)
                }
            }

            Spacer(minLength: 6)

            // Bottom: status
            HStack(spacing: 4) {
                Circle()
                    .fill(.green)
                    .frame(width: 6, height: 6)
                Text("CONNECTED")
                    .font(.system(size: 7, weight: .medium))
                    .foregroundStyle(.white.opacity(0.5))
                Spacer()
            }
        }
        .padding(14)
        .background(
            LinearGradient(
                colors: [Color(red: 0.08, green: 0.18, blue: 0.12), Color(red: 0.12, green: 0.25, blue: 0.15)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 12)
        )
    }

    private func kvRow(_ key: String, _ value: String) -> some View {
        HStack {
            Text(key)
                .font(.system(size: 9))
                .foregroundStyle(.white.opacity(0.4))
            Spacer()
            Text(value)
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(.white.opacity(0.7))
                .lineLimit(1)
        }
    }
}

// MARK: - Wallet Widget Content

struct WalletWidgetContent: View {
    let data: WidgetData

    private var hasCard: Bool { data.cardLast4 != nil && !(data.cardLast4?.isEmpty ?? true) }
    private var hasVault: Bool { data.vaultId != nil && !(data.vaultId?.isEmpty ?? true) }

    var body: some View {
        if hasCard && hasVault {
            // 2-column: card left, vault right, matched height
            HStack(alignment: .top, spacing: 12) {
                CreditCardVisual(
                    name: data.cardName ?? "",
                    last4: data.cardLast4 ?? "",
                    expiry: data.cardExpiry ?? "",
                    cvv: data.cardCode
                )
                .frame(maxWidth: .infinity)

                VaultVisual(
                    name: data.vaultName ?? "Vault",
                    vaultId: data.vaultId ?? ""
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .fixedSize(horizontal: false, vertical: true)
        } else if hasCard {
            CreditCardVisual(
                name: data.cardName ?? "",
                last4: data.cardLast4 ?? "",
                expiry: data.cardExpiry ?? ""
            )
        } else if hasVault {
            VaultVisual(
                name: data.vaultName ?? "Vault",
                vaultId: data.vaultId ?? ""
            )
        } else {
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
