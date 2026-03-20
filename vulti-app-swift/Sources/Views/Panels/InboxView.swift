import SwiftUI

/// Inbox message list — matches InboxView.svelte layout.
/// Shows messages from connected platforms with platform dot, sender, timestamp, preview.
struct InboxView: View {
    @Environment(AppState.self) private var app
    @State private var items: [InboxItem] = []
    @State private var isLoading = false

    var body: some View {
        VStack(spacing: 0) {
            // Content
            if items.isEmpty && !isLoading {
                emptyState
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(items) { item in
                            InboxItemRow(item: item)
                            Divider()
                        }
                    }
                }
            }
        }
        .onAppear { loadInbox() }
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "tray")
                .font(.system(size: 28))
                .foregroundStyle(.quaternary)
            Text("No messages yet")
                .font(.caption)
                .fontWeight(.medium)
                .foregroundStyle(VultiTheme.inkDim)
            Text("Messages from connected platforms will appear here")
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkMuted)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    func loadInbox() {
        isLoading = true
        Task {
            do {
                items = try await app.client.getInbox()
            } catch {
                items = []
            }
            isLoading = false
        }
    }
}

// MARK: - Inbox Item Row

struct InboxItemRow: View {
    let item: InboxItem

    private var platformColor: Color {
        switch (item.source ?? "").lowercased() {
        case "email": .blue
        case "whatsapp": .green
        case "telegram": .cyan
        case "discord": .indigo
        case "slack": .purple
        case "signal": .blue
        default: .secondary
        }
    }

    private var timeAgo: String {
        guard let ts = item.timestamp else { return "" }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: ts) ?? ISO8601DateFormatter().date(from: ts)
        guard let date else { return String(ts.prefix(10)) }

        let diff = Date.now.timeIntervalSince(date)
        let mins = Int(diff / 60)
        if mins < 60 { return "\(mins)m ago" }
        let hrs = mins / 60
        if hrs < 24 { return "\(hrs)h ago" }
        return "\(hrs / 24)d ago"
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Platform indicator
            VStack(spacing: 4) {
                Circle()
                    .fill(platformColor)
                    .frame(width: 8, height: 8)
                Text((item.source ?? "").uppercased())
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(VultiTheme.inkDim)
            }
            .frame(width: 40)

            // Message content
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(item.sender ?? "Unknown")
                        .font(.system(size: 13, weight: .medium))

                    Text(timeAgo)
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkMuted)

                    if item.read == false {
                        Circle()
                            .fill(.tint)
                            .frame(width: 6, height: 6)
                    }
                }

                if let preview = item.preview, !preview.isEmpty {
                    Text(preview)
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkDim)
                        .lineLimit(2)
                }
            }

            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .opacity(item.read == true ? 0.6 : 1.0)
        .contentShape(Rectangle())
    }
}
