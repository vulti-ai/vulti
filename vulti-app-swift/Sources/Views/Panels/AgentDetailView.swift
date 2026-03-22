import SwiftUI

/// Agent detail: Chat LEFT + ScratchPad RIGHT (appears when agent pushes content).
struct AgentDetailView: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var scratchPadHasContent = false
    @State private var expandedWidget: DrillTarget? = nil
    @State private var pollTimer: Timer?
    @State private var currentSessionId: String? = nil
    @State private var scratchPadHidden = true

    private var isOnboarding: Bool {
        app.agent(byId: agentId)?.status == "onboarding"
    }

    private var isWizard: Bool {
        app.agent(byId: agentId)?.role == "wizard"
    }

    private var showScratchPad: Bool {
        scratchPadHasContent && !scratchPadHidden
    }

    var body: some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                if (isOnboarding || isWizard) && !showScratchPad {
                    Spacer()
                }

                ChatView(
                    agentId: agentId,
                    autoIntrospect: true,
                    viewingContext: expandedWidget?.contextLabel
                )
                .frame(width: showScratchPad
                       ? geo.size.width / 3
                       : ((isOnboarding || isWizard) ? geo.size.width / 3 : geo.size.width))

                if (isOnboarding || isWizard) && !showScratchPad {
                    Spacer()
                }

                if showScratchPad {
                    // Static 1px divider
                    Rectangle()
                        .fill(VultiTheme.border)
                        .frame(width: 1)

                    ScratchPadView(
                        agentId: agentId,
                        sessionId: currentSessionId,
                        expandedWidget: $expandedWidget,
                        hasContent: $scratchPadHasContent,
                        onHide: { withAnimation(.spring(duration: 0.3)) { scratchPadHidden = true } }
                    )
                }

                // removed — toggle is in the overlay
            }
        }
        .overlay(alignment: .topTrailing) {
            if scratchPadHasContent && scratchPadHidden {
                Button {
                    withAnimation(.spring(duration: 0.3)) { scratchPadHidden = false }
                } label: {
                    Text("Show Panel")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(VultiTheme.primary)
                }
                .buttonStyle(.plain)
                .padding(.top, 10)
                .padding(.trailing, 16)
            }
        }
        .animation(.spring(duration: 0.4), value: showScratchPad)
        .onAppear {
            // All agents start hidden; regular agents auto-reveal when soul appears
            scratchPadHidden = true
        }
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

    @State private var soulRevealed = false

    private func checkForWidgets() {
        Task {
            // Check for pane widget content
            if !scratchPadHasContent {
                if let pane = try? await app.client.getPaneWidgets(agentId: agentId, sessionId: currentSessionId),
                   let tabs = pane.tabs {
                    let hasWidgets = tabs.values.contains { !$0.isEmpty }
                    if hasWidgets {
                        await MainActor.run { scratchPadHasContent = true }
                    }
                }
            }

            // Auto-reveal panel when soul appears (non-wizard agents only)
            if scratchPadHidden && !soulRevealed && !isWizard {
                if let soul = try? await app.client.getSoul(agentId: agentId),
                   !soul.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    await MainActor.run {
                        soulRevealed = true
                        withAnimation(.spring(duration: 0.4)) { scratchPadHidden = false }
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

// MARK: - Tab: Skills (two-column: installed left, available right — matches connections pattern)

struct AgentSkillsTab: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var installed: [GatewayClient.SkillResponse] = []
    @State private var allAvailable: [GatewayClient.SkillResponse] = []
    @State private var searchText = ""

    private var installedNames: Set<String> {
        Set(installed.map(\.name))
    }

    private var notInstalled: [GatewayClient.SkillResponse] {
        var filtered = allAvailable.filter { !installedNames.contains($0.name) }
        if !searchText.isEmpty {
            let q = searchText.lowercased()
            filtered = filtered.filter {
                $0.name.lowercased().contains(q) ||
                ($0.description?.lowercased().contains(q) ?? false) ||
                ($0.category?.lowercased().contains(q) ?? false)
            }
        }
        return filtered
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            // Left: Installed
            VStack(alignment: .leading, spacing: 8) {
                Text("INSTALLED (\(installed.count))")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(VultiTheme.inkMuted)

                if installed.isEmpty {
                    Text("No skills installed")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                        .padding(.top, 4)
                } else {
                    ForEach(installed, id: \.name) { skill in
                        HStack(spacing: 6) {
                            VStack(alignment: .leading, spacing: 1) {
                                HStack(spacing: 4) {
                                    Text(skill.name)
                                        .font(.system(size: 12, weight: .medium))
                                    if let cat = skill.category {
                                        Text(cat)
                                            .font(.system(size: 9))
                                            .padding(.horizontal, 4).padding(.vertical, 1)
                                            .background(VultiTheme.paperDeep, in: Capsule())
                                            .foregroundStyle(VultiTheme.inkMuted)
                                    }
                                }
                                if let desc = skill.description {
                                    Text(desc)
                                        .font(.system(size: 10))
                                        .foregroundStyle(VultiTheme.inkDim)
                                        .lineLimit(1)
                                }
                            }
                            Spacer()
                            Button {
                                Task {
                                    try? await app.client.removeSkill(agentId: agentId, name: skill.name)
                                    await reload()
                                }
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

            // Right: Available (not yet installed)
            VStack(alignment: .leading, spacing: 8) {
                Text("AVAILABLE (\(notInstalled.count))")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(VultiTheme.inkMuted)

                TextField("Search...", text: $searchText)
                    .textFieldStyle(.vulti)
                    .controlSize(.small)

                if notInstalled.isEmpty {
                    Text(searchText.isEmpty ? "All skills installed" : "No matching skills")
                        .font(.system(size: 12))
                        .foregroundStyle(VultiTheme.inkDim)
                        .padding(.top, 4)
                } else {
                    ForEach(notInstalled, id: \.name) { skill in
                        HStack(spacing: 6) {
                            Button {
                                Task {
                                    try? await app.client.installSkill(agentId: agentId, name: skill.name)
                                    await reload()
                                }
                            } label: {
                                Image(systemName: "plus.circle.fill")
                                    .font(.system(size: 12))
                                    .foregroundStyle(.green.opacity(0.6))
                            }
                            .buttonStyle(.plain)
                            VStack(alignment: .leading, spacing: 1) {
                                HStack(spacing: 4) {
                                    Text(skill.name)
                                        .font(.system(size: 12))
                                        .foregroundStyle(VultiTheme.inkDim)
                                    if let cat = skill.category {
                                        Text(cat)
                                            .font(.system(size: 9))
                                            .padding(.horizontal, 4).padding(.vertical, 1)
                                            .background(VultiTheme.paperDeep, in: Capsule())
                                            .foregroundStyle(VultiTheme.inkMuted)
                                    }
                                }
                                if let desc = skill.description {
                                    Text(desc)
                                        .font(.system(size: 10))
                                        .foregroundStyle(VultiTheme.inkFaint)
                                        .lineLimit(1)
                                }
                            }
                            Spacer()
                        }
                        .padding(.vertical, 3)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .padding(12)
        }
        .task { await reload() }
    }

    private func reload() async {
        if let list = try? await app.client.listAgentSkills(agentId: agentId) {
            installed = list
        }
        if let list = try? await app.client.listAvailableSkills() {
            allAvailable = list
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
    @State private var cardCode: String?
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
                                cardCode = code.isEmpty ? nil : code
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
                    LabeledContent("CVV") { Text(cardCode != nil ? "\u{2022}\u{2022}\u{2022}" : "\u{2014}") }
                    Button("Edit") {
                        name = cardName ?? ""
                        number = cardNumber ?? ""
                        expiry = cardExpiry ?? ""
                        code = cardCode ?? ""
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
                cardCode = cc["code"] as? String
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
        VStack(alignment: .leading, spacing: 16) {
            // Green vault card
            VaultVisual(
                name: vault.name ?? "Vault",
                vaultId: vault.vaultId ?? "",
                chainCount: vault.chains ?? addresses.count,
                vaultType: vault.type ?? "Fast Vault"
            )

            // Vault details
            VStack(alignment: .leading, spacing: 8) {
                Text("VAULT DETAILS")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(VultiTheme.inkMuted)

                vaultDetailRow("Name", vault.name ?? "Unnamed")
                vaultDetailRow("Vault ID", truncateId(vault.vaultId ?? ""), mono: true, selectable: true)
                vaultDetailRow("Type", vault.type?.capitalized ?? "Fast Vault")
                vaultDetailRow("Security", "Encrypted, 2-of-2 threshold")
                if let ts = vault.createdAt {
                    let date = Date(timeIntervalSince1970: ts / 1000)
                    vaultDetailRow("Created", date.formatted(date: .abbreviated, time: .shortened))
                }
            }

            // Addresses
            if !addresses.isEmpty {
                Divider()
                VStack(alignment: .leading, spacing: 8) {
                    Text("CHAIN ADDRESSES")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(VultiTheme.inkMuted)

                    ForEach(addresses.sorted(by: { $0.key < $1.key }), id: \.key) { chain, addr in
                        VStack(alignment: .leading, spacing: 3) {
                            HStack(spacing: 6) {
                                Image(systemName: chainIcon(chain))
                                    .font(.system(size: 11))
                                    .foregroundStyle(chainColor(chain))
                                    .frame(width: 16)
                                Text(chain)
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundStyle(VultiTheme.inkSoft)
                                Spacer()
                            }
                            Text(addr)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundStyle(VultiTheme.inkDim)
                                .lineLimit(1)
                                .truncationMode(.middle)
                                .textSelection(.enabled)
                        }
                        .padding(10)
                        .background(VultiTheme.paperDeep.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
                    }
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
            .foregroundStyle(VultiTheme.coral)
            .font(.system(size: 12, weight: .medium))
            .buttonStyle(.plain)
        }
    }

    private func vaultDetailRow(_ key: String, _ value: String, mono: Bool = false, selectable: Bool = false) -> some View {
        HStack {
            Text(key)
                .font(.system(size: 12))
                .foregroundStyle(VultiTheme.inkDim)
            Spacer()
            Group {
                if selectable {
                    Text(value)
                        .textSelection(.enabled)
                } else {
                    Text(value)
                }
            }
            .font(.system(size: 12, design: mono ? .monospaced : .default))
            .foregroundStyle(VultiTheme.inkSoft)
            .lineLimit(1)
        }
    }

    private func chainIcon(_ chain: String) -> String {
        switch chain.lowercased() {
        case "bitcoin": return "bitcoinsign.circle"
        case "ethereum", "bsc": return "diamond"
        case "solana": return "sun.max"
        case "thorchain": return "bolt.shield"
        default: return "circle"
        }
    }

    private func chainColor(_ chain: String) -> Color {
        switch chain.lowercased() {
        case "bitcoin": return .orange
        case "ethereum": return .blue
        case "solana": return .purple
        case "thorchain": return .cyan
        case "bsc": return .yellow
        default: return VultiTheme.inkDim
        }
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
                    password: vaultPassword,
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
        // Addresses come from the vault response now (backend fetches via CLI)
        if let addrs = vault?.addresses {
            addresses = addrs
        } else if let vid = vault?.vaultId, !vid.isEmpty {
            // Fallback: fetch via Vultisig client
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

// MARK: - Agent Files Viewer

struct AgentFilesView: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var files: [GatewayClient.AgentFile] = []
    @State private var filter: String? = nil  // nil = all

    private var filtered: [GatewayClient.AgentFile] {
        guard let filter else { return files }
        return files.filter { $0.category == filter }
    }

    private let categories: [(String?, String, String)] = [
        (nil, "All", "folder"),
        ("image", "Images", "photo"),
        ("audio", "Audio", "waveform"),
        ("video", "Video", "play.rectangle"),
        ("document", "Docs", "doc"),
    ]

    var body: some View {
        VStack(spacing: 0) {
            // Header with filter chips
            HStack(spacing: 8) {
                Text("FILES")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(VultiTheme.inkMuted)

                ForEach(categories, id: \.1) { cat, label, icon in
                    Button {
                        withAnimation(.easeInOut(duration: 0.15)) { filter = cat }
                    } label: {
                        HStack(spacing: 3) {
                            Image(systemName: icon)
                                .font(.system(size: 9))
                            Text(label)
                                .font(.system(size: 10, weight: filter == cat ? .semibold : .regular))
                        }
                        .foregroundStyle(filter == cat ? VultiTheme.primary : VultiTheme.inkMuted)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(
                            filter == cat ? VultiTheme.primary.opacity(0.1) : Color.clear,
                            in: Capsule()
                        )
                    }
                    .buttonStyle(.plain)
                }

                Spacer()

                Text("\(filtered.count) file\(filtered.count == 1 ? "" : "s")")
                    .font(.system(size: 10))
                    .foregroundStyle(VultiTheme.inkDim)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)

            Divider()

            // File list (horizontal scroll)
            if filtered.isEmpty {
                Spacer()
                Text("No files")
                    .font(.system(size: 12))
                    .foregroundStyle(VultiTheme.inkDim)
                Spacer()
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(filtered) { file in
                            fileCard(file)
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                }
            }
        }
        .task { await loadFiles() }
    }

    @ViewBuilder
    private func fileCard(_ file: GatewayClient.AgentFile) -> some View {
        VStack(spacing: 4) {
            ZStack(alignment: .topTrailing) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(VultiTheme.paperDeep)
                        .frame(width: 80, height: 56)
                    Image(systemName: iconForFile(file))
                        .font(.system(size: 20))
                        .foregroundStyle(colorForCategory(file.category))
                }

                // Delete button
                Button {
                    Task {
                        try? await app.client.deleteAgentFile(agentId: agentId, path: file.path)
                        files.removeAll { $0.path == file.path }
                    }
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 14))
                        .foregroundStyle(VultiTheme.inkDim)
                }
                .buttonStyle(.plain)
                .offset(x: 4, y: -4)
            }

            Text(file.name)
                .font(.system(size: 9))
                .foregroundStyle(VultiTheme.inkSoft)
                .lineLimit(1)
                .truncationMode(.middle)
                .frame(width: 80)

            // View button
            Button {
                if let url = app.client.agentFileURL(agentId: agentId, path: file.path) {
                    NSWorkspace.shared.open(url)
                }
            } label: {
                Text("View")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(VultiTheme.primary)
            }
            .buttonStyle(.plain)

            Text(formatSize(file.size))
                .font(.system(size: 8))
                .foregroundStyle(VultiTheme.inkDim)
        }
    }

    private func iconForFile(_ file: GatewayClient.AgentFile) -> String {
        switch file.category {
        case "image": return "photo"
        case "audio": return "waveform"
        case "video": return "play.rectangle.fill"
        case "document":
            if file.name.hasSuffix(".pdf") { return "doc.richtext" }
            return "doc"
        default: return "doc"
        }
    }

    private func colorForCategory(_ category: String) -> Color {
        switch category {
        case "image": return .blue
        case "audio": return .orange
        case "video": return .purple
        case "document": return .green
        default: return VultiTheme.inkDim
        }
    }

    private func formatSize(_ bytes: Int) -> String {
        if bytes < 1024 { return "\(bytes) B" }
        if bytes < 1024 * 1024 { return "\(bytes / 1024) KB" }
        return String(format: "%.1f MB", Double(bytes) / (1024 * 1024))
    }

    private func loadFiles() async {
        files = (try? await app.client.listAgentFiles(agentId: agentId)) ?? []
    }
}

// AgentAnalyticsTab moved to AnalyticsTab.swift
