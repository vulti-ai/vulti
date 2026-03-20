import SwiftUI

/// Audit log with event type badges, agent/event filters.
/// Loads from gateway via GatewayClient.
struct AuditView: View {
    @Environment(AppState.self) private var app
    @State private var events: [GatewayClient.AuditEventResponse] = []
    @State private var agentFilter = "All"
    @State private var eventFilter = "All"
    @State private var platformFilter = "All"
    @State private var isLoading = false
    @State private var expandedEventIds: Set<String> = []

    /// Unique event types extracted from loaded events
    private var eventTypes: [String] {
        Array(Set(events.compactMap(\.event))).sorted()
    }

    /// Unique platforms extracted from loaded events
    private var platforms: [String] {
        Array(Set(events.compactMap(\.platform))).sorted()
    }

    var body: some View {
        VStack(spacing: 0) {
            // Filters
            HStack(spacing: 12) {
                Picker("Agent", selection: $agentFilter) {
                    Text("All agents").tag("All")
                    ForEach(app.agentList) { agent in
                        Text(agent.name).tag(agent.id)
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: 160)

                Picker("Event", selection: $eventFilter) {
                    Text("All events").tag("All")
                    ForEach(eventTypes, id: \.self) { type in
                        Text(AuditEventType(rawValue: type)?.label ?? type).tag(type)
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: 160)

                Picker("Platform", selection: $platformFilter) {
                    Text("All platforms").tag("All")
                    ForEach(platforms, id: \.self) { platform in
                        Text(platform).tag(platform)
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: 160)

                Spacer()

                Button { loadEvents() } label: {
                    Image(systemName: "arrow.clockwise")
                        .rotationEffect(isLoading ? .degrees(360) : .degrees(0))
                        .animation(isLoading ? .linear(duration: 1).repeatForever(autoreverses: false) : .default, value: isLoading)
                }
                .buttonStyle(.plain)
            }
            .padding(16)

            Divider()

            // Events list
            if filteredEvents.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "doc.text.magnifyingglass")
                        .font(.system(size: 28))
                        .foregroundStyle(VultiTheme.inkMuted)
                    Text("No audit events")
                        .font(.system(size: 11)).foregroundStyle(VultiTheme.inkDim)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(filteredEvents) { event in
                            AuditEventRow(
                                event: event,
                                agentName: agentName(for: event.agentId ?? ""),
                                isExpanded: expandedEventIds.contains(event.id),
                                onToggle: { toggleExpanded(event.id) }
                            )
                            Divider()
                        }
                    }
                }
            }
        }
        .onAppear { loadEvents() }
        .onChange(of: agentFilter) { _, _ in loadEvents() }
        .onChange(of: eventFilter) { _, _ in loadEvents() }
    }

    private var filteredEvents: [GatewayClient.AuditEventResponse] {
        if platformFilter == "All" { return events }
        return events.filter { $0.platform == platformFilter }
    }

    private func loadEvents() {
        isLoading = true
        Task {
            events = (try? await app.client.listAuditEvents(
                n: 200,
                agentId: agentFilter == "All" ? nil : agentFilter,
                eventType: eventFilter == "All" ? nil : eventFilter
            )) ?? []
            isLoading = false
        }
    }

    private func agentName(for id: String) -> String {
        app.agent(byId: id)?.name ?? id
    }

    private func toggleExpanded(_ id: String) {
        if expandedEventIds.contains(id) {
            expandedEventIds.remove(id)
        } else {
            expandedEventIds.insert(id)
        }
    }
}

// MARK: - Event Row

struct AuditEventRow: View {
    let event: GatewayClient.AuditEventResponse
    let agentName: String
    let isExpanded: Bool
    let onToggle: () -> Void

    private var badgeColor: Color {
        switch event.event ?? "" {
        case "message_received": .blue
        case "message_response": .cyan
        case "interagent_send": .indigo
        case "interagent_receive": .purple
        case "cron_execute": .orange
        case "rule_trigger": .mint
        case "permission_request": .orange
        case "permission_approved": .green
        case "permission_denied": .red
        default: VultiTheme.inkDim
        }
    }

    private var formattedTimestamp: String {
        guard let ts = event.ts else { return "" }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: ts)
            ?? ISO8601DateFormatter().date(from: ts)

        guard let date else { return String(ts.prefix(19)) }

        let display = DateFormatter()
        if Calendar.current.isDateInToday(date) {
            display.dateFormat = "HH:mm:ss"
        } else {
            display.dateFormat = "MMM d HH:mm"
        }
        return display.string(from: date)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .center, spacing: 8) {
                // Event type badge
                Text(AuditEventType(rawValue: event.event ?? "")?.label
                     ?? (event.event ?? "").replacingOccurrences(of: "_", with: " "))
                    .font(.system(size: 9, weight: .bold))
                    .textCase(.uppercase)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(badgeColor.opacity(0.15), in: Capsule())
                    .foregroundStyle(badgeColor)

                // Agent name
                Text(agentName)
                    .font(.system(size: 11, weight: .medium))

                // Detail summary (target, sender, connection, etc.)
                if !event.detailSummary.isEmpty {
                    Text(event.detailSummary)
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkDim)
                }

                // Platform tag
                if let platform = event.platform {
                    Text(platform)
                        .font(.system(size: 9, weight: .medium))
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(VultiTheme.paperDeep, in: RoundedRectangle(cornerRadius: 3))
                        .foregroundStyle(VultiTheme.inkDim)
                }

                Spacer()

                // Timestamp
                Text(formattedTimestamp)
                    .font(.system(size: 10).monospacedDigit())
                    .foregroundStyle(VultiTheme.inkMuted)
            }

            // Message preview
            if let preview = event.messagePreview {
                Text(String(preview.prefix(120)).replacingOccurrences(of: "\n", with: " "))
                    .font(.system(size: 10))
                    .foregroundStyle(VultiTheme.inkMuted)
                    .lineLimit(1)
            }

            // Trace ID
            if let traceId = event.traceId {
                Text("trace:\(String(traceId.prefix(12)))")
                    .font(.system(size: 9).monospaced())
                    .foregroundStyle(VultiTheme.inkMuted)
            }

            // Expandable details
            if isExpanded, let details = event.details, !details.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(details.sorted(by: { $0.key < $1.key }), id: \.key) { key, value in
                        HStack(alignment: .top, spacing: 4) {
                            Text(key)
                                .font(.system(size: 9, weight: .medium).monospaced())
                                .foregroundStyle(VultiTheme.inkDim)
                            Text(String(describing: value.value))
                                .font(.system(size: 9).monospaced())
                                .foregroundStyle(VultiTheme.inkMuted)
                                .lineLimit(3)
                        }
                    }
                }
                .padding(8)
                .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 6))
                .padding(.top, 4)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .contentShape(Rectangle())
        .onTapGesture { onToggle() }
    }
}

// MARK: - Event Type Enum

enum AuditEventType: String, CaseIterable {
    case messageReceived = "message_received"
    case messageResponse = "message_response"
    case interagentSend = "interagent_send"
    case interagentReceive = "interagent_receive"
    case cronExecute = "cron_execute"
    case ruleTrigger = "rule_trigger"
    case permissionRequest = "permission_request"
    case permissionApproved = "permission_approved"
    case permissionDenied = "permission_denied"

    var label: String {
        switch self {
        case .messageReceived: "Owner Msg"
        case .messageResponse: "Agent Reply"
        case .interagentSend: "Agent Send"
        case .interagentReceive: "Agent Recv"
        case .cronExecute: "Cron"
        case .ruleTrigger: "Rule"
        case .permissionRequest: "Perm Req"
        case .permissionApproved: "Approved"
        case .permissionDenied: "Denied"
        }
    }
}
