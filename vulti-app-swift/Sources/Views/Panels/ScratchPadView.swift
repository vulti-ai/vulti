import SwiftUI

// MARK: - Drill-down target enum

/// Known detail views a widget can drill into via the "drill" field in WidgetData.
enum DrillTarget: String {
    case role, soul, user, memories, connections, skills, actions, wallet, analytics

    var contextLabel: String { rawValue }
}

// MARK: - ScratchPadView

/// Agent-driven scratch pad that renders dynamic widgets from getPaneWidgets.
/// The agent decides what widgets to show, can reorder/add/remove them at any time.
/// Widgets with a `drill` field show a chevron and tap into known CRUD detail views.
struct ScratchPadView: View {
    let agentId: String
    @Binding var expandedWidget: DrillTarget?
    @Binding var hasContent: Bool

    @Environment(AppState.self) private var app

    @State private var widgets: [PaneWidget] = []
    @State private var pollTimer: Timer?
    /// IDs of widgets the user deleted — polling ignores these until next full reload
    @State private var deletedIds: Set<String> = []
    /// Temporarily suppress polling during drag/delete operations
    @State private var suppressPoll = false
    /// The widget currently being dragged
    @State private var draggingWidget: PaneWidget?

    var body: some View {
        Group {
            if let drill = expandedWidget {
                drillDownView(for: drill)
            } else {
                widgetList
            }
        }
        .onAppear {
            Task { await loadWidgets() }
            startPolling()
        }
        .onDisappear {
            stopPolling()
        }
    }

    // MARK: - Widget List

    private var widgetList: some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                // Reset defaults button
                HStack {
                    Spacer()
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
                .padding(.bottom, 4)

                ForEach(widgets) { widget in
                    widgetCard(widget)
                        .opacity(draggingWidget?.id == widget.id ? 0.4 : 1.0)
                        .onDrag {
                            draggingWidget = widget
                            suppressPoll = true
                            return NSItemProvider(object: widget.id as NSString)
                        }
                        .onDrop(of: [.text], delegate: WidgetDropDelegate(
                            targetWidget: widget,
                            widgets: $widgets,
                            draggingWidget: $draggingWidget,
                            onReorder: saveOrder
                        ))
                }
            }
            .padding(16)
            .animation(.spring(duration: 0.25), value: widgets.map(\.id))
        }
    }

    // MARK: - Widget Card

    private func widgetCard(_ widget: PaneWidget) -> some View {
        let drillTarget = widget.data.drill.flatMap { DrillTarget(rawValue: $0) }

        return VStack(alignment: .leading, spacing: 0) {
            // Top bar: drag handle (left) + close button (right)
            HStack(spacing: 0) {
                // Drag handle — three horizontal lines
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

                // Close / delete button
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
        // Track as deleted so polling doesn't bring it back
        deletedIds.insert(widgetId)
        // Suppress polling briefly
        suppressPoll = true
        // Remove from local state
        withAnimation(.easeOut(duration: 0.2)) {
            widgets.removeAll { $0.id == widgetId }
        }
        // Remove from backend
        Task {
            try? await app.client.removePaneWidget(agentId: agentId, widgetId: widgetId)
            // Re-enable polling after backend confirms
            try? await Task.sleep(for: .milliseconds(500))
            suppressPoll = false
        }
    }

    // MARK: - Reset Defaults

    private func resetDefaults() {
        suppressPoll = true
        deletedIds.removeAll()
        // Clear local widgets first so loadWidgetsForced sees a diff and does a full replace
        withAnimation(.spring(duration: 0.3)) { widgets = [] }
        Task {
            do {
                _ = try await app.client.resetDefaultWidgets(agentId: agentId)
                try? await Task.sleep(for: .milliseconds(200))
                await loadWidgetsForced()
            } catch {
                // Silently fail
            }
            suppressPoll = false
        }
    }

    // MARK: - Reorder

    private func saveOrder() {
        let ids = widgets.map(\.id)
        suppressPoll = true
        Task {
            try? await app.client.reorderPaneWidgets(agentId: agentId, widgetIds: ids)
            // Re-fetch from backend to confirm the new order is persisted
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
            KvWidgetContent(data: widget.data)
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
        case .soul, .user, .memories:
            AgentProfileTab(agentId: agentId)
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

    /// Fetch widgets from backend. Called by poll timer — skips if suppressed.
    private func loadWidgets() async {
        guard !suppressPoll else { return }
        await loadWidgetsForced()
    }

    /// Fetch widgets from backend unconditionally.
    private func loadWidgetsForced() async {
        do {
            let pane = try await app.client.getPaneWidgets(agentId: agentId)
            var all: [GatewayClient.PaneWidget] = []
            if let tabs = pane.tabs {
                for (_, tabWidgets) in tabs.sorted(by: { $0.key < $1.key }) {
                    all.append(contentsOf: tabWidgets)
                }
            }
            var converted = all.compactMap { $0.toPaneWidget() }

            // Filter out widgets the user deleted locally
            if !deletedIds.isEmpty {
                converted = converted.filter { !deletedIds.contains($0.id) }
            }

            // Check if the widget set changed (new/removed widgets) vs just reorder
            let newIdSet = Set(converted.map(\.id))
            let currentIdSet = Set(widgets.map(\.id))

            if newIdSet != currentIdSet {
                // Widgets added or removed — full replace
                withAnimation(.spring(duration: 0.3)) {
                    widgets = converted
                }
            } else if converted.map(\.id) != widgets.map(\.id) {
                // Same widgets but different order from backend — accept backend order
                withAnimation(.spring(duration: 0.3)) {
                    widgets = converted
                }
            }
            // If same IDs in same order — don't touch (preserves local state)

            if !converted.isEmpty && !hasContent {
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
