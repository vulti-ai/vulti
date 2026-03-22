import SwiftUI

/// Full-height panel that slides in from LEFT.
/// Matches SlideOutPanel.svelte layout: header 56px, tabs, two-column for agents.
struct SlideOutPanel: View {
    let mode: AppState.PanelMode
    @Environment(AppState.self) private var app

    var body: some View {
        VStack(spacing: 0) {
            // Header (56px = 3.5rem — matches original)
            panelHeader
                .frame(height: 56)
                .padding(.horizontal, 24)

            Divider()

            // Content
            panelContent
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(VultiTheme.paper)
    }

    @ViewBuilder
    private var panelHeader: some View {
        HStack {
            switch mode {
            case .agent(let id):
                AgentPanelHeader(agentId: id)
            case .owner:
                Text("Owner")
                    .font(.system(size: 16, weight: .bold)).foregroundStyle(VultiTheme.inkSoft)
            case .settings:
                Text("Settings")
                    .font(.system(size: 16, weight: .bold)).foregroundStyle(VultiTheme.inkSoft)
            case .create:
                Text("New Agent")
                    .font(.system(size: 16, weight: .bold)).foregroundStyle(VultiTheme.inkSoft)
            case .audit:
                Text("Activity")
                    .font(.system(size: 16, weight: .bold)).foregroundStyle(VultiTheme.inkSoft)
            }

            Spacer()

            // Close button (or spinner if busy — matches original)
            if app.isBusy {
                ProgressView()
                    .controlSize(.small)
                    .frame(width: 32, height: 32)
            } else {
                Button { app.closePanel() } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 14))
                        .frame(width: 32, height: 32)
                }
                .buttonStyle(.plain)
                .foregroundStyle(VultiTheme.inkDim)
            }
        }
    }

    @ViewBuilder
    private var panelContent: some View {
        switch mode {
        case .agent(let id):
            AgentDetailView(agentId: id)
        case .owner:
            ScrollView { OwnerView().padding(24) }
        case .settings:
            SettingsView()
        case .create:
            CreateAgentView()
        case .audit:
            AuditView()
        }
    }
}

/// Agent header: avatar, name, role badge, @id, default badge, delete button, model picker
struct AgentPanelHeader: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var isGeneratingAvatar = false
    @State private var showDeleteConfirm = false
    @State private var isDeleting = false
    @State private var configModel = ""
    @State private var providers: [GatewayClient.ProviderResponse] = []
    @State private var isLoadingProviders = true

    private var agent: GatewayClient.AgentResponse? {
        app.agent(byId: agentId)
    }

    @State private var didLoadConfig = false

    /// Short display name for the active model
    private var modelShortName: String {
        if !didLoadConfig { return "Loading…" }
        if configModel.isEmpty { return "No model" }
        return String(configModel.split(separator: "/").last ?? Substring(configModel))
    }

    /// Which provider owns the current model
    private var activeProviderName: String? {
        guard !configModel.isEmpty else { return nil }
        for p in providers {
            let models = (p.models ?? []).map { Self.stripProviderPrefix($0) }
            if models.contains(configModel) {
                return p.name
            }
        }
        return nil
    }

    var body: some View {
        HStack(spacing: 10) {
            // Avatar — uses shared AgentAvatar component
            if let a = agent {
                AgentAvatar(agent: a, roleColor: roleColorForAgent(a), size: 32)
            }

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(agent?.name ?? agentId)
                        .font(.system(size: 16, weight: .bold))
                        .foregroundStyle(VultiTheme.inkSoft)

                    if isGeneratingAvatar {
                        ProgressView().controlSize(.mini)
                    } else {
                        Button {
                            isGeneratingAvatar = true
                            Task {
                                try? await app.client.generateAvatar(agentId: agentId)
                                app.invalidateAvatar(agentId)
                                await app.refreshAgents()
                                isGeneratingAvatar = false
                            }
                        } label: {
                            Image(systemName: "wand.and.stars")
                                .font(.system(size: 11))
                                .foregroundStyle(VultiTheme.inkDim)
                        }
                        .buttonStyle(.plain)
                        .help("Generate avatar")
                    }

                    if let role = agent?.role, !role.isEmpty {
                        VultiTag(text: role, color: VultiTheme.inkDim)
                    }

                    if agentId == app.defaultAgentId {
                        Text("default")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(VultiTheme.lime)
                    }

                }

                HStack(spacing: 8) {
                    Text("@\(agentId)-vulti")
                        .font(.system(size: 11))
                        .foregroundStyle(VultiTheme.inkMuted)
                        .monospaced()

                    modelPicker

                    if agentId != "hector" {
                        if showDeleteConfirm {
                            HStack(spacing: 6) {
                                Text("Delete?")
                                    .font(.system(size: 11))
                                    .foregroundStyle(VultiTheme.inkMuted)
                                Button(isDeleting ? "..." : "Yes") {
                                    isDeleting = true
                                    Task {
                                        try? await app.client.deleteAgent(agentId)
                                        await app.refreshAgents()
                                        await MainActor.run {
                                            isDeleting = false
                                            showDeleteConfirm = false
                                            app.closePanel()
                                        }
                                    }
                                }
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(.white)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 2)
                                .background(.red, in: RoundedRectangle(cornerRadius: 4))
                                .buttonStyle(.plain)
                                .disabled(isDeleting)

                                Button("No") { showDeleteConfirm = false }
                                    .font(.system(size: 11))
                                    .foregroundStyle(VultiTheme.inkMuted)
                                    .buttonStyle(.plain)
                            }
                        } else {
                            Button("Delete") { showDeleteConfirm = true }
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(VultiTheme.coral)
                                .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
        .task(id: agentId) {
            configModel = ""
            didLoadConfig = false
            isLoadingProviders = true
            // Load model from agent config — model can be a string or a dict with "default" key
            do {
                let cfg = try await app.client.getAgentConfig(agentId: agentId)
                if let modelVal = cfg["model"]?.value {
                    if let s = modelVal as? String, !s.isEmpty {
                        configModel = s
                    } else if let dict = modelVal as? [String: Any],
                              let defaultModel = dict["default"] as? String, !defaultModel.isEmpty {
                        // Nested format: model: { default: "provider/model", provider: "..." }
                        let provider = dict["provider"] as? String ?? ""
                        if !provider.isEmpty && !defaultModel.contains("/") {
                            configModel = "\(provider)/\(defaultModel)"
                        } else {
                            configModel = defaultModel
                        }
                    }
                }
            } catch {
                // Config may not exist for new agents
            }
            didLoadConfig = true
            // Load authenticated providers
            if let list = try? await app.client.listProviders() {
                providers = list.filter(\.authenticated)
            }
            isLoadingProviders = false
        }
    }

    @ViewBuilder
    private var modelPicker: some View {
        if isLoadingProviders {
            HStack(spacing: 4) {
                ProgressView()
                    .controlSize(.mini)
                Text(modelShortName)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(VultiTheme.inkDim)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(VultiTheme.paperDeep, in: Capsule())
        } else {
        Menu {
            if providers.isEmpty {
                Text("No providers connected")
            }
            ForEach(providers, id: \.id) { provider in
                let models = provider.models ?? []
                if models.isEmpty {
                    Menu(provider.name) {
                        Text("No models available")
                    }
                } else {
                    let isActive = activeProviderName == provider.name
                    Menu(isActive ? "\(provider.name) ✓" : provider.name) {
                        ForEach(models, id: \.self) { model in
                            // Strip routing prefix (openrouter/, anthropic/anthropic/) — backend expects clean model ID
                            let cleanId = Self.stripProviderPrefix(model)
                            Button {
                                configModel = cleanId
                                Task {
                                    _ = try? await app.client.updateAgent(
                                        agentId, updates: ["model": cleanId]
                                    )
                                }
                            } label: {
                                HStack {
                                    Text(cleanId)
                                    if configModel == cleanId || configModel == model {
                                        Image(systemName: "checkmark")
                                    }
                                }
                            }
                        }
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "cpu")
                    .font(.system(size: 9))
                if let provName = activeProviderName {
                    Text(provName)
                        .font(.system(size: 10, weight: .medium))
                        .lineLimit(1)
                    Text("·")
                        .font(.system(size: 10))
                }
                Text(modelShortName)
                    .font(.system(size: 10, design: .monospaced))
                    .lineLimit(1)
                Image(systemName: "chevron.down")
                    .font(.system(size: 7))
            }
            .foregroundStyle(VultiTheme.inkDim)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(VultiTheme.paperDeep, in: Capsule())
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        } // else
    }

    private func roleColorForAgent(_ agent: GatewayClient.AgentResponse) -> Color {
        let hex = CanvasLayout.roleColors[(agent.role ?? "").lowercased()] ?? CanvasLayout.defaultColor
        return Color(hex: hex)
    }

    /// Strip routing prefixes from model IDs — backend expects clean IDs like "anthropic/claude-opus-4"
    static func stripProviderPrefix(_ model: String) -> String {
        let prefixes = ["openrouter/", "openai/openai/", "anthropic/anthropic/"]
        for prefix in prefixes {
            if model.hasPrefix(prefix) {
                return String(model.dropFirst(prefix.count))
            }
        }
        return model
    }
}
