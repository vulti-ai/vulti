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
    @State private var lastWidgetCount = 0

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

    /// Widget size as a fraction of container width
    private func widgetFraction(_ widget: PaneWidget) -> CGFloat {
        switch widget.data.size {
        case "small": return 1.0 / 3.0
        case "medium": return 2.0 / 3.0
        default: return 1.0 // "large" or nil = full width
        }
    }

    /// Group widgets into rows based on their size fractions.
    /// Widgets that fit together (sum <= 1.0) share a row.
    private var widgetRows: [[PaneWidget]] {
        var rows: [[PaneWidget]] = []
        var currentRow: [PaneWidget] = []
        var currentWidth: CGFloat = 0

        for widget in widgets {
            let fraction = widgetFraction(widget)
            if currentWidth + fraction > 1.001 && !currentRow.isEmpty {
                rows.append(currentRow)
                currentRow = [widget]
                currentWidth = fraction
            } else {
                currentRow.append(widget)
                currentWidth += fraction
            }
            // Full-width widgets always get their own row
            if fraction >= 1.0 {
                rows.append(currentRow)
                currentRow = []
                currentWidth = 0
            }
        }
        if !currentRow.isEmpty { rows.append(currentRow) }
        return rows
    }

    private var widgetList: some View {
        GeometryReader { geo in
            let totalWidth = geo.size.width - 32 // account for padding
            ScrollView {
                VStack(spacing: 10) {
                    ForEach(Array(widgetRows.enumerated()), id: \.offset) { _, row in
                        HStack(spacing: 10) {
                            ForEach(row) { widget in
                                let fraction = widgetFraction(widget)
                                let cardWidth = fraction >= 1.0
                                    ? totalWidth
                                    : (totalWidth * fraction - (fraction < 1.0 ? 5 : 0))
                                widgetCard(widget)
                                    .frame(width: cardWidth)
                                    .transition(
                                        .asymmetric(
                                            insertion: .move(edge: .trailing).combined(with: .opacity),
                                            removal: .opacity
                                        )
                                    )
                            }
                        }
                    }
                }
                .padding(16)
                .animation(.spring(duration: 0.3), value: widgets.count)
            }
        }
    }

    // MARK: - Widget Card

    /// Renders a widget card with drag handle (top-left) and close button (top-right).
    /// Drill-target widgets get a chevron on the title row and tap handler.
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
            .padding(.bottom, 0)

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
                    .padding(.top, widget.title == nil ? 0 : 0)
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

    /// Remove a widget: delete from backend then drop from local state.
    private func removeWidget(_ widget: PaneWidget) {
        let widgetId = widget.id
        // Remove from backend first
        Task {
            try? await app.client.removePaneWidget(agentId: agentId, widgetId: widgetId)
        }
        // Remove from local state immediately
        withAnimation(.easeOut(duration: 0.2)) {
            widgets.removeAll { $0.id == widgetId }
        }
    }

    /// Widget content without the title (used when we render title + chevron separately)
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
            // Back button
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

            // Embedded detail view
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

    private func loadWidgets() async {
        do {
            let pane = try await app.client.getPaneWidgets(agentId: agentId)
            var all: [GatewayClient.PaneWidget] = []
            if let tabs = pane.tabs {
                // Flatten all tabs, preserving order
                for (_, tabWidgets) in tabs.sorted(by: { $0.key < $1.key }) {
                    all.append(contentsOf: tabWidgets)
                }
            }
            let converted = all.compactMap { $0.toPaneWidget() }

            // Only update if changed
            if converted.count != widgets.count || !widgetsEqual(converted, widgets) {
                withAnimation(.spring(duration: 0.3)) {
                    widgets = converted
                }
            }

            // Signal to parent that scratch pad has content
            if !converted.isEmpty && !hasContent {
                hasContent = true
            }
        } catch {
            // No widgets available yet — that's fine during onboarding
        }
    }

    /// Simple equality check by count + titles to avoid unnecessary re-renders
    private func widgetsEqual(_ a: [PaneWidget], _ b: [PaneWidget]) -> Bool {
        guard a.count == b.count else { return false }
        for i in a.indices {
            if a[i].title != b[i].title || a[i].type != b[i].type {
                return false
            }
        }
        return true
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

    /// Send a message to the agent via the chat (used by interactive widgets)
    private func sendChatMessage(_ message: String) {
        // Interactive widget messages go through the chat — the ChatView
        // picks them up via its WebSocket. For now this is a no-op placeholder;
        // the WidgetView onSendMessage callbacks are wired but need a shared
        // message bus or NotificationCenter post to reach the ChatView.
        NotificationCenter.default.post(
            name: .scratchPadMessage,
            object: nil,
            userInfo: ["message": message, "agentId": agentId]
        )
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
