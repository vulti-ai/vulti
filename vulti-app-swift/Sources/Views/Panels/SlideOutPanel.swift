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
            case .onboard(let id):
                Text("Setup: \(app.agent(byId: id)?.name ?? id)")
                    .font(.system(size: 16, weight: .bold)).foregroundStyle(VultiTheme.inkSoft)
            case .audit:
                Text("Audit Log")
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
        case .onboard(let id):
            OnboardingView(agentId: id)
        case .audit:
            AuditView()
        }
    }
}

/// Agent header: avatar, name, role badge, @id, default badge, delete button
struct AgentPanelHeader: View {
    let agentId: String
    @Environment(AppState.self) private var app
    @State private var isGeneratingAvatar = false

    private var agent: GatewayClient.AgentResponse? {
        app.agent(byId: agentId)
    }

    var body: some View {
        HStack(spacing: 10) {
            // Avatar (32px — warm paper bg)
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(VultiTheme.paperWarm)
                    .frame(width: 32, height: 32)

                if let avatarStr = agent?.avatar, !avatarStr.isEmpty {
                    if avatarStr.count <= 2, avatarStr.unicodeScalars.allSatisfy({ $0.properties.isEmoji }) {
                        Text(avatarStr)
                            .font(.system(size: 18))
                    } else if let data = Data(base64Encoded: avatarStr),
                              let img = NSImage(data: data) {
                        Image(nsImage: img)
                            .resizable()
                            .frame(width: 32, height: 32)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                    } else {
                        Text(String((agent?.name ?? "A").prefix(1)).uppercased())
                            .font(.system(size: 13, weight: .semibold))
                    }
                } else {
                    Text(String((agent?.name ?? "A").prefix(1)).uppercased())
                        .font(.system(size: 13, weight: .semibold))
                }
            }

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(agent?.name ?? agentId)
                        .font(.system(size: 16, weight: .bold))
                        .foregroundStyle(VultiTheme.inkSoft)

                    // Generate Avatar button
                    if isGeneratingAvatar {
                        ProgressView()
                            .controlSize(.mini)
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

                    Button("Delete") {
                        Task {
                            try? await app.client.deleteAgent(agentId)
                            await app.refreshAgents()
                        }
                        app.closePanel()
                    }
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(VultiTheme.coral)
                    .buttonStyle(.plain)
                }

                Text("@\(agentId)-vulti")
                    .font(.system(size: 11))
                    .foregroundStyle(VultiTheme.inkMuted)
                    .monospaced()
            }
        }
    }
}
