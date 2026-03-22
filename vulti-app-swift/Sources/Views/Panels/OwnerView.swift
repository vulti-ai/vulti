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
    @State private var isGeneratingAvatar = false
    @State private var isSavingMatrix = false
    @State private var savedMatrixUsername = ""
    @State private var savedMatrixPassword = ""

    private var matrixCredsDirty: Bool {
        matrixUsername != savedMatrixUsername || matrixPassword != savedMatrixPassword
    }

    var body: some View {
        HStack(alignment: .top, spacing: 24) {
            // Left column — Profile
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

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Avatar").font(.system(size: 13, weight: .medium)).foregroundStyle(VultiTheme.inkDim)

                        Button {
                            isGeneratingAvatar = true
                            Task {
                                try? await app.client.generateOwnerAvatar()
                                await app.refreshOwner()
                                avatar = app.ownerInfo?.avatar ?? ""
                                isGeneratingAvatar = false
                            }
                        } label: {
                            HStack(spacing: 4) {
                                if isGeneratingAvatar {
                                    ProgressView().controlSize(.mini)
                                } else {
                                    Image(systemName: "wand.and.stars")
                                        .font(.system(size: 11))
                                }
                                Text(isGeneratingAvatar ? "Generating..." : "Generate Avatar")
                                    .font(.system(size: 11))
                            }
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(VultiTheme.primary)
                        .disabled(isGeneratingAvatar || name.isEmpty)
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
            }
            .frame(maxWidth: 320)

            Divider()

            // Right column — Matrix
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

                        Text("Connect from your phone or desktop:")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(VultiTheme.inkMuted)

                        VStack(alignment: .leading, spacing: 4) {
                            instructionRow(num: "1", text: "Download **Element X** from the App Store or Play Store")
                            instructionRow(num: "2", text: "Tap **\"I already have an account\"**")
                            instructionRow(num: "3", text: "Enter **\"Other\"** for the server, then type the address below")
                            instructionRow(num: "4", text: "Sign in with your username and password")
                        }

                        LabeledContent("Homeserver") { Text(matrixInfo["homeserver_url"] ?? "—").textSelection(.enabled) }
                            .font(.system(size: 12))

                        TextField("Username", text: $matrixUsername)
                            .textFieldStyle(.vulti)
                        TextField("Password", text: $matrixPassword)
                            .textFieldStyle(.vulti)

                        if matrixCredsDirty {
                            Button {
                                saveMatrixCredentials()
                            } label: {
                                HStack(spacing: 6) {
                                    if isSavingMatrix {
                                        ProgressView().controlSize(.small)
                                    }
                                    Text("Save")
                                }
                            }
                            .buttonStyle(.vultiPrimary)
                            .disabled(matrixUsername.isEmpty || matrixPassword.count < 8 || isSavingMatrix)
                        }
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
                    TextField("Password (min 8 chars)", text: $matrixPassword)
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
            .frame(maxWidth: 320)
        }
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
        let hadAvatar = !avatar.isEmpty
        Task {
            try? await app.client.updateOwner(
                name: name.isEmpty ? "" : name,
                about: about.isEmpty ? nil : about
            )
            await app.refreshOwner()
            // Auto-generate avatar on first save (when no avatar exists yet)
            if !hadAvatar && !name.isEmpty {
                Task {
                    try? await app.client.generateOwnerAvatar()
                    await app.refreshOwner()
                }
            }
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
            // Map raw keys to display keys expected by the UI
            if let u = creds["username"] as? String {
                matrixInfo["owner_username"] = u
                matrixUsername = u
                savedMatrixUsername = u
            }
            if let p = creds["password"] as? String {
                matrixInfo["owner_password"] = p
                matrixPassword = p
                savedMatrixPassword = p
            }

            // Read server_name from conduit.toml for the Tailscale URL
            let configURL = VultiHome.continuwuityDir.appending(path: "conduit.toml")
            if let toml = try? String(contentsOf: configURL, encoding: .utf8) {
                for line in toml.components(separatedBy: "\n") {
                    let trimmed = line.trimmingCharacters(in: .whitespaces)
                    if trimmed.hasPrefix("server_name") {
                        let parts = trimmed.components(separatedBy: "=")
                        if parts.count >= 2 {
                            let name = parts[1].trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "\"", with: "")
                            matrixInfo["homeserver_url"] = "https://\(name)"
                        }
                    }
                }
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

    private func saveMatrixCredentials() {
        isSavingMatrix = true
        matrixStatus = "Saving..."
        Task {
            do {
                try await app.client.updateMatrixCredentials(
                    username: matrixUsername,
                    password: matrixPassword
                )
                matrixStatus = "Saved"
                loadMatrixInfo()
            } catch {
                matrixStatus = "Error: \(error.localizedDescription)"
            }
            isSavingMatrix = false
        }
    }

    @ViewBuilder
    private func instructionRow(num: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Text("\(num).")
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(VultiTheme.inkMuted)
                .frame(width: 14, alignment: .trailing)
            Text(.init(text))  // .init enables markdown
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkDim)
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
    @State private var providers: [GatewayClient.ProviderResponse] = []
    @State private var oauthStatuses: [GatewayClient.OAuthResponse] = []
    @State private var pendingPermissions: [GatewayClient.PermissionResponse] = []

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

            // Integrations moved to Connections tab

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

            // API keys managed via connections

            Spacer().frame(height: 40)

            Divider()

            // ── Reset Everything ──
            VStack(spacing: 12) {
                if showResetConfirm {
                    Text("This will delete all agents, connections, skills, jobs, rules, memories, sessions, Matrix server, and all cached data. Are you sure?")
                        .font(.system(size: 12))
                        .foregroundStyle(.red.opacity(0.8))
                        .multilineTextAlignment(.center)

                    HStack(spacing: 12) {
                        Button("No") {
                            withAnimation(.easeInOut(duration: 0.15)) { showResetConfirm = false }
                        }
                        .buttonStyle(.plain)
                        .font(.system(size: 12, weight: .medium))

                        Button("Yes, delete everything") {
                            performReset()
                        }
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 6)
                        .background(.red, in: RoundedRectangle(cornerRadius: 6))
                        .buttonStyle(.plain)
                    }
                } else {
                    Button {
                        withAnimation(.easeInOut(duration: 0.15)) { showResetConfirm = true }
                    } label: {
                        Text("Reset Everything")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(.red)
                    }
                    .buttonStyle(.plain)
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 8)
        }
        .task { await reload() }
    }

    @State private var showResetConfirm = false

    private func performReset() {
        Task {
            try? await app.client.resetEverything()
            await app.refreshAgents()
            showResetConfirm = false
            // Close settings panel, reset onboarding flag, go back to home → onboarding
            app.closePanel()
            Persistence.onboardingComplete = false
            app.onboardingComplete = false
        }
    }

    private func reload() async {
        do { providers = try await app.client.listProviders() } catch {}
        do { oauthStatuses = try await app.client.oauthStatus() } catch {}
        do { pendingPermissions = try await app.client.listPermissions() } catch {}
    }

    private func resolvePermission(_ id: String, approved: Bool) {
        Task {
            try? await app.client.resolvePermission(requestId: id, approved: approved)
            do { pendingPermissions = try await app.client.listPermissions() } catch {}
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
/// Create agent — matches Tauri CreateAgentView.svelte exactly.
/// Single form: Name + Model picker (grouped by provider) + inline API key addition.
/// After create → transitions to onboarding wizard.
struct CreateAgentView: View {
    @Environment(AppState.self) private var app

    @State private var name = ""
    @State private var selectedModel = ""
    @State private var providers: [GatewayClient.ProviderResponse] = []
    @State private var isCreating = false
    @State private var error: String?

    // Inline API key addition
    @State private var showAddKey = false
    @State private var newKeyName = "OPENROUTER_API_KEY"
    @State private var newKeyValue = ""
    @State private var isAddingKey = false

    private static let keyOptions: [(label: String, key: String)] = [
        ("OpenRouter", "OPENROUTER_API_KEY"),
        ("Anthropic", "ANTHROPIC_API_KEY"),
        ("OpenAI", "OPENAI_API_KEY"),
        ("DeepSeek", "DEEPSEEK_API_KEY"),
        ("Google AI", "GOOGLE_API_KEY"),
    ]

    private var authenticatedProviders: [GatewayClient.ProviderResponse] {
        providers.filter(\.authenticated)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {

                // ── Name ──
                VStack(alignment: .leading, spacing: 6) {
                    Text("Name")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(VultiTheme.inkSoft)
                    TextField("e.g. Hector, WorkBot, Researcher", text: $name)
                        .textFieldStyle(.vulti)
                        .onSubmit { if canCreate { create() } }
                }

                // ── Model ──
                VStack(alignment: .leading, spacing: 8) {
                    Text("Model")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(VultiTheme.inkSoft)

                    if authenticatedProviders.isEmpty {
                        // No providers warning
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.triangle")
                                .foregroundStyle(.orange)
                            Text("No API keys configured. Add one to get started.")
                                .font(.system(size: 12))
                                .foregroundStyle(VultiTheme.inkDim)
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
                    } else {
                        // Model list grouped by provider
                        VStack(alignment: .leading, spacing: 12) {
                            ForEach(authenticatedProviders, id: \.id) { provider in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(provider.name)
                                        .font(.system(size: 11, weight: .semibold))
                                        .foregroundStyle(VultiTheme.inkDim)
                                        .textCase(.uppercase)

                                    ForEach(provider.models ?? [], id: \.self) { m in
                                        let modelId = stripProviderPrefix(m)
                                        HStack(spacing: 8) {
                                            Image(systemName: selectedModel == modelId ? "circle.inset.filled" : "circle")
                                                .font(.system(size: 13))
                                                .foregroundStyle(selectedModel == modelId ? VultiTheme.primary : VultiTheme.inkDim)
                                            Text(modelId)
                                                .font(.system(size: 12, design: .monospaced))
                                                .foregroundStyle(selectedModel == modelId ? VultiTheme.inkSoft : VultiTheme.inkDim)
                                        }
                                        .padding(.vertical, 4)
                                        .padding(.horizontal, 8)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .background(
                                            selectedModel == modelId
                                                ? VultiTheme.primary.opacity(0.08)
                                                : Color.clear,
                                            in: RoundedRectangle(cornerRadius: 6)
                                        )
                                        .contentShape(Rectangle())
                                        .onTapGesture { selectedModel = modelId }
                                    }
                                }
                            }
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, maxHeight: 192, alignment: .topLeading)
                        .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
                    }

                    // Inline API key addition
                    if showAddKey {
                        HStack(spacing: 8) {
                            Picker("", selection: $newKeyName) {
                                ForEach(Self.keyOptions, id: \.key) { opt in
                                    Text(opt.label).tag(opt.key)
                                }
                            }
                            .labelsHidden()
                            .frame(width: 130)

                            SecureField("Paste API key", text: $newKeyValue)
                                .textFieldStyle(.vulti)

                            Button(isAddingKey ? "Saving..." : "Save") {
                                addKey()
                            }
                            .buttonStyle(.vultiPrimary)
                            .font(.system(size: 11, weight: .medium))
                            .disabled(isAddingKey || newKeyValue.trimmingCharacters(in: .whitespaces).isEmpty)

                            Button("Cancel") {
                                showAddKey = false
                                newKeyValue = ""
                            }
                            .font(.system(size: 11))
                            .foregroundStyle(VultiTheme.inkMuted)
                            .buttonStyle(.plain)
                        }
                    } else {
                        Button("+ Add API key") {
                            showAddKey = true
                        }
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.primary)
                        .buttonStyle(.plain)
                    }
                }

                // ── Error ──
                if let error {
                    Text(error)
                        .font(.system(size: 12))
                        .foregroundStyle(.red)
                }

                // ── Buttons ──
                HStack {
                    Button("Cancel") { app.closePanel() }
                        .font(.system(size: 13))
                        .foregroundStyle(VultiTheme.inkMuted)
                        .buttonStyle(.plain)

                    Spacer()

                    Button(isCreating ? "Creating..." : "Create") { create() }
                        .buttonStyle(.vultiPrimary)
                        .disabled(!canCreate)
                }
            }
            .padding(32)
            .frame(maxWidth: 448)
        }
        .task { await loadProviders() }
    }

    // MARK: - Helpers

    private var canCreate: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty
            && !selectedModel.isEmpty
            && !isCreating
    }

    private func loadProviders() async {
        providers = (try? await app.client.listProviders()) ?? []
        // Auto-select first model from first authenticated provider
        if selectedModel.isEmpty,
           let first = authenticatedProviders.first,
           let firstModel = first.models?.first {
            selectedModel = firstModel
        }
    }

    private func addKey() {
        let value = newKeyValue.trimmingCharacters(in: .whitespaces)
        guard !value.isEmpty else { return }
        isAddingKey = true
        Task {
            try? await app.client.addSecret(key: newKeyName, value: value)
            newKeyValue = ""
            showAddKey = false
            isAddingKey = false
            await loadProviders()
        }
    }

    /// Strip provider routing prefix (e.g. "openrouter/anthropic/claude-opus-4" → "anthropic/claude-opus-4")
    private func stripProviderPrefix(_ model: String) -> String {
        let prefixes = ["openrouter/", "openai/openai/", "anthropic/anthropic/"]
        for prefix in prefixes {
            if model.hasPrefix(prefix) {
                return String(model.dropFirst(prefix.count))
            }
        }
        return model
    }

    private func create() {
        error = nil
        isCreating = true
        Task {
            do {
                let agent = try await app.client.createAgent(
                    name: name.trimmingCharacters(in: .whitespaces),
                    model: selectedModel
                )

                // Every agent gets matrix connection + skill by default
                _ = try? await app.client.updateAgent(agent.id, updates: [
                    "allowedConnections": "matrix"
                ])
                try? await app.client.installSkill(agentId: agent.id, name: "matrix")

                await app.refreshAgents()

                // Matrix onboarding (fire-and-forget — registers agent on homeserver, creates DM)
                Task { try? await app.client.onboardAgentToMatrix(agentId: agent.id) }

                await MainActor.run {
                    app.openAgent(agent.id)
                }
            } catch {
                self.error = error.localizedDescription
                isCreating = false
            }
        }
    }
}
