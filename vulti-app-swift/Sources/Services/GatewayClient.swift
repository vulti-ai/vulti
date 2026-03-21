import Foundation

/// Thin API client over the vulti-core gateway.
/// Replaces all local file I/O stores with REST calls.
/// Mirrors api.ts from the Tauri app 1:1.
actor GatewayClient {
    private let gw: GatewayService

    init(gateway: GatewayService) {
        self.gw = gateway
    }

    // MARK: - Gateway lifecycle (delegates to GatewayService)

    func start() async throws { try await gw.start() }
    func stop() async { await gw.stop() }
    func checkHealth() async -> Bool { await gw.checkHealth() }

    // MARK: - Agents

    struct AgentResponse: Codable, Identifiable, Hashable {
        var id: String
        var name: String
        var role: String?
        var status: String?
        var avatar: String?
        var description: String?
        var createdAt: String?
        var createdFrom: String?
        var platforms: [String]?
        var allowedConnections: [String]?

        enum CodingKeys: String, CodingKey {
            case id, name, role, status, avatar, description, platforms
            case createdAt = "created_at"
            case createdFrom = "created_from"
            case allowedConnections = "allowed_connections"
        }

        func hash(into hasher: inout Hasher) { hasher.combine(id) }
        static func == (lhs: AgentResponse, rhs: AgentResponse) -> Bool { lhs.id == rhs.id }
    }

    func listAgents() async throws -> [AgentResponse] {
        try await gw.get([AgentResponse].self, path: "agents")
    }

    func getAgent(_ id: String) async throws -> AgentResponse {
        try await gw.get(AgentResponse.self, path: "agents/\(id)")
    }

    func createAgent(name: String, role: String? = nil, personality: String? = nil, model: String? = nil, inheritFrom: String? = nil) async throws -> AgentResponse {
        var body: [String: String] = ["name": name]
        if let role { body["role"] = role }
        if let personality { body["personality"] = personality }
        if let model { body["model"] = model }
        if let inheritFrom { body["inherit_from"] = inheritFrom }
        return try await gw.post(AgentResponse.self, path: "agents", body: body)
    }

    func updateAgent(_ id: String, updates: [String: String]) async throws -> AgentResponse {
        return try await gw.put(AgentResponse.self, path: "agents/\(id)", body: updates)
    }

    func deleteAgent(_ id: String) async throws {
        try await gw.delete(path: "agents/\(id)")
    }

    func generateAvatar(agentId: String) async throws {
        try await gw.generateAvatar(agentId: agentId)
    }

    struct AvatarResponse: Codable {
        var avatar: String?
        var format: String?
    }

    func getAvatar(agentId: String) async throws -> AvatarResponse {
        try await gw.get(AvatarResponse.self, path: "agents/\(agentId)/avatar")
    }

    func finalizeOnboarding(agentId: String, role: String? = nil) async throws {
        var body: [String: String] = [:]
        if let role { body["role"] = role }
        _ = try await gw.postRaw(path: "agents/\(agentId)/finalize-onboarding", body: body)
    }

    // MARK: - Sessions

    struct SessionResponse: Codable, Identifiable {
        var id: String
        var name: String?
        var agentId: String?
        var createdAt: String?
        var updatedAt: String?
        var preview: String?

        enum CodingKeys: String, CodingKey {
            case id, name, preview
            case agentId = "agent_id"
            case createdAt = "created_at"
            case updatedAt = "updated_at"
        }
    }

    struct MessageResponse: Codable {
        var id: String?
        var role: String
        var content: String
        var timestamp: String?
    }

    func listSessions(agentId: String? = nil) async throws -> [SessionResponse] {
        let path = agentId != nil ? "agents/\(agentId!)/sessions" : "sessions"
        return try await gw.get([SessionResponse].self, path: path)
    }

    func createSession(agentId: String? = nil, name: String? = nil) async throws -> SessionResponse {
        var body: [String: String] = [:]
        if let name { body["name"] = name }
        let path = agentId != nil ? "agents/\(agentId!)/sessions" : "sessions"
        return try await gw.post(SessionResponse.self, path: path, body: body)
    }

    func renameSession(_ id: String, name: String) async throws {
        _ = try await gw.patchRaw(path: "sessions/\(id)", body: ["name": name])
    }

    func deleteSession(_ id: String) async throws {
        try await gw.delete(path: "sessions/\(id)")
    }

    func getHistory(_ sessionId: String) async throws -> [MessageResponse] {
        try await gw.get([MessageResponse].self, path: "sessions/\(sessionId)/history")
    }

    // MARK: - Memories & Soul

    struct MemoriesResponse: Codable {
        var memory: String
        var user: String
    }

    struct SoulResponse: Codable {
        var content: String
    }

    func getMemories(agentId: String? = nil) async throws -> MemoriesResponse {
        let path = agentId != nil ? "agents/\(agentId!)/memories" : "memories"
        return try await gw.get(MemoriesResponse.self, path: path)
    }

    func updateMemory(file: String, content: String, agentId: String? = nil) async throws {
        let path = agentId != nil ? "agents/\(agentId!)/memories" : "memories"
        _ = try await gw.putRaw(path: path, body: ["file": file, "content": content])
    }

    func getSoul(agentId: String? = nil) async throws -> String {
        let path = agentId != nil ? "agents/\(agentId!)/soul" : "soul"
        let resp = try await gw.get(SoulResponse.self, path: path)
        return resp.content
    }

    func updateSoul(content: String, agentId: String? = nil) async throws {
        let path = agentId != nil ? "agents/\(agentId!)/soul" : "soul"
        _ = try await gw.putRaw(path: path, body: ["content": content])
    }

    // MARK: - Connections

    struct ConnectionResponse: Codable {
        var name: String
        var type: String?
        var description: String?
        var tags: [String]?
        var enabled: Bool?
    }

    func listConnections() async throws -> [ConnectionResponse] {
        try await gw.get([ConnectionResponse].self, path: "connections")
    }

    func addConnection(name: String, type: String? = nil, description: String? = nil) async throws {
        var body: [String: String] = ["name": name]
        if let type { body["type"] = type }
        if let description { body["description"] = description }
        _ = try await gw.postRaw(path: "connections", body: body)
    }

    func updateConnection(name: String, updates: [String: String]) async throws {
        _ = try await gw.putRaw(path: "connections/\(name)", body: updates)
    }

    func deleteConnection(name: String) async throws {
        try await gw.delete(path: "connections/\(name)")
    }

    // MARK: - Relationships

    struct RelationshipResponse: Codable {
        var rawId: String?
        var fromAgentId: String?
        var toAgentId: String?
        var type: String?
        var matrixRoomId: String?

        /// Stable identifier for views
        var stableId: String { rawId ?? "\(fromAgentId ?? "")-\(toAgentId ?? "")" }

        enum CodingKeys: String, CodingKey {
            case type
            case rawId = "id"
            case fromAgentId = "from_agent_id"
            case toAgentId = "to_agent_id"
            case matrixRoomId = "matrix_room_id"
        }
    }

    func listRelationships() async throws -> [RelationshipResponse] {
        try await gw.get([RelationshipResponse].self, path: "relationships")
    }

    func createRelationship(fromId: String, toId: String, type: String = "manages") async throws -> RelationshipResponse {
        return try await gw.post(RelationshipResponse.self, path: "relationships", body: [
            "from_agent_id": fromId, "to_agent_id": toId, "type": type,
        ])
    }

    func deleteRelationship(_ id: String) async throws {
        try await gw.delete(path: "relationships/\(id)")
    }

    // MARK: - Skills

    struct SkillResponse: Codable {
        var name: String
        var description: String?
        var category: String?
    }

    func listAvailableSkills() async throws -> [SkillResponse] {
        try await gw.get([SkillResponse].self, path: "skills")
    }

    func listAgentSkills(agentId: String) async throws -> [SkillResponse] {
        try await gw.get([SkillResponse].self, path: "agents/\(agentId)/skills")
    }

    func installSkill(agentId: String, name: String) async throws {
        _ = try await gw.postRaw(path: "agents/\(agentId)/skills", body: ["name": name])
    }

    func removeSkill(agentId: String, name: String) async throws {
        try await gw.delete(path: "agents/\(agentId)/skills/\(name)")
    }

    // MARK: - Cron

    struct CronResponse: Codable, Identifiable {
        var id: String
        var name: String?
        var prompt: String?
        var schedule: String?
        var status: String?
        var lastRun: String?
        var lastOutput: String?

        enum CodingKeys: String, CodingKey {
            case id, name, prompt, schedule, status
            case lastRun = "last_run"
            case lastOutput = "last_output"
        }

        /// Whether the job is active (convenience for views)
        var enabled: Bool { status != "paused" }
    }

    func listCron(agentId: String? = nil) async throws -> [CronResponse] {
        let path = agentId != nil ? "agents/\(agentId!)/cron" : "cron"
        return try await gw.get([CronResponse].self, path: path)
    }

    func createCron(agentId: String? = nil, name: String, prompt: String, schedule: String) async throws -> CronResponse {
        let path = agentId != nil ? "agents/\(agentId!)/cron" : "cron"
        return try await gw.post(CronResponse.self, path: path, body: [
            "name": name, "prompt": prompt, "schedule": schedule,
        ])
    }

    func updateCron(jobId: String, updates: [String: String]) async throws {
        _ = try await gw.putRaw(path: "cron/\(jobId)", body: updates)
    }

    func deleteCron(jobId: String) async throws {
        try await gw.delete(path: "cron/\(jobId)")
    }

    // MARK: - Rules

    struct RuleResponse: Codable, Identifiable {
        var id: String
        var name: String?
        var condition: String?
        var action: String?
        var enabled: Bool?
        var priority: Int?
        var triggerCount: Int?
        var maxTriggers: Int?
        var cooldownMinutes: Int?
        var lastTriggeredAt: String?
        var tags: [String]?

        enum CodingKeys: String, CodingKey {
            case id, name, condition, action, enabled, priority, tags
            case triggerCount = "trigger_count"
            case maxTriggers = "max_triggers"
            case cooldownMinutes = "cooldown_minutes"
            case lastTriggeredAt = "last_triggered_at"
        }
    }

    func listRules(agentId: String? = nil) async throws -> [RuleResponse] {
        let path = agentId != nil ? "agents/\(agentId!)/rules" : "rules"
        return try await gw.get([RuleResponse].self, path: path)
    }

    /// Create rule — API returns `{"success": true, "rule": {...}}`, so we unwrap the nested object.
    struct CreateRuleWrapper: Codable {
        var success: Bool?
        var rule: RuleResponse?
        var error: String?
    }

    func createRule(condition: String, action: String, name: String? = nil, priority: Int = 0, cooldownMinutes: Int? = nil, agentId: String? = nil) async throws -> RuleResponse {
        var body: [String: String] = ["condition": condition, "action": action]
        if let name { body["name"] = name }
        if priority != 0 { body["priority"] = String(priority) }
        if let cd = cooldownMinutes { body["cooldown_minutes"] = String(cd) }
        let path = agentId != nil ? "agents/\(agentId!)/rules" : "rules"
        let wrapper = try await gw.post(CreateRuleWrapper.self, path: path, body: body)
        if let error = wrapper.error { throw NSError(domain: "vulti", code: 0, userInfo: [NSLocalizedDescriptionKey: error]) }
        guard let rule = wrapper.rule else { throw NSError(domain: "vulti", code: 0, userInfo: [NSLocalizedDescriptionKey: "No rule in response"]) }
        return rule
    }

    func updateRule(ruleId: String, updates: [String: String]) async throws {
        _ = try await gw.putRaw(path: "rules/\(ruleId)", body: updates)
    }

    func deleteRule(ruleId: String) async throws {
        try await gw.delete(path: "rules/\(ruleId)")
    }

    // MARK: - Secrets & Providers

    struct SecretResponse: Codable {
        var key: String
        var maskedValue: String?
        var isSet: Bool?
        var category: String?

        enum CodingKeys: String, CodingKey {
            case key, category
            case maskedValue = "masked_value"
            case isSet = "is_set"
        }
    }

    struct ProviderResponse: Codable {
        var id: String
        var name: String
        var authenticated: Bool
        var models: [String]?
        var envKeys: [String]?

        enum CodingKeys: String, CodingKey {
            case id, name, authenticated, models
            case envKeys = "env_keys"
        }
    }

    struct OAuthResponse: Codable {
        var service: String
        var valid: Bool
        var scopes: [String]?
        var hasRefresh: Bool?

        enum CodingKeys: String, CodingKey {
            case service, valid, scopes
            case hasRefresh = "has_refresh"
        }
    }

    func listSecrets() async throws -> [SecretResponse] {
        try await gw.get([SecretResponse].self, path: "secrets")
    }

    func addSecret(key: String, value: String) async throws {
        _ = try await gw.postRaw(path: "secrets", body: ["key": key, "value": value])
    }

    func deleteSecret(key: String) async throws {
        try await gw.delete(path: "secrets/\(key)")
    }

    func listProviders() async throws -> [ProviderResponse] {
        try await gw.get([ProviderResponse].self, path: "providers")
    }

    func oauthStatus() async throws -> [OAuthResponse] {
        try await gw.get([OAuthResponse].self, path: "oauth")
    }

    // MARK: - Audit

    struct AuditEventResponse: Codable, Identifiable {
        var id: String { traceId ?? "\(ts ?? "")-\(agentId ?? "")-\(event ?? "")" }
        var ts: String?
        var event: String?
        var agentId: String?
        var traceId: String?
        var details: [String: AnyCodable]?

        enum CodingKeys: String, CodingKey {
            case ts, event, details
            case agentId = "agent_id"
            case traceId = "trace_id"
        }

        /// Convenience: extract platform from details
        var platform: String? {
            details?["platform"]?.value as? String
        }

        /// Convenience: extract a message preview from details
        var messagePreview: String? {
            let keys = ["message_preview", "response_preview", "prompt_preview"]
            for key in keys {
                if let val = details?[key]?.value as? String, !val.isEmpty { return val }
            }
            return nil
        }

        /// Convenience: extract detail string from details
        var detailSummary: String {
            var parts: [String] = []
            if let t = details?["target"]?.value as? String { parts.append("to \(t)") }
            if let s = details?["sender"]?.value as? String { parts.append("from \(s)") }
            if let c = details?["connection"]?.value as? String { parts.append(c) }
            if let j = details?["job_name"]?.value as? String { parts.append(j) }
            if let r = details?["rule_name"]?.value as? String { parts.append(r) }
            return parts.joined(separator: " ")
        }
    }

    func listAuditEvents(n: Int = 50, agentId: String? = nil, traceId: String? = nil, eventType: String? = nil) async throws -> [AuditEventResponse] {
        var params: [String] = ["n=\(n)"]
        if let agentId { params.append("agent_id=\(agentId)") }
        if let traceId { params.append("trace_id=\(traceId)") }
        if let eventType { params.append("event_type=\(eventType)") }
        return try await gw.get([AuditEventResponse].self, path: "audit?\(params.joined(separator: "&"))")
    }

    // MARK: - Permissions

    struct PermissionResponse: Codable {
        var id: String
        var agentId: String?
        var connectionName: String?
        var reason: String?
        var status: String?
        var createdAt: String?

        enum CodingKeys: String, CodingKey {
            case id, reason, status
            case agentId = "agent_id"
            case connectionName = "connection_name"
            case createdAt = "created_at"
        }
    }

    func listPermissions(agentId: String? = nil) async throws -> [PermissionResponse] {
        let query = agentId != nil ? "?agent_id=\(agentId!)" : ""
        return try await gw.get([PermissionResponse].self, path: "permissions\(query)")
    }

    func resolvePermission(requestId: String, approved: Bool) async throws {
        _ = try await gw.postRaw(path: "permissions/\(requestId)/resolve", body: ["approved": approved])
    }

    // MARK: - Owner

    struct OwnerResponse: Codable {
        var name: String?
        var about: String?
        var avatar: String?
    }

    func getOwner() async throws -> OwnerResponse {
        try await gw.get(OwnerResponse.self, path: "owner")
    }

    func updateOwner(name: String, about: String? = nil) async throws {
        var body: [String: String] = ["name": name]
        if let about { body["about"] = about }
        _ = try await gw.putRaw(path: "owner", body: body)
    }

    func generateOwnerAvatar() async throws {
        try await gw.generateOwnerAvatar()
    }

    // MARK: - Agent Config

    func getAgentConfig(agentId: String) async throws -> [String: AnyCodable] {
        try await gw.get([String: AnyCodable].self, path: "agents/\(agentId)/config")
    }

    // MARK: - Agent Wallet

    func getWallet(agentId: String) async throws -> [String: AnyCodable] {
        try await gw.get([String: AnyCodable].self, path: "agents/\(agentId)/wallet")
    }

    func saveWallet(agentId: String, wallet: [String: Any]) async throws {
        // Encode wallet as generic JSON
        let data = try JSONSerialization.data(withJSONObject: wallet)
        let dict = try JSONSerialization.jsonObject(with: data) as? [String: String] ?? [:]
        _ = try await gw.putRaw(path: "agents/\(agentId)/wallet", body: dict)
    }

    // MARK: - Agent Vault

    struct VaultResponse: Codable {
        var vaultId: String?
        var name: String?
        var type: String?
        var chains: Int?
        var createdAt: Double?
        var addresses: [String: String]?

        enum CodingKeys: String, CodingKey {
            case name, type, chains, addresses, createdAt
            case vaultId = "vault_id"
        }
    }

    struct VaultPortfolioResponse: Codable {
        var data: PortfolioData?

        struct PortfolioData: Codable {
            var portfolio: Portfolio?
        }

        struct Portfolio: Codable {
            var totalValue: TotalValue?
            var chainBalances: [ChainBalance]?
        }

        struct TotalValue: Codable {
            var amount: String?
            var currency: String?
        }

        struct ChainBalance: Codable {
            var chain: String?
            var value: TotalValue?
        }
    }

    func getVault(agentId: String) async throws -> VaultResponse {
        try await gw.get(VaultResponse.self, path: "agents/\(agentId)/vault")
    }

    func getVaultPortfolio(agentId: String) async throws -> VaultPortfolioResponse {
        try await gw.get(VaultPortfolioResponse.self, path: "agents/\(agentId)/vault/portfolio")
    }

    func deleteVault(agentId: String) async throws {
        try await gw.delete(path: "agents/\(agentId)/vault")
    }

    // MARK: - Pane Widgets

    struct PaneResponse: Codable {
        var version: Int?
        var tabs: [String: [PaneWidget]]?
    }

    struct PaneWidget: Codable, Identifiable {
        var id: String?
        var type: String?
        var title: String?
        var data: AnyCodable?

        /// Convert gateway response to the typed PaneWidget model used by WidgetView.
        func toPaneWidget() -> VultiHub.PaneWidget? {
            guard let typeStr = type, let wt = WidgetType(rawValue: typeStr) else { return nil }
            let wd: WidgetData
            if let raw = data?.value as? [String: Any] {
                // Re-encode through JSONSerialization → JSONDecoder for typed WidgetData
                if let jsonData = try? JSONSerialization.data(withJSONObject: raw),
                   let decoded = try? JSONDecoder().decode(WidgetData.self, from: jsonData) {
                    wd = decoded
                } else {
                    wd = WidgetData()
                }
            } else {
                wd = WidgetData()
            }
            var pw = VultiHub.PaneWidget(type: wt, title: title, data: wd)
            if let widgetId = id { pw.id = widgetId }
            return pw
        }
    }

    func getPaneWidgets(agentId: String, sessionId: String? = nil) async throws -> PaneResponse {
        let query = sessionId != nil ? "?session_id=\(sessionId!)" : ""
        return try await gw.get(PaneResponse.self, path: "agents/\(agentId)/pane\(query)")
    }

    func getSessionPaneWidgets(sessionId: String) async throws -> PaneResponse {
        try await gw.get(PaneResponse.self, path: "sessions/\(sessionId)/pane")
    }

    func clearPaneWidgets(agentId: String, tab: String? = nil) async throws {
        let query = tab != nil ? "?tab=\(tab!)" : ""
        try await gw.delete(path: "agents/\(agentId)/pane\(query)")
    }

    func removePaneWidget(agentId: String, widgetId: String) async throws {
        try await gw.delete(path: "agents/\(agentId)/pane/widgets/\(widgetId)")
    }

    func reorderPaneWidgets(agentId: String, widgetIds: [String]) async throws {
        _ = try await gw.putRaw(path: "agents/\(agentId)/pane/reorder", body: ["widget_ids": widgetIds])
    }

    func resetDefaultWidgets(agentId: String) async throws -> PaneResponse {
        let raw = try await gw.postRaw(path: "agents/\(agentId)/pane/reset-defaults", body: [String: String]())
        let data = try JSONSerialization.data(withJSONObject: raw)
        return try JSONDecoder().decode(PaneResponse.self, from: data)
    }

    // MARK: - Integrations & Status

    struct IntegrationResponse: Codable {
        var id: String
        var name: String
        var category: String?
        var status: String?
        var details: [String: AnyCodable]?
        var updatedAt: String?

        enum CodingKeys: String, CodingKey {
            case id, name, category, status, details
            case updatedAt = "updated_at"
        }
    }

    func listIntegrations() async throws -> [IntegrationResponse] {
        try await gw.get([IntegrationResponse].self, path: "integrations")
    }

    func getStatus() async throws -> [String: AnyCodable] {
        try await gw.get([String: AnyCodable].self, path: "status")
    }

    func getChannels() async throws -> [String: AnyCodable] {
        try await gw.get([String: AnyCodable].self, path: "channels")
    }

    // MARK: - Analytics

    func getAnalytics(days: Int = 30, agentId: String? = nil) async throws -> [String: AnyCodable] {
        var query = "days=\(days)"
        if let agentId { query += "&agent_id=\(agentId)" }
        return try await gw.get([String: AnyCodable].self, path: "analytics?\(query)")
    }

    /// Typed analytics fetch — decodes directly into AnalyticsData
    func getAnalyticsData(days: Int = 30, agentId: String? = nil) async throws -> AnalyticsData {
        var query = "days=\(days)"
        if let agentId { query += "&agent_id=\(agentId)" }
        return try await gw.get(AnalyticsData.self, path: "analytics?\(query)")
    }

    // MARK: - Inbox & Contacts

    func getInbox() async throws -> [InboxItem] {
        try await gw.getInbox()
    }

    func getContacts() async throws -> [Contact] {
        try await gw.getContacts()
    }

    // MARK: - Matrix (delegates to GatewayService)

    func registerMatrix(username: String, password: String) async throws {
        try await gw.registerMatrix(username: username, password: password)
    }

    func updateMatrixCredentials(username: String, password: String) async throws {
        try await gw.updateMatrixCredentials(username: username, password: password)
    }

    func createRelationshipRoom(fromId: String, toId: String) async throws {
        try await gw.createRelationshipRoom(fromId: fromId, toId: toId)
    }

    func createOwnerDM(agentId: String) async throws {
        try await gw.createOwnerDM(agentId: agentId)
    }

    func onboardAgentToMatrix(agentId: String) async throws {
        try await gw.onboardAgentToMatrix(agentId: agentId)
    }

    func createSquadRoom(name: String, agentIds: [String]) async throws {
        try await gw.createSquadRoom(name: name, agentIds: agentIds)
    }

    func resetMatrixRooms() async throws {
        try await gw.resetMatrixRooms()
    }
}
