import Foundation
import Observation
import Yams

/// Agent registry and per-agent CRUD.
/// Replaces Tauri's agents.rs commands.
@Observable
final class AgentStore {
    var registry = AgentRegistry(agents: [:])
    var agents: [AgentEntry] { registry.sortedAgents }
    var defaultAgentId: String? { registry.defaultAgent }
    var relationships: [RelationshipEntry] { registry.relationships ?? [] }
    var owner: OwnerEntry? { registry.owner }

    private let reservedIds = Set(["agent", "agents", "api", "ws", "system", "interagent"])

    // MARK: - Registry I/O

    func loadRegistry() async {
        guard let reg = VultiHome.readJSON(AgentRegistry.self, from: VultiHome.registryPath) else {
            return
        }
        registry = reg
    }

    func saveRegistry() throws {
        try VultiHome.atomicWriteJSON(registry, to: VultiHome.registryPath)
    }

    func agent(byId id: String) -> AgentEntry? {
        registry.agents[id]
    }

    // MARK: - CRUD (matches agents.rs create_agent, update_agent, delete_agent)

    func createAgent(
        name: String, role: String? = nil, avatar: String? = nil,
        description: String? = nil, personality: String? = nil,
        model: String? = nil, inheritFrom: String? = nil
    ) throws -> AgentEntry {
        // Generate ID from name
        var agentId = name.lowercased()
            .replacingOccurrences(of: " ", with: "-")
            .filter { $0.isLetter || $0.isNumber || $0 == "-" }
        agentId = String(agentId.prefix(32))

        if agentId.isEmpty { agentId = "agent" }
        guard !reservedIds.contains(agentId) else {
            throw AgentError.reservedId(agentId)
        }

        // Deduplicate
        var finalId = agentId
        var suffix = 2
        while registry.agents[finalId] != nil {
            finalId = "\(agentId)-\(suffix)"
            suffix += 1
        }

        let now = ISO8601DateFormatter().string(from: Date())
        let entry = AgentEntry(
            id: finalId, name: name, role: role, status: "active",
            createdAt: now, createdFrom: inheritFrom, avatar: avatar,
            description: description ?? ""
        )

        // Create directory structure
        let dir = VultiHome.agentDir(finalId)
        try VultiHome.ensureDir(dir)
        for sub in ["memories", "cron", "sessions", "skills"] {
            try VultiHome.ensureDir(dir.appending(path: sub))
        }

        // Config
        if let inheritFrom, let srcConfig = VultiHome.readString(from: VultiHome.agentConfig(inheritFrom)) {
            try VultiHome.atomicWriteString(srcConfig, to: VultiHome.agentConfig(finalId))
        }
        if let model {
            var config = VultiHome.readYAML(AgentConfig.self, from: VultiHome.agentConfig(finalId)) ?? AgentConfig()
            config.model = model
            let yaml = try YAMLEncoder().encode(config)
            try VultiHome.atomicWriteString(yaml, to: VultiHome.agentConfig(finalId))
        }

        // Soul
        if let inheritFrom, personality == nil {
            if let srcSoul = VultiHome.readString(from: VultiHome.agentSoul(inheritFrom)) {
                try VultiHome.atomicWriteString(srcSoul, to: VultiHome.agentSoul(finalId))
            }
        }
        if let personality {
            try VultiHome.atomicWriteString(personality, to: VultiHome.agentSoul(finalId))
        }

        // Save to registry
        registry.agents[finalId] = entry
        try saveRegistry()

        return entry
    }

    func updateAgent(_ id: String, updates: [String: Any]) throws -> AgentEntry {
        guard var entry = registry.agents[id] else {
            throw AgentError.notFound(id)
        }

        if let name = updates["name"] as? String { entry.name = name }
        if let role = updates["role"] as? String { entry.role = role }
        if let status = updates["status"] as? String { entry.status = status }
        if let avatar = updates["avatar"] as? String { entry.avatar = avatar }
        if let desc = updates["description"] as? String { entry.description = desc }
        if let conns = updates["allowedConnections"] as? [String] { entry.allowedConnections = conns }
        if let conns = updates["allowed_connections"] as? [String] { entry.allowedConnections = conns }

        if let personality = updates["personality"] as? String {
            try VultiHome.atomicWriteString(personality, to: VultiHome.agentSoul(id))
        }

        if let model = updates["model"] as? String {
            var config = VultiHome.readYAML(AgentConfig.self, from: VultiHome.agentConfig(id)) ?? AgentConfig()
            config.model = model
            let yaml = try YAMLEncoder().encode(config)
            try VultiHome.atomicWriteString(yaml, to: VultiHome.agentConfig(id))
        }

        registry.agents[id] = entry
        try saveRegistry()
        return entry
    }

    func deleteAgent(_ id: String) throws {
        guard registry.agents[id] != nil else { throw AgentError.notFound(id) }
        registry.agents.removeValue(forKey: id)
        registry.relationships?.removeAll { $0.source == id || $0.target == id }
        if registry.defaultAgent == id { registry.defaultAgent = nil }
        try saveRegistry()

        // Remove agent directory
        let dir = VultiHome.agentDir(id)
        if VultiHome.fileExists(dir) {
            try FileManager.default.removeItem(at: dir)
        }
    }

    // MARK: - Relationships (matches agents.rs relationship commands)

    func createRelationship(source: String, target: String, type: String = "manages") throws {
        let rel = RelationshipEntry(source: source, target: target, type: type)
        if registry.relationships == nil { registry.relationships = [] }
        registry.relationships?.append(rel)
        try saveRegistry()
    }

    func deleteRelationship(source: String, target: String) throws {
        registry.relationships?.removeAll { $0.source == source && $0.target == target }
        try saveRegistry()
    }

    // MARK: - Owner

    func updateOwner(name: String?, about: String?) throws {
        registry.owner = OwnerEntry(name: name, about: about)
        try saveRegistry()
    }

    // MARK: - Per-agent file reads

    func soul(for id: String) -> String? { VultiHome.readString(from: VultiHome.agentSoul(id)) }
    func config(for id: String) -> AgentConfig? { VultiHome.readYAML(AgentConfig.self, from: VultiHome.agentConfig(id)) }
    func creditCard(for id: String) -> CreditCardFile? { VultiHome.readJSON(CreditCardFile.self, from: VultiHome.agentWallet(id)) }
    func userMemory(for id: String) -> String? { VultiHome.readString(from: VultiHome.agentUser(id)) }
    func agentMemory(for id: String) -> String? { VultiHome.readString(from: VultiHome.agentMemory(id)) }

    func saveCreditCard(_ card: CreditCardFile, for id: String) throws {
        var existing = self.creditCard(for: id) ?? CreditCardFile()
        if card.creditCard != nil { existing.creditCard = card.creditCard }
        try VultiHome.atomicWriteJSON(existing, to: VultiHome.agentWallet(id))
    }

    func saveSoul(_ content: String, for id: String) throws {
        try VultiHome.atomicWriteString(content, to: VultiHome.agentSoul(id))
    }

    func saveMemory(_ content: String, for id: String) throws {
        try VultiHome.atomicWriteString(content, to: VultiHome.agentMemory(id))
    }

    func saveUserMemory(_ content: String, for id: String) throws {
        try VultiHome.atomicWriteString(content, to: VultiHome.agentUser(id))
    }

    // MARK: - Avatar (matches get_agent_avatar)

    func avatar(for id: String) -> Data? {
        VultiHome.readData(from: VultiHome.agentAvatar(id))
    }

    func avatarBase64(for id: String) -> String? {
        guard let data = avatar(for: id) else { return nil }
        return "data:image/png;base64,\(data.base64EncodedString())"
    }

    // MARK: - Vault file (matches get_agent_vault)

    func vaultInfo(for id: String) -> VaultInfo? {
        let files = VultiHome.listFiles(in: VultiHome.agentDir(id), withExtension: "vult")
        guard let file = files.first,
              let data = VultiHome.readData(from: file),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        let vaultId = (json["uid"] as? String) ?? (json["vault_id"] as? String) ?? (json["vaultId"] as? String) ?? ""
        let name = file.deletingPathExtension().lastPathComponent
        return VaultInfo(name: name, vaultId: vaultId, filePath: file.path())
    }

    func deleteVault(for id: String) throws {
        let dir = VultiHome.agentDir(id)
        let vultFiles = VultiHome.listFiles(in: dir, withExtension: "vult")
        for f in vultFiles { try FileManager.default.removeItem(at: f) }

        // Remove vault:*.json files
        let allFiles = VultiHome.listFiles(in: dir)
        for f in allFiles where f.lastPathComponent.hasPrefix("vault:") && f.pathExtension == "json" {
            try FileManager.default.removeItem(at: f)
        }

        // Clear crypto from wallet
        if var w = wallet(for: id) {
            w.crypto = nil
            try VultiHome.atomicWriteJSON(w, to: VultiHome.agentWallet(id))
        }
    }

    enum AgentError: Error, LocalizedError {
        case notFound(String)
        case reservedId(String)

        var errorDescription: String? {
            switch self {
            case .notFound(let id): "Agent '\(id)' not found"
            case .reservedId(let id): "'\(id)' is a reserved ID"
            }
        }
    }
}
