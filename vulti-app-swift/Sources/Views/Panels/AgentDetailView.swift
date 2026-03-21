import SwiftUI

/// Agent detail: Chat LEFT + ScratchPad RIGHT (appears when agent pushes content).
struct AgentDetailView: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var scratchPadHasContent = false
    @State private var expandedWidget: DrillTarget? = nil
    @State private var pollTimer: Timer?
    @State private var currentSessionId: String? = nil

    var body: some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                ChatView(
                    agentId: agentId,
                    autoIntrospect: true,
                    viewingContext: expandedWidget?.contextLabel
                )
                .frame(width: scratchPadHasContent ? geo.size.width / 3 : geo.size.width)

                if scratchPadHasContent {
                    // Static 1px divider
                    Rectangle()
                        .fill(VultiTheme.border)
                        .frame(width: 1)

                    ScratchPadView(
                        agentId: agentId,
                        sessionId: currentSessionId,
                        expandedWidget: $expandedWidget,
                        hasContent: $scratchPadHasContent
                    )
                }
            }
        }
        .animation(.spring(duration: 0.4), value: scratchPadHasContent)
        .onAppear { startWidgetPolling() }
        .onDisappear { stopWidgetPolling() }
        .onReceive(NotificationCenter.default.publisher(for: .chatSessionChanged)) { notification in
            if let sid = notification.userInfo?["sessionId"] as? String,
               let aid = notification.userInfo?["agentId"] as? String,
               aid == agentId {
                currentSessionId = sid
            }
        }
    }

    /// Poll for pane widgets from AgentDetailView so we detect content
    /// even before ScratchPadView is mounted.
    private func startWidgetPolling() {
        checkForWidgets()
        pollTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { _ in
            checkForWidgets()
        }
    }

    private func stopWidgetPolling() {
        pollTimer?.invalidate()
        pollTimer = nil
    }

    private func checkForWidgets() {
        guard !scratchPadHasContent else {
            // Already showing — stop polling from here, ScratchPadView takes over
            pollTimer?.invalidate()
            pollTimer = nil
            return
        }
        Task {
            if let pane = try? await app.client.getPaneWidgets(agentId: agentId, sessionId: currentSessionId),
               let tabs = pane.tabs {
                let hasWidgets = tabs.values.contains { !$0.isEmpty }
                if hasWidgets {
                    await MainActor.run {
                        scratchPadHasContent = true
                    }
                }
            }
        }
    }
}

// Helper for single-edge borders
extension View {
    func border(width: CGFloat, edges: [Edge], color: Color) -> some View {
        overlay(EdgeBorder(width: width, edges: edges).foregroundStyle(color))
    }
}

struct EdgeBorder: Shape {
    var width: CGFloat
    var edges: [Edge]

    func path(in rect: CGRect) -> Path {
        var path = Path()
        for edge in edges {
            switch edge {
            case .top: path.addRect(CGRect(x: 0, y: 0, width: rect.width, height: width))
            case .bottom: path.addRect(CGRect(x: 0, y: rect.height - width, width: rect.width, height: width))
            case .leading: path.addRect(CGRect(x: 0, y: 0, width: width, height: rect.height))
            case .trailing: path.addRect(CGRect(x: rect.width - width, y: 0, width: width, height: rect.height))
            }
        }
        return path
    }
}

// MARK: - Tab: Home (custom widgets — matches DynamicPane.svelte)

struct AgentHomeTab: View {
    let agentId: String
    /// Called when a widget with a drill target is tapped (e.g. rules, wallet, crypto)
    var onDrill: ((DrillTarget) -> Void)?
    @Environment(AppState.self) private var app
    @State private var widgets: [GatewayClient.PaneWidget] = []

    var body: some View {
        Group {
            if widgets.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "diamond")
                        .font(.system(size: 32))
                        .foregroundStyle(VultiTheme.inkMuted)
                    Text("No custom widgets yet")
                        .font(.system(size: 14))
                        .foregroundStyle(VultiTheme.inkDim)
                    Text("Ask your agent to create a home view")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkMuted)
                }
                .frame(maxWidth: .infinity, minHeight: 200)
            } else {
                VStack(spacing: 16) {
                    HStack {
                        Text("Custom home view")
                            .font(.system(size: 12))
                            .foregroundStyle(VultiTheme.inkMuted)
                        Spacer()
                        Button("Clear widgets") {
                            Task {
                                try? await app.client.clearPaneWidgets(agentId: agentId)
                                widgets = []
                            }
                        }
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.coral)
                    }
                    ForEach(widgets) { widget in
                        if let converted = widget.toPaneWidget() {
                            homeWidgetCard(converted)
                        }
                    }
                }
            }
        }
        .task { await loadWidgets() }
    }

    /// Widget card with drill-down navigation support
    @ViewBuilder
    private func homeWidgetCard(_ widget: PaneWidget) -> some View {
        let drillTarget = ScratchPadView.inferDrillTarget(for: widget)

        VStack(alignment: .leading, spacing: 8) {
            if let title = widget.title, !title.isEmpty {
                HStack {
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
            }
            WidgetView(widget: widget)
        }
        .padding(12)
        .background(VultiTheme.paperDeep.opacity(0.4), in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(VultiTheme.border.opacity(0.3)))
        .contentShape(Rectangle())
        .onTapGesture {
            if let target = drillTarget {
                onDrill?(target)
            }
        }
    }

    private func loadWidgets() async {
        do {
            let pane = try await app.client.getPaneWidgets(agentId: agentId)
            // Flatten all tabs into a single widget list for display
            var all: [GatewayClient.PaneWidget] = []
            if let tabs = pane.tabs {
                for (_, tabWidgets) in tabs {
                    all.append(contentsOf: tabWidgets)
                }
            }
            widgets = all
        } catch {
            // No widgets available
        }
    }
}

// MARK: - Tab: Profile (soul, understanding, memory — matches original)

struct AgentProfileTab: View {
    let agentId: String
    var initialSubtab: String = "Soul"
    @Environment(AppState.self) private var app

    enum ProfileSubtab: String, CaseIterable {
        case soul = "Soul"
        case user = "User"
        case memories = "Memories"
    }

    @State private var subtab = "Soul"

    // Loaded content (fetched async)
    @State private var soul = ""
    @State private var userMem = ""
    @State private var memory = ""

    // Editing state
    @State private var isEditing = false
    @State private var draft = ""
    @State private var isSaving = false

    /// The content for the current subtab
    private var currentContent: String {
        switch subtab {
        case "Soul": soul
        case "User": userMem
        case "Memories": memory
        default: ""
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Sub-tab picker (left-justified, same style as Actions Jobs/Rules)
            VultiPicker(options: ["Soul", "User", "Memories"], selection: $subtab)
                .onChange(of: subtab) { if isEditing { isEditing = false } }

            // Edit button row
            HStack {
                Spacer()
                if !isEditing {
                    Button {
                        draft = currentContent
                        isEditing = true
                    } label: {
                        Text("Edit")
                    }
                    .buttonStyle(.vultiSecondary)
                }
            }

            // Content
            if isEditing {
                TextEditor(text: $draft)
                    .font(.system(size: 13, design: .monospaced))
                    .foregroundStyle(VultiTheme.inkSoft)
                    .frame(minHeight: 250)
                    .scrollContentBackground(.hidden)
                    .padding(8)
                    .background(VultiTheme.paperDeep, in: RoundedRectangle(cornerRadius: 6))

                HStack(spacing: 8) {
                    Button {
                        isSaving = true
                        Task {
                            switch subtab {
                            case "Soul":
                                try? await app.client.updateSoul(content: draft, agentId: agentId)
                                soul = draft
                            case "User":
                                try? await app.client.updateMemory(file: "user", content: draft, agentId: agentId)
                                userMem = draft
                            case "Memories":
                                try? await app.client.updateMemory(file: "memory", content: draft, agentId: agentId)
                                memory = draft
                            default: break
                            }
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
                profileContent
            }

        }
        .task { await loadProfileData() }
        .onAppear { subtab = initialSubtab }
    }

    @ViewBuilder
    private var profileContent: some View {
        switch subtab {
        case "Soul":
            if soul.isEmpty {
                Text("No personality defined")
                    .font(.system(size: 13))
                    .foregroundStyle(VultiTheme.inkDim)
            } else {
                MarkdownMessageView(content: soul, isUser: false)
            }

        case "User":
            if userMem.isEmpty {
                Text("No understanding yet")
                    .font(.system(size: 13))
                    .foregroundStyle(VultiTheme.inkDim)
            } else {
                ForEach(userMem.components(separatedBy: "\u{00A7}").filter({ !$0.trimmingCharacters(in: .whitespaces).isEmpty }), id: \.self) { entry in
                    MarkdownMessageView(content: entry.trimmingCharacters(in: .whitespacesAndNewlines), isUser: false)
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(VultiTheme.paperDeep, in: RoundedRectangle(cornerRadius: 6))
                }
            }

        case "Memories":
            if memory.isEmpty {
                Text("No long-term memory")
                    .font(.system(size: 13))
                    .foregroundStyle(VultiTheme.inkDim)
            } else {
                let entries = memory.components(separatedBy: "\u{00A7}")
                    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty }
                if entries.count > 1 {
                    // Multiple entries separated by § — render as cards
                    ForEach(entries, id: \.self) { entry in
                        MarkdownMessageView(content: entry, isUser: false)
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(VultiTheme.paperDeep, in: RoundedRectangle(cornerRadius: 6))
                    }
                } else {
                    // Single block — render as markdown
                    MarkdownMessageView(content: memory, isUser: false)
                }
            }
        default:
            EmptyView()
        }
    }

    private func loadProfileData() async {
        if let s = try? await app.client.getSoul(agentId: agentId) {
            soul = s
        }
        if let mem = try? await app.client.getMemories(agentId: agentId) {
            userMem = mem.user
            memory = mem.memory
        }
    }
}

// MARK: - Tab: Connections (per-agent allowed connections selector — matches AgentConnectionsView.svelte)

struct AgentConnectionsTab: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var allConnections: [GatewayClient.ConnectionResponse] = []
    @State private var allowedNames: Set<String> = []

    private var allowedConnections: [GatewayClient.ConnectionResponse] {
        allConnections.filter { allowedNames.contains($0.name) }
    }
    private var availableConnections: [GatewayClient.ConnectionResponse] {
        allConnections.filter { !allowedNames.contains($0.name) }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            // Left: Allowed
            VStack(alignment: .leading, spacing: 8) {
                Text("ALLOWED (\(allowedConnections.count))")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(VultiTheme.inkMuted)

                if allowedConnections.isEmpty {
                    Text("None")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                        .padding(.top, 4)
                } else {
                    ForEach(allowedConnections, id: \.name) { conn in
                        HStack(spacing: 6) {
                            Text(conn.name)
                                .font(.system(size: 12, weight: .medium))
                            Spacer()
                            Button {
                                allowedNames.remove(conn.name)
                                saveAllowed()
                            } label: {
                                Image(systemName: "minus.circle.fill")
                                    .font(.system(size: 12))
                                    .foregroundStyle(.red.opacity(0.6))
                            }
                            .buttonStyle(.plain)
                        }
                        .padding(.vertical, 3)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .padding(12)

            Rectangle()
                .fill(VultiTheme.border)
                .frame(width: 1)

            // Right: Available (not yet allowed)
            VStack(alignment: .leading, spacing: 8) {
                Text("AVAILABLE (\(availableConnections.count))")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(VultiTheme.inkMuted)

                if availableConnections.isEmpty {
                    Text("All connections allowed")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                        .padding(.top, 4)
                } else {
                    ForEach(availableConnections, id: \.name) { conn in
                        HStack(spacing: 6) {
                            Text(conn.name)
                                .font(.system(size: 12))
                                .foregroundStyle(VultiTheme.inkDim)
                            Spacer()
                            Button {
                                allowedNames.insert(conn.name)
                                saveAllowed()
                            } label: {
                                Image(systemName: "plus.circle.fill")
                                    .font(.system(size: 12))
                                    .foregroundStyle(.green.opacity(0.6))
                            }
                            .buttonStyle(.plain)
                        }
                        .padding(.vertical, 3)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .padding(12)
        }
        .task { await loadData() }
    }

    private func loadData() async {
        if let list = try? await app.client.listConnections() {
            allConnections = list
        }
        // Fetch fresh from API to get current allowedConnections
        if let agent = try? await app.client.getAgent(agentId),
           let allowed = agent.allowedConnections {
            allowedNames = Set(allowed)
        }
    }

    private func saveAllowed() {
        Task {
            let updates: [String: String] = [
                "allowedConnections": Array(allowedNames).joined(separator: ",")
            ]
            _ = try? await app.client.updateAgent(agentId, updates: updates)
            await app.refreshAgents()
        }
    }
}

// MARK: - Tab: Skills (installed + browse — matches original)

struct AgentSkillsTab: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var installed: [GatewayClient.SkillResponse] = []
    @State private var available: [GatewayClient.SkillResponse] = []
    @State private var isBrowsing = false
    @State private var searchText = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Button(isBrowsing ? "Done" : "Add Skills") {
                    isBrowsing.toggle()
                    if isBrowsing {
                        Task {
                            if let list = try? await app.client.listAvailableSkills() {
                                available = list
                            }
                        }
                    }
                }
                .buttonStyle(.vultiSecondary)

                if isBrowsing {
                    TextField("Search skills...", text: $searchText)
                        .textFieldStyle(.vulti)
                }
                Spacer()
            }

            if isBrowsing {
                let filtered = searchText.isEmpty ? available :
                    available.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
                ForEach(filtered, id: \.name) { skill in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text(skill.name).font(.system(size: 13, weight: .medium))
                                if let cat = skill.category {
                                    Text(cat).font(.system(size: 10))
                                        .padding(.horizontal, 6).padding(.vertical, 2)
                                        .background(VultiTheme.paperDeep, in: Capsule())
                                }
                            }
                            if let desc = skill.description {
                                Text(desc).font(.system(size: 11)).foregroundStyle(VultiTheme.inkDim).lineLimit(1)
                            }
                        }
                        Spacer()
                        Button("Install") {
                            Task {
                                try? await app.client.installSkill(agentId: agentId, name: skill.name)
                                if let list = try? await app.client.listAgentSkills(agentId: agentId) {
                                    installed = list
                                }
                            }
                        }
                        .font(.system(size: 12))
                        .buttonStyle(.bordered)
                    }
                }
            } else {
                ForEach(installed, id: \.name) { skill in
                    HStack {
                        Text(skill.name).font(.system(size: 13, weight: .medium))
                        if let cat = skill.category {
                            Text(cat).font(.system(size: 10))
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(VultiTheme.paperDeep, in: Capsule())
                        }
                        Spacer()
                        Button {
                            Task {
                                try? await app.client.removeSkill(agentId: agentId, name: skill.name)
                                if let list = try? await app.client.listAgentSkills(agentId: agentId) {
                                    installed = list
                                }
                            }
                        } label: {
                            Image(systemName: "xmark")
                                .font(.system(size: 10))
                                .foregroundStyle(VultiTheme.inkDim)
                        }
                        .buttonStyle(.plain)
                        .help("Remove skill")
                    }
                }
                if installed.isEmpty {
                    Text("No skills installed")
                        .font(.system(size: 13)).foregroundStyle(VultiTheme.inkMuted)
                }
            }
        }
        .task {
            if let list = try? await app.client.listAgentSkills(agentId: agentId) {
                installed = list
            }
        }
    }
}

// AgentActionsTab moved to ActionsTab.swift

// MARK: - Tab: Wallet (Card + Crypto subtabs — matches original)

struct AgentWalletTab: View {
    let agentId: String
    var initialSubtab: String = "Card"
    @Environment(AppState.self) private var app
    @State private var subtab = "Card"

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VultiPicker(options: ["Card", "Crypto"], selection: $subtab)

            if subtab == "Card" {
                CardSubtab(agentId: agentId)
            } else {
                CryptoSubtab(agentId: agentId)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear { subtab = initialSubtab }
    }
}

struct CardSubtab: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var isEditing = false
    @State private var name = ""
    @State private var number = ""
    @State private var expiry = ""
    @State private var code = ""

    // Loaded wallet data
    @State private var cardName: String?
    @State private var cardNumber: String?
    @State private var cardExpiry: String?
    @State private var hasCard = false

    var body: some View {
        Group {
            if isEditing {
                VStack(alignment: .leading, spacing: 12) {
                    TextField("Name on card", text: $name).textFieldStyle(.vulti)
                    TextField("Card number", text: $number).textFieldStyle(.vulti)
                    HStack {
                        TextField("Expiry", text: $expiry).textFieldStyle(.vulti)
                        TextField("CVV", text: $code).textFieldStyle(.vulti)
                    }
                    HStack {
                        Button("Cancel") { isEditing = false }
                        Button("Save") {
                            Task {
                                let wallet: [String: Any] = [
                                    "credit_card": [
                                        "name": name,
                                        "number": number,
                                        "expiry": expiry,
                                        "code": code
                                    ]
                                ]
                                try? await app.client.saveWallet(agentId: agentId, wallet: wallet)
                                cardName = name
                                cardNumber = number
                                cardExpiry = expiry
                                hasCard = true
                                isEditing = false
                            }
                        }
                        .buttonStyle(.vultiPrimary)
                    }
                }
            } else if hasCard {
                VStack(alignment: .leading, spacing: 8) {
                    LabeledContent("Name") { Text(cardName ?? "\u{2014}") }
                    LabeledContent("Number") {
                        Text(maskCard(cardNumber ?? ""))
                            .monospaced()
                    }
                    LabeledContent("Expiry") { Text(cardExpiry ?? "\u{2014}") }
                    Button("Edit") {
                        name = cardName ?? ""
                        number = cardNumber ?? ""
                        expiry = cardExpiry ?? ""
                        code = ""
                        isEditing = true
                    }
                    .buttonStyle(.vultiSecondary)
                }
                .font(.system(size: 12))
            } else {
                Button("Add Credit Card") { isEditing = true }
                    .buttonStyle(.vultiSecondary)
            }
        }
        .task { await loadWalletData() }
    }

    private func maskCard(_ num: String) -> String {
        guard num.count > 4 else { return num }
        return String(repeating: "\u{2022}", count: num.count - 4) + num.suffix(4)
    }

    private func loadWalletData() async {
        do {
            let wallet = try await app.client.getWallet(agentId: agentId)
            if let cc = wallet["credit_card"]?.value as? [String: Any] {
                cardName = cc["name"] as? String
                cardNumber = cc["number"] as? String
                cardExpiry = cc["expiry"] as? String
                hasCard = true
            }
        } catch {
            // No wallet data
        }
    }
}

struct CryptoSubtab: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var vault: GatewayClient.VaultResponse?
    @State private var phase: VaultPhase = .idle
    @State private var addresses: [String: String] = [:]
    @State private var error: String?

    // Form state persisted across phases
    @State private var vaultName = ""
    @State private var vaultEmail = ""
    @State private var vaultPassword = ""
    @State private var vaultId = ""
    @State private var verifyCode = ""

    enum VaultPhase {
        case idle, form, creating, verify, verifying
    }

    var body: some View {
        Group {
            if let vault, vault.vaultId != nil {
                connectedVaultView(vault)
            } else {
                switch phase {
                case .idle:
                    Button("Create Fast Vault") { phase = .form }
                        .buttonStyle(.vultiSecondary)
                case .form:
                    fastVaultForm
                case .creating:
                    ProgressView("Creating vault...")
                case .verify:
                    verifyForm
                case .verifying:
                    ProgressView("Verifying...")
                }

                if let error {
                    Text(error)
                        .font(.system(size: 11))
                        .foregroundStyle(.red)
                        .padding(.top, 4)
                }
            }
        }
        .task { await loadVault() }
    }

    // MARK: - Fast Vault Form

    private var fastVaultForm: some View {
        VStack(alignment: .leading, spacing: 12) {
            TextField("Vault name", text: $vaultName).textFieldStyle(.vulti)
            TextField("Email", text: $vaultEmail).textFieldStyle(.vulti)
            SecureField("Password", text: $vaultPassword).textFieldStyle(.vulti)
            HStack {
                Button("Cancel") { phase = .idle; error = nil }
                Button("Create") { createVault() }
                    .buttonStyle(.vultiPrimary)
                    .disabled(vaultName.isEmpty || vaultEmail.isEmpty || vaultPassword.isEmpty)
            }
        }
    }

    // MARK: - Verify Form

    private var verifyForm: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Enter the verification code sent to \(vaultEmail)")
                .font(.system(size: 12))
                .foregroundStyle(VultiTheme.inkDim)
            TextField("6-digit code", text: $verifyCode)
                .textFieldStyle(.vulti)
            HStack {
                Button("Verify") { verifyVault() }
                    .buttonStyle(.vultiPrimary)
                    .disabled(verifyCode.trimmingCharacters(in: .whitespaces).isEmpty)
                Button("Resend Code") { resendCode() }
                    .font(.system(size: 12))
                Button("Cancel") { phase = .idle; error = nil }
                    .font(.system(size: 12))
            }
        }
    }

    // MARK: - Connected Vault

    @ViewBuilder
    private func connectedVaultView(_ vault: GatewayClient.VaultResponse) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            Section {
                LabeledContent("Name") { Text(vault.name ?? "Unnamed") }
                LabeledContent("Vault ID") {
                    Text(truncateId(vault.vaultId ?? ""))
                        .font(.system(size: 11)).monospaced().lineLimit(1)
                        .textSelection(.enabled)
                }
            } header: {
                Label("Vault connected", systemImage: "checkmark.shield.fill")
                    .foregroundStyle(.green)
                    .font(.system(size: 12, weight: .medium))
            }

            if !addresses.isEmpty {
                Divider()
                Section {
                    ForEach(addresses.sorted(by: { $0.key < $1.key }), id: \.key) { chain, addr in
                        LabeledContent(chain) {
                            Text(truncateId(addr))
                                .font(.system(size: 11)).monospaced()
                                .textSelection(.enabled)
                        }
                    }
                } header: {
                    Text("ADDRESSES").font(.system(size: 12, weight: .medium)).foregroundStyle(VultiTheme.inkMuted)
                }
            }

            Divider()

            Button("Delete Vault") {
                Task {
                    try? await app.client.deleteVault(agentId: agentId)
                    self.vault = nil
                    addresses = [:]
                }
            }
            .buttonStyle(.vultiSecondary)
        }
        .font(.system(size: 12))
    }

    // MARK: - Actions

    private func createVault() {
        error = nil
        phase = .creating
        Task {
            do {
                let id = try await app.vultisig.createFastVault(
                    name: vaultName.trimmingCharacters(in: .whitespaces),
                    email: vaultEmail.trimmingCharacters(in: .whitespaces),
                    password: vaultPassword
                )
                vaultId = id
                phase = .verify
            } catch {
                self.error = error.localizedDescription
                phase = .form
            }
        }
    }

    private func verifyVault() {
        error = nil
        phase = .verifying
        Task {
            do {
                _ = try await app.vultisig.verifyVault(
                    vaultId: vaultId,
                    code: verifyCode.trimmingCharacters(in: .whitespaces),
                    agentId: agentId
                )
                await loadVault()
                phase = .idle
            } catch {
                self.error = error.localizedDescription
                phase = .verify
            }
        }
    }

    private func resendCode() {
        error = nil
        Task {
            do {
                try await app.vultisig.resendVerification(
                    vaultId: vaultId,
                    email: vaultEmail,
                    password: vaultPassword
                )
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func truncateId(_ id: String) -> String {
        guard id.count > 16 else { return id }
        return String(id.prefix(8)) + "..." + String(id.suffix(8))
    }

    private func loadVault() async {
        vault = try? await app.client.getVault(agentId: agentId)
        if let vid = vault?.vaultId {
            if let addrs = try? await app.vultisig.addresses(vaultId: vid) {
                var result: [String: String] = [:]
                for (k, v) in addrs {
                    if let s = v as? String { result[k] = s }
                }
                addresses = result
            }
        }
    }
}

// AgentAnalyticsTab moved to AnalyticsTab.swift
