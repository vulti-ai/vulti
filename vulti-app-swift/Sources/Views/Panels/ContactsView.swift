import SwiftUI

/// Contacts list — matches ContactsView.svelte layout.
/// Filterable list with avatar initials, name, platform handles, tags.
struct ContactsView: View {
    @Environment(AppState.self) private var app
    @State private var contacts: [Contact] = []
    @State private var search = ""
    @State private var isLoading = false

    private var filtered: [Contact] {
        guard !search.isEmpty else { return contacts }
        let query = search.lowercased()
        return contacts.filter { contact in
            contact.name.lowercased().contains(query)
                || (contact.tags ?? []).contains { $0.lowercased().contains(query) }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Search bar
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(VultiTheme.inkMuted)
                TextField("Search contacts...", text: $search)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(VultiTheme.paperWarm)
            .overlay(alignment: .bottom) {
                Rectangle().fill(VultiTheme.border).frame(height: 1)
            }

            Divider()

            // Content
            if filtered.isEmpty && !isLoading {
                emptyState
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(filtered) { contact in
                            ContactRow(contact: contact)
                            Divider()
                        }
                    }
                }
            }
        }
        .onAppear { loadContacts() }
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "person.2")
                .font(.system(size: 28))
                .foregroundStyle(.quaternary)
            Text("No contacts yet")
                .font(.caption)
                .fontWeight(.medium)
                .foregroundStyle(VultiTheme.inkDim)
            Text("Contacts are built automatically from your interactions")
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkMuted)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func loadContacts() {
        isLoading = true
        Task {
            do {
                contacts = try await app.client.getContacts()
            } catch {
                contacts = []
            }
            isLoading = false
        }
    }
}

// MARK: - Contact Row

struct ContactRow: View {
    let contact: Contact

    private var formattedDate: String? {
        guard let ts = contact.lastInteraction else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: ts) ?? ISO8601DateFormatter().date(from: ts)
        guard let date else { return String(ts.prefix(10)) }

        let display = DateFormatter()
        display.dateStyle = .short
        return display.string(from: date)
    }

    var body: some View {
        HStack(spacing: 12) {
            // Avatar initial
            ZStack {
                Circle()
                    .fill(.quaternary)
                    .frame(width: 40, height: 40)
                Text(String(contact.name.prefix(1)).uppercased())
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(.tint)
            }

            // Name & platforms
            VStack(alignment: .leading, spacing: 3) {
                Text(contact.name)
                    .font(.system(size: 13, weight: .medium))

                if let platforms = contact.platforms, !platforms.isEmpty {
                    HStack(spacing: 8) {
                        ForEach(platforms, id: \.platform) { p in
                            Text("\(p.platform): \(p.handle)")
                                .font(.system(size: 10))
                                .foregroundStyle(VultiTheme.inkMuted)
                        }
                    }
                }
            }

            Spacer()

            // Date & tags
            VStack(alignment: .trailing, spacing: 4) {
                if let date = formattedDate {
                    Text(date)
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkMuted)
                }

                if let tags = contact.tags, !tags.isEmpty {
                    HStack(spacing: 4) {
                        ForEach(tags, id: \.self) { tag in
                            Text(tag)
                                .font(.system(size: 9))
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(.quaternary, in: Capsule())
                                .foregroundStyle(VultiTheme.inkDim)
                        }
                    }
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .contentShape(Rectangle())
    }
}
