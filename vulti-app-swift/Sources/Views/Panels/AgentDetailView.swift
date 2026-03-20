import SwiftUI

/// Two-column agent detail: Chat (26rem) LEFT + Tabs RIGHT.
/// Matches SlideOutPanel.svelte agent mode layout.
struct AgentDetailView: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var selectedTab = Tab.home

    enum Tab: String, CaseIterable {
        case home = "Home"
        case profile = "Profile"
        case connections = "Connections"
        case skills = "Skills"
        case actions = "Actions"
        case wallet = "Wallet"
        case analytics = "Analytics"
    }

    @State private var chatWidth: CGFloat = 380

    var body: some View {
        GeometryReader { geo in
            let minChat = geo.size.width / 3
            let maxChat = geo.size.width * 2 / 3

            HStack(spacing: 0) {
                // Left: Chat — resizable
                ChatView(agentId: agentId)
                    .frame(width: max(minChat, min(maxChat, chatWidth)))

                // Drag handle divider
                Rectangle()
                    .fill(VultiTheme.border)
                    .frame(width: 1)
                    .overlay(
                        Rectangle()
                            .fill(Color.clear)
                            .frame(width: 8)
                            .contentShape(Rectangle())
                            .onHover { h in if h { NSCursor.resizeLeftRight.push() } else { NSCursor.pop() } }
                            .gesture(
                                DragGesture(minimumDistance: 1)
                                    .onChanged { value in
                                        let newWidth = chatWidth + value.translation.width
                                        chatWidth = max(minChat, min(maxChat, newWidth))
                                    }
                            )
                    )

                // Right: Tabs — fills remaining space
                VStack(spacing: 0) {
                    tabBar
                    Divider()
                    ScrollView {
                        tabContent
                            .padding(24)
                    }
                }
                .frame(maxWidth: .infinity)
            }
        }
    }

    /// Tab bar matching original: 0.625rem vertical, 1rem horizontal padding,
    /// 0.8125rem font, weight 500, 2px bottom border on active.
    private var tabBar: some View {
        HStack(spacing: 0) {
            ForEach(Tab.allCases, id: \.self) { tab in
                Button {
                    selectedTab = tab
                } label: {
                    Text(tab.rawValue)
                        .font(.system(size: 13, weight: .medium))
                        .padding(.vertical, 10)
                        .padding(.horizontal, 16)
                        .overlay(alignment: .bottom) {
                            if selectedTab == tab {
                                Rectangle()
                                    .fill(VultiTheme.inkSoft)
                                    .frame(height: 2)
                            }
                        }
                        .foregroundStyle(selectedTab == tab ? VultiTheme.inkSoft : VultiTheme.inkDim)
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
        .padding(.horizontal, 8)
    }

    @ViewBuilder
    private var tabContent: some View {
        switch selectedTab {
        case .home: AgentHomeTab(agentId: agentId)
        case .profile: AgentProfileTab(agentId: agentId)
        case .connections: AgentConnectionsTab(agentId: agentId)
        case .skills: AgentSkillsTab(agentId: agentId)
        case .actions: AgentActionsTab(agentId: agentId)
        case .wallet: AgentWalletTab(agentId: agentId)
        case .analytics: AgentAnalyticsTab(agentId: agentId)
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
                            WidgetView(widget: converted)
                        }
                    }
                }
            }
        }
        .task { await loadWidgets() }
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
                    Text(entry.trimmingCharacters(in: .whitespacesAndNewlines))
                        .font(.system(size: 12))
                        .padding(8)
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
                MarkdownMessageView(content: memory, isUser: false)
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
    @State private var providers: [GatewayClient.ProviderResponse] = []
    @State private var configModel = ""
    @State private var expandedProvider: String?
    @State private var isSavingModel = false

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // ── Model / Provider ──
            Section {
                if providers.isEmpty {
                    Text("No providers configured. Add an API key in Settings.")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                } else {
                    ForEach(providers, id: \.id) { provider in
                        VStack(alignment: .leading, spacing: 0) {
                            // Provider row — click to expand model list
                            Button {
                                withAnimation(.easeInOut(duration: 0.15)) {
                                    expandedProvider = expandedProvider == provider.id ? nil : provider.id
                                }
                            } label: {
                                HStack(spacing: 8) {
                                    Circle()
                                        .fill(provider.authenticated ? .green : VultiTheme.inkDim)
                                        .frame(width: 8, height: 8)
                                    Text(provider.name)
                                        .font(.system(size: 13, weight: .medium))
                                        .foregroundStyle(VultiTheme.inkSoft)
                                    Spacer()
                                    if provider.authenticated {
                                        // Show current model if this provider is active
                                        if configModel.hasPrefix(provider.id + "/") || configModel.hasPrefix(provider.id + ":") {
                                            Text(configModel.split(separator: "/").last.map(String.init) ?? configModel)
                                                .font(.system(size: 10, design: .monospaced))
                                                .foregroundStyle(VultiTheme.inkMuted)
                                                .lineLimit(1)
                                        }
                                        Image(systemName: expandedProvider == provider.id ? "chevron.up" : "chevron.down")
                                            .font(.system(size: 9))
                                            .foregroundStyle(VultiTheme.inkMuted)
                                        Text("Connected")
                                            .font(.system(size: 10))
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 2)
                                            .background(.green.opacity(0.1), in: Capsule())
                                            .foregroundStyle(.green)
                                    } else {
                                        Text("No key")
                                            .font(.system(size: 10))
                                            .foregroundStyle(VultiTheme.inkMuted)
                                    }
                                }
                                .padding(.vertical, 6)
                            }
                            .buttonStyle(.plain)
                            .disabled(!provider.authenticated)
                            .opacity(provider.authenticated ? 1.0 : 0.5)

                            // Expanded model list
                            if expandedProvider == provider.id, provider.authenticated {
                                modelList(for: provider)
                                    .transition(.opacity.combined(with: .move(edge: .top)))
                            }
                        }
                    }

                    // Active model display
                    if !configModel.isEmpty {
                        HStack(spacing: 6) {
                            Text("Active:")
                                .font(.system(size: 11))
                                .foregroundStyle(VultiTheme.inkDim)
                            Text(configModel)
                                .font(.system(size: 11, weight: .medium, design: .monospaced))
                                .foregroundStyle(VultiTheme.primary)
                        }
                        .padding(.top, 4)
                    }
                }
            } header: {
                Text("MODEL PROVIDER")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(VultiTheme.inkMuted)
            }

            Divider()

            // ── Allowed Connections ──
            Section {
                if !allowedNames.isEmpty {
                    HStack(spacing: 6) {
                        ForEach(Array(allowedNames).sorted(), id: \.self) { name in
                            Text(name)
                                .font(.system(size: 10, weight: .medium))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(VultiTheme.primary.opacity(0.1), in: Capsule())
                                .foregroundStyle(VultiTheme.primary)
                        }
                    }
                    .padding(.bottom, 4)
                }

                ForEach(allConnections, id: \.name) { conn in
                    HStack {
                        Toggle(isOn: Binding(
                            get: { allowedNames.contains(conn.name) },
                            set: { enabled in
                                if enabled {
                                    allowedNames.insert(conn.name)
                                } else {
                                    allowedNames.remove(conn.name)
                                }
                                saveAllowed()
                            }
                        )) {
                            VStack(alignment: .leading, spacing: 2) {
                                HStack(spacing: 6) {
                                    Text(conn.name)
                                        .font(.system(size: 13, weight: .medium))
                                    if let type = conn.type {
                                        Text(type)
                                            .font(.system(size: 10))
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 2)
                                            .background(VultiTheme.paperDeep, in: Capsule())
                                    }
                                }
                                if let desc = conn.description {
                                    Text(desc)
                                        .font(.system(size: 11))
                                        .foregroundStyle(VultiTheme.inkMuted)
                                        .lineLimit(1)
                                }
                            }
                        }
                        .toggleStyle(.checkbox)
                    }
                    .opacity(allowedNames.contains(conn.name) ? 1.0 : 0.55)
                }

                if allConnections.isEmpty {
                    Text("No connections configured. Add connections in Settings.")
                        .font(.system(size: 13))
                        .foregroundStyle(VultiTheme.inkMuted)
                }
            } header: {
                Text("ALLOWED CONNECTIONS")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(VultiTheme.inkMuted)
            }
        }
        .task { await loadData() }
    }

    private func loadData() async {
        if let list = try? await app.client.listConnections() {
            allConnections = list
        }
        if let agent = app.agent(byId: agentId),
           let allowed = agent.allowedConnections {
            allowedNames = Set(allowed)
        }
        if let list = try? await app.client.listProviders() {
            providers = list
        }
        if let cfg = try? await app.client.getAgentConfig(agentId: agentId),
           let model = cfg["model"]?.value as? String {
            configModel = model
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

    // MARK: Model picker

    @ViewBuilder
    private func modelList(for provider: GatewayClient.ProviderResponse) -> some View {
        let models = provider.models ?? []
        VStack(alignment: .leading, spacing: 0) {
            if models.isEmpty {
                Text("No models available")
                    .font(.system(size: 11))
                    .foregroundStyle(VultiTheme.inkMuted)
                    .padding(.vertical, 8)
                    .padding(.leading, 16)
            } else {
                ForEach(models, id: \.self) { model in
                    let fullId = "\(provider.id)/\(model)"
                    let isActive = configModel == fullId || configModel == model
                    Button {
                        saveModel(fullId)
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: isActive ? "checkmark.circle.fill" : "circle")
                                .font(.system(size: 12))
                                .foregroundStyle(isActive ? VultiTheme.primary : VultiTheme.inkMuted)
                            Text(model)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundStyle(isActive ? VultiTheme.inkSoft : VultiTheme.inkDim)
                                .lineLimit(1)
                            Spacer()
                        }
                        .padding(.vertical, 5)
                        .padding(.horizontal, 16)
                        .background(isActive ? VultiTheme.primary.opacity(0.06) : .clear)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.vertical, 4)
        .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 6))
    }

    private func saveModel(_ model: String) {
        guard !isSavingModel else { return }
        isSavingModel = true
        configModel = model
        Task {
            _ = try? await app.client.updateAgent(agentId, updates: ["model": model])
            isSavingModel = false
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
