import SwiftUI
import Observation

@Observable
final class AppState {
    // MARK: - Services
    let gateway = GatewayService()
    let client: GatewayClient
    let vultisig = VultisigService()

    // MARK: - Cached data (fetched from gateway)
    var agentList: [GatewayClient.AgentResponse] = []
    var relationships: [GatewayClient.RelationshipResponse] = []
    var ownerInfo: GatewayClient.OwnerResponse?
    var defaultAgentId: String?

    /// Avatar cache — avoids re-fetching base64 PNGs every refresh cycle
    private var avatarCache: [String: String] = [:]

    // MARK: - UI State
    var hasToken = false
    var isGatewayRunning = false
    var onboardingComplete = Persistence.onboardingComplete
    var activeAgentId: String?
    var panelMode: PanelMode?
    var notifications: [AppNotification] = []
    var pendingOps = 0
    /// Tracks which agents have already had their daily introspect triggered this app session.
    var introspectedAgents: Set<String> = []

    var isBusy: Bool { pendingOps > 0 }

    /// Refresh timer replaces FileWatcher
    private var refreshTimer: Timer?

    enum PanelMode: Equatable {
        case agent(String)
        case owner
        case settings
        case create
        case audit

        /// Agent/owner panels slide from bottom; toolbar panels slide from left
        var isBottomPanel: Bool {
            switch self {
            case .agent, .owner: return true
            case .settings, .create, .audit: return false
            }
        }
    }

    init() {
        self.client = GatewayClient(gateway: gateway)
        activeAgentId = Persistence.activeAgentId
    }

    // MARK: - Agent accessors (convenience over cached list)

    func agent(byId id: String) -> GatewayClient.AgentResponse? {
        agentList.first { $0.id == id }
    }

    // MARK: - Lifecycle

    func boot() async {
        hasToken = !(VultiHome.webToken() ?? "").isEmpty
        guard hasToken else { return }
        isGatewayRunning = await client.checkHealth()
        if !isGatewayRunning {
            try? await startGateway()
        } else {
            await refreshAgents()
        }
        startRefreshTimer()
    }

    func startGateway() async throws {
        pendingOps += 1
        defer { pendingOps -= 1 }
        try await client.start()
        for _ in 0..<30 {
            try await Task.sleep(for: .milliseconds(500))
            if await client.checkHealth() {
                isGatewayRunning = true
                await refreshAgents()
                return
            }
        }
        isGatewayRunning = await client.checkHealth()
        if isGatewayRunning {
            await refreshAgents()
        }
    }

    func stopGateway() async {
        await client.stop()
        isGatewayRunning = false
    }

    func refreshAgents() async {
        do {
            var agents = try await client.listAgents()
            // Detect default agent (the one with platforms set)
            if let def = agents.first(where: { !($0.platforms ?? []).isEmpty }) {
                defaultAgentId = def.id
            }
            // Merge avatars: use cache first, fetch missing ones
            var needsFetch: [(Int, String)] = []
            for (i, agent) in agents.enumerated() {
                if let cached = avatarCache[agent.id] {
                    agents[i].avatar = cached
                } else {
                    needsFetch.append((i, agent.id))
                }
            }
            if !needsFetch.isEmpty {
                await withTaskGroup(of: (Int, String, String?).self) { group in
                    for (i, agentId) in needsFetch {
                        group.addTask { [client] in
                            let resp = try? await client.getAvatar(agentId: agentId)
                            return (i, agentId, resp?.avatar)
                        }
                    }
                    for await (index, agentId, avatar) in group {
                        if let avatar, !avatar.isEmpty {
                            agents[index].avatar = avatar
                            avatarCache[agentId] = avatar
                        }
                    }
                }
            }
            agentList = agents
        } catch {
            // Keep existing list on error
        }
        // Refresh relationships and owner in parallel (non-critical)
        async let rels: () = refreshRelationships()
        async let own: () = refreshOwner()
        _ = await (rels, own)
    }

    /// Invalidate avatar cache for an agent (call after generating a new avatar)
    func invalidateAvatar(_ agentId: String) {
        avatarCache.removeValue(forKey: agentId)
    }

    func refreshRelationships() async {
        relationships = (try? await client.listRelationships()) ?? relationships
    }

    func refreshOwner() async {
        ownerInfo = try? await client.getOwner()
    }

    private func startRefreshTimer() {
        refreshTimer?.invalidate()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                await self.refreshAgents()
                self.isGatewayRunning = await self.client.checkHealth()
            }
        }
    }

    // MARK: - Panel helpers

    func openAgent(_ id: String) {
        activeAgentId = id
        Persistence.activeAgentId = id
        panelMode = .agent(id)
    }

    func openOwner() { panelMode = .owner }
    func openSettings() { panelMode = .settings }
    func openCreate() { panelMode = .create }
    func openAudit() { panelMode = .audit }
    func closePanel() { panelMode = nil; activeAgentId = nil }

    // MARK: - Notifications (max 50)

    func addNotification(source: String, summary: String) {
        notifications.insert(AppNotification(source: source, summary: summary), at: 0)
        if notifications.count > 50 { notifications = Array(notifications.prefix(50)) }
    }

    func dismissNotification(_ id: UUID) {
        notifications.removeAll { $0.id == id }
    }
}
