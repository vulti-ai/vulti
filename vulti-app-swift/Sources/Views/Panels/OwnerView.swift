import SwiftUI

/// Owner panel — name, about, Matrix account management.
/// Matches SlideOutPanel.svelte owner mode.
struct OwnerView: View {
    @Environment(AppState.self) private var app
    @State private var name = ""
    @State private var about = ""
    @State private var avatar = ""
    @State private var matrixUsername = ""
    @State private var matrixPassword = ""
    @State private var matrixInfo: [String: String] = [:]
    @State private var matrixConnected = false
    @State private var matrixStatus = ""
    @State private var isCreatingMatrix = false
    @State private var isResettingRooms = false
    @State private var showResetConfirmation = false

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Avatar
            HStack(spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 12)
                        .fill(VultiTheme.paperDeep)
                        .frame(width: 64, height: 64)

                    if !avatar.isEmpty,
                       let data = Data(base64Encoded: avatar),
                       let img = NSImage(data: data) {
                        Image(nsImage: img)
                            .resizable()
                            .frame(width: 64, height: 64)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                    } else {
                        Image(systemName: "person.fill")
                            .font(.system(size: 24))
                            .foregroundStyle(VultiTheme.inkMuted)
                    }
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("Avatar").font(.system(size: 13, weight: .medium)).foregroundStyle(VultiTheme.inkDim)
                    Text("Set via agent avatar generation or manually")
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkMuted)
                }
            }

            // Name
            VStack(alignment: .leading, spacing: 4) {
                Text("Name").font(.system(size: 13, weight: .medium)).foregroundStyle(VultiTheme.inkDim)
                TextField("Your name", text: $name)
                    .textFieldStyle(.vulti)
                    .onSubmit { save() }
            }

            // About
            VStack(alignment: .leading, spacing: 4) {
                Text("About").font(.system(size: 13, weight: .medium)).foregroundStyle(VultiTheme.inkDim)
                TextEditor(text: $about)
                    .frame(minHeight: 60)
                    .font(.system(size: 13))
                    .foregroundStyle(VultiTheme.inkSoft)
                    .scrollContentBackground(.hidden)
                    .padding(4)
                    .background(VultiTheme.paperDeep, in: RoundedRectangle(cornerRadius: 6))
            }

            Button("Save") { save() }
                .buttonStyle(.vultiSecondary)

            Divider()

            // Matrix section
            VStack(alignment: .leading, spacing: 12) {
                Text("MATRIX").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)

                // Connection status
                HStack(spacing: 8) {
                    Circle()
                        .fill(matrixConnected ? .green : VultiTheme.inkDim)
                        .frame(width: 8, height: 8)
                    Text(matrixConnected ? "Connected" : "Not configured")
                        .font(.system(size: 13, weight: .medium))
                }

                if !matrixInfo.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Label("Account created", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                            .font(.system(size: 13))

                        Group {
                            LabeledContent("Homeserver") { Text(matrixInfo["homeserver_url"] ?? "—").textSelection(.enabled) }
                            LabeledContent("Username") { Text(matrixInfo["owner_username"] ?? "—").textSelection(.enabled) }
                            LabeledContent("Password") { Text(matrixInfo["owner_password"] ?? "—").textSelection(.enabled) }
                        }
                        .font(.system(size: 12))
                    }
                    .padding(12)
                    .background(.green.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(.green.opacity(0.2)))

                    // Reset Rooms button
                    VStack(alignment: .leading, spacing: 6) {
                        Button {
                            showResetConfirmation = true
                        } label: {
                            HStack(spacing: 6) {
                                if isResettingRooms {
                                    ProgressView()
                                        .controlSize(.small)
                                }
                                Text("Reset Rooms")
                            }
                        }
                        .buttonStyle(.bordered)
                        .tint(.red)
                        .controlSize(.small)
                        .disabled(isResettingRooms)
                        .confirmationDialog(
                            "Reset all Matrix rooms?",
                            isPresented: $showResetConfirmation,
                            titleVisibility: .visible
                        ) {
                            Button("Reset Rooms", role: .destructive) {
                                resetRooms()
                            }
                        } message: {
                            Text("This will delete all existing Matrix rooms and recreate them from current relationships. This cannot be undone.")
                        }

                        if !matrixStatus.isEmpty {
                            Text(matrixStatus)
                                .font(.system(size: 11))
                                .foregroundStyle(matrixStatus.hasPrefix("Error") ? .red : VultiTheme.inkDim)
                        }
                    }
                } else {
                    TextField("Username", text: $matrixUsername)
                        .textFieldStyle(.vulti)
                    SecureField("Password (min 8 chars)", text: $matrixPassword)
                        .textFieldStyle(.vulti)

                    if !matrixStatus.isEmpty {
                        Text(matrixStatus)
                            .font(.system(size: 11))
                            .foregroundStyle(matrixStatus.hasPrefix("Error") ? .red : VultiTheme.inkDim)
                    }

                    Button {
                        createMatrixAccount()
                    } label: {
                        HStack(spacing: 6) {
                            if isCreatingMatrix {
                                ProgressView().controlSize(.small)
                            }
                            Text("Create Matrix Account")
                        }
                    }
                    .buttonStyle(.vultiPrimary)
                    .disabled(matrixUsername.isEmpty || matrixPassword.count < 8 || isCreatingMatrix)
                }
            }
        }
        .frame(maxWidth: 448)
        .task {
            await loadOwner()
            loadMatrixInfo()
        }
    }

    private func loadOwner() async {
        do {
            let owner = try await app.client.getOwner()
            name = owner.name ?? ""
            about = owner.about ?? ""
            avatar = owner.avatar ?? ""
        } catch {
            // Keep defaults on error
        }
    }

    private func save() {
        Task {
            try? await app.client.updateOwner(
                name: name.isEmpty ? "" : name,
                about: about.isEmpty ? nil : about
            )
        }
    }

    private func loadMatrixInfo() {
        let credsURL = VultiHome.continuwuityDir.appending(path: "owner_credentials.json")
        matrixConnected = VultiHome.fileExists(credsURL)

        let creds = VultiHome.readRawJSON(from: credsURL)
        if let creds {
            for (k, v) in creds {
                if let s = v as? String { matrixInfo[k] = s }
            }
        }
    }

    private func createMatrixAccount() {
        isCreatingMatrix = true
        matrixStatus = "Creating account..."
        Task {
            do {
                try await app.client.registerMatrix(
                    username: matrixUsername,
                    password: matrixPassword
                )
                matrixStatus = ""
                matrixUsername = ""
                matrixPassword = ""
                loadMatrixInfo()
            } catch {
                matrixStatus = "Error: \(error.localizedDescription)"
            }
            isCreatingMatrix = false
        }
    }

    private func resetRooms() {
        isResettingRooms = true
        matrixStatus = "Resetting rooms..."
        Task {
            do {
                try await app.client.resetMatrixRooms()
                matrixStatus = "Rooms reset successfully"
            } catch {
                matrixStatus = "Error: \(error.localizedDescription)"
            }
            isResettingRooms = false
        }
    }
}

/// Settings panel with General + Connections subtabs.
struct SettingsView: View {
    @State private var subtab = "General"

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                ForEach(["General", "Connections"], id: \.self) { tab in
                    Button {
                        subtab = tab
                    } label: {
                        Text(tab)
                            .font(.system(size: 13, weight: .medium))
                            .padding(.vertical, 10)
                            .padding(.horizontal, 16)
                            .overlay(alignment: .bottom) {
                                if subtab == tab {
                                    Rectangle().fill(.tint).frame(height: 2)
                                }
                            }
                            .foregroundStyle(subtab == tab ? VultiTheme.inkSoft : VultiTheme.inkDim)
                    }
                    .buttonStyle(.plain)
                }
                Spacer()
            }
            .padding(.horizontal, 8)

            Divider()

            ScrollView {
                if subtab == "General" {
                    GeneralSettingsView().padding(24)
                } else {
                    ConnectionsSettingsView().padding(24)
                }
            }
        }
    }
}

struct GeneralSettingsView: View {
    @Environment(AppState.self) private var app
    @AppStorage("vulti_theme") private var themeRaw: String = "system"
    @State private var secrets: [GatewayClient.SecretResponse] = []
    @State private var providers: [GatewayClient.ProviderResponse] = []
    @State private var oauthStatuses: [GatewayClient.OAuthResponse] = []
    @State private var integrations: [GatewayClient.IntegrationResponse] = []
    @State private var pendingPermissions: [GatewayClient.PermissionResponse] = []
    @State private var newKeyType = "OpenRouter"
    @State private var newKeyValue = ""
    @State private var showAddKey = false

    /// Group integrations by category.
    private var integrationsByCategory: [(String, [GatewayClient.IntegrationResponse])] {
        Dictionary(grouping: integrations, by: { $0.category ?? "Other" })
            .sorted { $0.key < $1.key }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // ── Theme ──
            Section {
                Picker("Appearance", selection: $themeRaw) {
                    ForEach(ThemePreference.allCases, id: \.rawValue) { pref in
                        Text(pref.label).tag(pref.rawValue)
                    }
                }
                .pickerStyle(.segmented)
                .frame(maxWidth: 260)
            } header: {
                Text("THEME").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
            }

            Divider()

            // ── Gateway Control ──
            Section {
                HStack {
                    Circle()
                        .fill(app.isGatewayRunning ? .green : .red)
                        .frame(width: 8, height: 8)
                    Text(app.isGatewayRunning ? "Running" : "Stopped")
                        .font(.system(size: 13, weight: .medium))
                    Spacer()
                    Button(app.isGatewayRunning ? "Stop" : "Start") {
                        Task {
                            if app.isGatewayRunning {
                                await app.stopGateway()
                            } else {
                                try? await app.startGateway()
                            }
                        }
                    }
                    .buttonStyle(.vultiPrimary)
                    .tint(app.isGatewayRunning ? .red : .green)
                    .controlSize(.small)
                }
            } header: {
                Text("GATEWAY").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
            }

            Divider()

            // ── Permissions ──
            Section {
                if pendingPermissions.isEmpty {
                    Text("No pending requests")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                } else {
                    ForEach(pendingPermissions, id: \.id) { req in
                        HStack(spacing: 10) {
                            VStack(alignment: .leading, spacing: 2) {
                                HStack(spacing: 4) {
                                    if let agentId = req.agentId,
                                       let agent = app.agent(byId: agentId) {
                                        Text(agent.name)
                                            .font(.system(size: 13, weight: .medium))
                                    } else if let agentId = req.agentId {
                                        Text(agentId)
                                            .font(.system(size: 13, weight: .medium))
                                    }
                                    if let conn = req.connectionName {
                                        Text(conn)
                                            .font(.system(size: 11))
                                            .padding(.horizontal, 5)
                                            .padding(.vertical, 1)
                                            .background(VultiTheme.paperDeep, in: Capsule())
                                    }
                                }
                                if let reason = req.reason, !reason.isEmpty {
                                    Text(reason)
                                        .font(.system(size: 11))
                                        .foregroundStyle(VultiTheme.inkDim)
                                        .lineLimit(2)
                                }
                            }
                            Spacer()
                            Button {
                                resolvePermission(req.id, approved: true)
                            } label: {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.system(size: 18))
                                    .foregroundStyle(.green)
                            }
                            .buttonStyle(.plain)
                            .help("Approve")

                            Button {
                                resolvePermission(req.id, approved: false)
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .font(.system(size: 18))
                                    .foregroundStyle(.red)
                            }
                            .buttonStyle(.plain)
                            .help("Deny")
                        }
                    }
                }
            } header: {
                HStack(spacing: 6) {
                    Text("PERMISSIONS").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
                    if !pendingPermissions.isEmpty {
                        Text("\(pendingPermissions.count)")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(.orange, in: Capsule())
                    }
                }
            }

            Divider()

            // ── OAuth Status ──
            if !oauthStatuses.isEmpty {
                Section {
                    ForEach(oauthStatuses, id: \.service) { oauth in
                        HStack {
                            Text(oauth.service)
                                .font(.system(size: 13, weight: .medium))
                            if let scopes = oauth.scopes {
                                Text("\(scopes.count) scopes")
                                    .font(.system(size: 10))
                                    .foregroundStyle(VultiTheme.inkDim)
                            }
                            Spacer()
                            if oauth.hasRefresh == true {
                                Text("Refresh")
                                    .font(.system(size: 10))
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(.blue.opacity(0.1), in: Capsule())
                                    .foregroundStyle(.blue)
                            }
                            Text(oauth.valid ? "Connected" : "Disconnected")
                                .font(.system(size: 10))
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(oauth.valid ? .green.opacity(0.1) : .red.opacity(0.1), in: Capsule())
                                .foregroundStyle(oauth.valid ? .green : .red)
                        }
                    }
                } header: {
                    Text("OAUTH TOKENS").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
                }

                Divider()
            }

            // ── Integrations Status ──
            if !integrations.isEmpty {
                ForEach(integrationsByCategory, id: \.0) { category, items in
                    Section {
                        ForEach(items, id: \.id) { integ in
                            HStack {
                                Circle()
                                    .fill(integrationStatusColor(integ.status ?? "unknown"))
                                    .frame(width: 8, height: 8)
                                Text(integ.name)
                                    .font(.system(size: 13, weight: .medium))
                                Spacer()
                                Text((integ.status ?? "unknown").capitalized)
                                    .font(.system(size: 10))
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(integrationStatusColor(integ.status ?? "unknown").opacity(0.1), in: Capsule())
                                    .foregroundStyle(integrationStatusColor(integ.status ?? "unknown"))
                            }
                        }
                    } header: {
                        Text(category.uppercased()).font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
                    }
                }

                Divider()
            }

            // ── Providers ──
            Section {
                ForEach(providers, id: \.id) { provider in
                    HStack {
                        Circle()
                            .fill(provider.authenticated ? .green : VultiTheme.inkDim)
                            .frame(width: 8, height: 8)
                        Text(provider.name)
                            .font(.system(size: 13, weight: .medium))
                        Spacer()
                        Text(provider.authenticated ? "Connected" : "Not configured")
                            .font(.system(size: 11))
                            .foregroundStyle(VultiTheme.inkDim)
                    }
                }
            } header: {
                Text("PROVIDERS").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
            }

            Divider()

            // API Keys
            Section {
                ForEach(secrets, id: \.key) { secret in
                    HStack {
                        Text(secret.key)
                            .font(.system(size: 12))
                            .monospaced()
                        Spacer()
                        Text(secret.maskedValue ?? "***")
                            .font(.system(size: 11))
                            .foregroundStyle(VultiTheme.inkDim)
                        Button(role: .destructive) {
                            Task {
                                try? await app.client.deleteSecret(key: secret.key)
                                await reload()
                            }
                        } label: {
                            Image(systemName: "trash")
                                .font(.system(size: 11))
                        }
                        .buttonStyle(.plain)
                    }
                }

                if showAddKey {
                    VStack(alignment: .leading, spacing: 8) {
                        Picker("Type", selection: $newKeyType) {
                            ForEach(["OpenRouter", "Anthropic", "OpenAI", "DeepSeek", "Google"], id: \.self) { Text($0) }
                        }
                        SecureField("API Key", text: $newKeyValue)
                            .textFieldStyle(.vulti)
                        HStack {
                            Button("Cancel") { showAddKey = false; newKeyValue = "" }
                            Button("Save") {
                                let key = keyForType(newKeyType)
                                Task {
                                    try? await app.client.addSecret(key: key, value: newKeyValue)
                                    showAddKey = false; newKeyValue = ""
                                    await reload()
                                }
                            }
                            .buttonStyle(.vultiPrimary)
                            .disabled(newKeyValue.isEmpty)
                        }
                    }
                } else {
                    Button("Add API Key") { showAddKey = true }
                        .font(.system(size: 12))
                }
            } header: {
                Text("API KEYS").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
            }
        }
        .task { await reload() }
    }

    private func reload() async {
        do { secrets = try await app.client.listSecrets() } catch {}
        do { providers = try await app.client.listProviders() } catch {}
        do { oauthStatuses = try await app.client.oauthStatus() } catch {}
        do { integrations = try await app.client.listIntegrations() } catch {}
        do { pendingPermissions = try await app.client.listPermissions() } catch {}
    }

    private func resolvePermission(_ id: String, approved: Bool) {
        Task {
            try? await app.client.resolvePermission(requestId: id, approved: approved)
            do { pendingPermissions = try await app.client.listPermissions() } catch {}
        }
    }

    private func integrationStatusColor(_ status: String) -> Color {
        switch status {
        case "connected": .green
        case "degraded": .yellow
        case "configured": .blue
        default: .red
        }
    }

    private func keyForType(_ type: String) -> String {
        switch type {
        case "Anthropic": "ANTHROPIC_API_KEY"
        case "OpenAI": "OPENAI_API_KEY"
        case "DeepSeek": "DEEPSEEK_API_KEY"
        case "Google": "GOOGLE_API_KEY"
        default: "OPENROUTER_API_KEY"
        }
    }
}

struct ConnectionsSettingsView: View {
    @Environment(AppState.self) private var app
    @State private var connections: [GatewayClient.ConnectionResponse] = []

    // Form state
    @State private var showForm = false
    @State private var editingName: String?  // nil = adding new, non-nil = editing existing
    @State private var formName = ""
    @State private var formType = "api_key"
    @State private var formDescription = ""
    @State private var formTags = ""
    @State private var formEnabled = true

    // Delete confirmation
    @State private var deleteTarget: String?

    @State private var error: String?

    private let connectionTypes = ["api_key", "mcp", "oauth", "custom"]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Add button
            if !showForm {
                Button {
                    resetForm()
                    editingName = nil
                    showForm = true
                } label: {
                    Text("Add Connection")
                }
                .buttonStyle(.vultiSecondary)
            }

            // Inline form (add / edit)
            if showForm {
                connectionForm
            }

            // Connection list
            ForEach(connections, id: \.name) { conn in
                connectionRow(conn)
                Divider()
            }

            if connections.isEmpty && !showForm {
                VStack(alignment: .leading, spacing: 4) {
                    Text("No connections yet.")
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkDim)
                    Text("Add API keys, MCP servers, and other integrations.")
                        .font(.system(size: 10))
                        .foregroundStyle(VultiTheme.inkMuted)
                }
            }
        }
        .task { await reload() }
    }

    // MARK: - Connection Row

    private func connectionRow(_ conn: GatewayClient.ConnectionResponse) -> some View {
        HStack(spacing: 8) {
            Circle()
                .fill(conn.enabled != false ? .green : VultiTheme.inkDim)
                .frame(width: 8, height: 8)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(conn.name)
                        .font(.system(size: 13, weight: .medium))
                    if let type = conn.type {
                        Text(typeLabel(type))
                            .font(.system(size: 10))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(VultiTheme.paperDeep, in: Capsule())
                    }
                    if let tags = conn.tags {
                        ForEach(tags, id: \.self) { tag in
                            Text(tag)
                                .font(.system(size: 10))
                                .padding(.horizontal, 5)
                                .padding(.vertical, 1)
                                .background(.blue.opacity(0.1), in: Capsule())
                                .foregroundStyle(.blue)
                        }
                    }
                }
                if let desc = conn.description, !desc.isEmpty {
                    Text(desc)
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkDim)
                        .lineLimit(1)
                }
            }

            Spacer()

            // Enable/disable toggle
            Toggle("", isOn: Binding(
                get: { conn.enabled != false },
                set: { newValue in toggleConnection(conn.name, enabled: newValue) }
            ))
            .toggleStyle(.switch)
            .controlSize(.mini)
            .labelsHidden()

            // Edit button
            Button {
                populateForm(from: conn)
            } label: {
                Image(systemName: "pencil")
                    .font(.system(size: 11))
                    .foregroundStyle(VultiTheme.inkDim)
            }
            .buttonStyle(.plain)
            .help("Edit")

            // Delete button
            if deleteTarget == conn.name {
                Button("Cancel") { deleteTarget = nil }
                    .font(.system(size: 10))
                    .foregroundStyle(VultiTheme.inkDim)
                Button("Confirm") {
                    deleteConnection(conn.name)
                    deleteTarget = nil
                }
                .font(.system(size: 10))
                .foregroundStyle(.red)
            } else {
                Button {
                    deleteTarget = conn.name
                } label: {
                    Image(systemName: "trash")
                        .font(.system(size: 11))
                        .foregroundStyle(.red.opacity(0.7))
                }
                .buttonStyle(.plain)
                .help("Delete")
            }
        }
    }

    // MARK: - Form

    private var connectionForm: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(editingName == nil ? "New Connection" : "Edit Connection")
                .font(.system(size: 12, weight: .semibold))

            // Name + Type row
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Name").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkDim)
                    TextField("e.g. github", text: $formName)
                        .textFieldStyle(.vulti)
                        .font(.system(size: 12))
                        .disabled(editingName != nil)
                }
                VStack(alignment: .leading, spacing: 3) {
                    Text("Type").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkDim)
                    Picker("", selection: $formType) {
                        ForEach(connectionTypes, id: \.self) { t in
                            Text(typeLabel(t)).tag(t)
                        }
                    }
                    .labelsHidden()
                    .frame(maxWidth: 120)
                }
            }

            // Description
            VStack(alignment: .leading, spacing: 3) {
                Text("Description").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkDim)
                TextField("What this connection does", text: $formDescription)
                    .textFieldStyle(.vulti)
                    .font(.system(size: 12))
            }

            // Tags
            VStack(alignment: .leading, spacing: 3) {
                Text("Tags (comma-separated)").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkDim)
                TextField("e.g. web, search, code", text: $formTags)
                    .textFieldStyle(.vulti)
                    .font(.system(size: 12))
            }

            if let error {
                Text(error)
                    .font(.system(size: 11))
                    .foregroundStyle(.red)
            }

            // Save / Cancel
            HStack {
                Button("Cancel") {
                    showForm = false
                    self.error = nil
                }
                .font(.system(size: 12))

                Button(editingName == nil ? "Add Connection" : "Save Changes") {
                    saveConnection()
                }
                .buttonStyle(.vultiPrimary)
                .font(.system(size: 12))
                .disabled(formName.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(12)
        .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - Actions

    private func reload() async {
        do { connections = try await app.client.listConnections() } catch {}
    }

    private func saveConnection() {
        error = nil
        let trimmedName = formName.trimmingCharacters(in: .whitespaces)
        guard !trimmedName.isEmpty else { return }

        Task {
            do {
                if editingName != nil {
                    // Update existing
                    var updates: [String: String] = [:]
                    if !formDescription.isEmpty { updates["description"] = formDescription }
                    updates["enabled"] = formEnabled ? "true" : "false"
                    try await app.client.updateConnection(name: trimmedName, updates: updates)
                } else {
                    // Add new
                    try await app.client.addConnection(
                        name: trimmedName,
                        type: formType,
                        description: formDescription.isEmpty ? nil : formDescription
                    )
                }
                showForm = false
                await reload()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func deleteConnection(_ name: String) {
        Task {
            do {
                try await app.client.deleteConnection(name: name)
                await reload()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func toggleConnection(_ name: String, enabled: Bool) {
        Task {
            do {
                try await app.client.updateConnection(name: name, updates: ["enabled": enabled ? "true" : "false"])
                await reload()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func populateForm(from conn: GatewayClient.ConnectionResponse) {
        editingName = conn.name
        formName = conn.name
        formType = conn.type ?? "api_key"
        formDescription = conn.description ?? ""
        formTags = (conn.tags ?? []).joined(separator: ", ")
        formEnabled = conn.enabled != false
        error = nil
        showForm = true
    }

    private func resetForm() {
        formName = ""
        formType = "api_key"
        formDescription = ""
        formTags = ""
        formEnabled = true
        error = nil
    }

    private func typeLabel(_ t: String) -> String {
        switch t {
        case "mcp": "MCP"
        case "api_key": "API Key"
        case "oauth": "OAuth"
        case "custom": "Custom"
        default: t
        }
    }
}

/// Create agent wizard — tabbed form: Identity, Model, Communication, Permissions.
struct CreateAgentView: View {
    @Environment(AppState.self) private var app

    enum WizardTab: String, CaseIterable {
        case identity = "Identity"
        case model = "Model"
        case communication = "Communication"
        case permissions = "Permissions"
    }

    @State private var currentTab: WizardTab = .identity

    // Identity
    @State private var name = ""
    @State private var role = ""
    @State private var personality = ""

    // Model
    @State private var model = ""
    @State private var availableProviders: [GatewayClient.ProviderResponse] = []

    // Communication — selected connection names
    @State private var selectedConnections: Set<String> = []
    @State private var connections: [GatewayClient.ConnectionResponse] = []

    // Permissions
    @State private var readFiles = true
    @State private var readWeb = true
    @State private var writeFiles = false
    @State private var writeCode = false
    @State private var toolAccess = false

    @State private var error: String?

    /// Messaging-type connections for the Communication tab.
    private var messagingConnections: [GatewayClient.ConnectionResponse] {
        let messagingTypes: Set<String> = ["telegram", "discord", "slack", "matrix", "whatsapp", "signal", "email"]
        return connections.filter { conn in
            if let type = conn.type?.lowercased(), messagingTypes.contains(type) { return true }
            // Also match by name if type is missing
            let lower = conn.name.lowercased()
            return messagingTypes.contains(where: { lower.contains($0) })
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Tab bar
            HStack(spacing: 0) {
                ForEach(WizardTab.allCases, id: \.self) { tab in
                    Button {
                        currentTab = tab
                    } label: {
                        Text(tab.rawValue)
                            .font(.system(size: 13, weight: .medium))
                            .padding(.vertical, 10)
                            .padding(.horizontal, 16)
                            .overlay(alignment: .bottom) {
                                if currentTab == tab {
                                    Rectangle().fill(.tint).frame(height: 2)
                                }
                            }
                            .foregroundStyle(currentTab == tab ? VultiTheme.inkSoft : VultiTheme.inkDim)
                    }
                    .buttonStyle(.plain)
                }
                Spacer()
            }
            .padding(.horizontal, 8)

            Divider()

            // Tab content
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    switch currentTab {
                    case .identity:
                        identityTab
                    case .model:
                        modelTab
                    case .communication:
                        communicationTab
                    case .permissions:
                        permissionsTab
                    }
                }
                .padding(24)
            }

            Divider()

            // Bottom buttons
            HStack {
                Button("Cancel") { app.closePanel() }
                Spacer()
                if let error {
                    Text(error)
                        .font(.system(size: 11))
                        .foregroundStyle(.red)
                        .lineLimit(2)
                }
                Button("Create") { create() }
                    .buttonStyle(.vultiPrimary)
                    .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 12)
        }
        .frame(maxWidth: 448)
        .task {
            do { connections = try await app.client.listConnections() } catch {}
            do { availableProviders = try await app.client.listProviders() } catch {}
        }
    }

    // MARK: - Identity Tab

    private var identityTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Name").font(.system(size: 13, weight: .medium)).foregroundStyle(VultiTheme.inkDim)
                TextField("e.g. Hector, WorkBot, Researcher", text: $name)
                    .textFieldStyle(.vulti)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Role").font(.system(size: 13, weight: .medium)).foregroundStyle(VultiTheme.inkDim)
                TextField("e.g. Research Assistant, Community Manager", text: $role)
                    .textFieldStyle(.vulti)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Personality / SOUL.md").font(.system(size: 13, weight: .medium)).foregroundStyle(VultiTheme.inkDim)
                TextEditor(text: $personality)
                    .frame(minHeight: 120)
                    .font(.system(size: 13))
                    .foregroundStyle(VultiTheme.inkSoft)
                    .scrollContentBackground(.hidden)
                    .padding(4)
                    .background(VultiTheme.paperDeep, in: RoundedRectangle(cornerRadius: 6))
                Text("Describe the agent's personality, style, and initial instructions.")
                    .font(.system(size: 10))
                    .foregroundStyle(VultiTheme.inkMuted)
            }
        }
    }

    // MARK: - Model Tab

    private var modelTab: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("MODEL").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)

            let providers = availableProviders.filter(\.authenticated)
            ForEach(providers, id: \.id) { provider in
                VStack(alignment: .leading, spacing: 4) {
                    Text(provider.name)
                        .font(.system(size: 12, weight: .medium))
                    ForEach(provider.models ?? [], id: \.self) { m in
                        HStack {
                            Image(systemName: model == m ? "circle.inset.filled" : "circle")
                                .font(.system(size: 12))
                                .foregroundStyle(model == m ? AnyShapeStyle(.tint) : AnyShapeStyle(VultiTheme.inkDim))
                            Text(m)
                                .font(.system(size: 12))
                                .monospaced()
                        }
                        .contentShape(Rectangle())
                        .onTapGesture { model = m }
                    }
                }
                .padding(.leading, 4)
            }

            if providers.isEmpty {
                Text("No providers configured. Add an API key in Settings.")
                    .font(.system(size: 11))
                    .foregroundStyle(VultiTheme.inkDim)
            }
        }
    }

    // MARK: - Communication Tab

    private var communicationTab: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("MESSAGING PLATFORMS").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
            Text("Enable connections this agent can use to send and receive messages.")
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkDim)

            if messagingConnections.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("No messaging connections found.")
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkDim)
                    Text("Add connections in Settings > Connections first.")
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkMuted)
                }
                .padding(.top, 4)
            } else {
                ForEach(messagingConnections, id: \.name) { conn in
                    HStack {
                        Toggle(isOn: Binding(
                            get: { selectedConnections.contains(conn.name) },
                            set: { enabled in
                                if enabled {
                                    selectedConnections.insert(conn.name)
                                } else {
                                    selectedConnections.remove(conn.name)
                                }
                            }
                        )) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(conn.name)
                                    .font(.system(size: 13, weight: .medium))
                                if let type = conn.type {
                                    Text(type)
                                        .font(.system(size: 10))
                                        .foregroundStyle(VultiTheme.inkDim)
                                }
                            }
                        }
                        .toggleStyle(.switch)
                        .controlSize(.small)
                    }
                }
            }

            // Also show non-messaging connections if any
            let otherConnections = connections.filter { conn in
                !messagingConnections.contains(where: { $0.name == conn.name })
            }
            if !otherConnections.isEmpty {
                Divider().padding(.vertical, 4)
                Text("OTHER CONNECTIONS").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
                ForEach(otherConnections, id: \.name) { conn in
                    HStack {
                        Toggle(isOn: Binding(
                            get: { selectedConnections.contains(conn.name) },
                            set: { enabled in
                                if enabled {
                                    selectedConnections.insert(conn.name)
                                } else {
                                    selectedConnections.remove(conn.name)
                                }
                            }
                        )) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(conn.name)
                                    .font(.system(size: 13, weight: .medium))
                                if let type = conn.type {
                                    Text(type)
                                        .font(.system(size: 10))
                                        .foregroundStyle(VultiTheme.inkDim)
                                }
                            }
                        }
                        .toggleStyle(.switch)
                        .controlSize(.small)
                    }
                }
            }
        }
    }

    // MARK: - Permissions Tab

    private var permissionsTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("PERMISSIONS").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
            Text("Control what this agent is allowed to do.")
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkDim)

            VStack(alignment: .leading, spacing: 12) {
                Text("Read Access").font(.system(size: 12, weight: .medium))
                Toggle("Files — read local files and directories", isOn: $readFiles)
                    .toggleStyle(.switch).controlSize(.small)
                Toggle("Web — fetch URLs and search the web", isOn: $readWeb)
                    .toggleStyle(.switch).controlSize(.small)
            }

            Divider()

            VStack(alignment: .leading, spacing: 12) {
                Text("Write Access").font(.system(size: 12, weight: .medium))
                Toggle("Files — create and modify files", isOn: $writeFiles)
                    .toggleStyle(.switch).controlSize(.small)
                Toggle("Code — execute code and scripts", isOn: $writeCode)
                    .toggleStyle(.switch).controlSize(.small)
            }

            Divider()

            VStack(alignment: .leading, spacing: 12) {
                Text("Tool Access").font(.system(size: 12, weight: .medium))
                Toggle("Tools — use external tools and integrations", isOn: $toolAccess)
                    .toggleStyle(.switch).controlSize(.small)
            }
        }
    }

    // MARK: - Create

    private func create() {
        error = nil
        Task {
            do {
                let agent = try await app.client.createAgent(
                    name: name,
                    role: role.isEmpty ? nil : role,
                    personality: personality.isEmpty ? nil : personality,
                    model: model.isEmpty ? nil : model
                )

                // Set allowed connections via updateAgent
                if !selectedConnections.isEmpty {
                    let updates: [String: String] = [
                        "allowedConnections": Array(selectedConnections).joined(separator: ",")
                    ]
                    _ = try await app.client.updateAgent(agent.id, updates: updates)
                }

                await app.refreshAgents()
                await MainActor.run {
                    app.openAgent(agent.id)
                }
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}

// OnboardingView moved to OnboardingWizard.swift
// AuditView moved to AuditTab.swift
