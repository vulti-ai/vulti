import Foundation

// MARK: - Registry (matches ~/.vulti/agents/registry.json)

struct AgentRegistry: Codable {
    var version: UInt?
    var defaultAgent: String?
    var agents: [String: AgentEntry]
    var relationships: [RelationshipEntry]?
    var owner: OwnerEntry?

    enum CodingKeys: String, CodingKey {
        case version
        case defaultAgent = "default_agent"
        case agents
        case relationships
        case owner
    }

    /// Sorted agent list by created_at
    var sortedAgents: [AgentEntry] {
        agents.values.sorted { ($0.createdAt ?? "") < ($1.createdAt ?? "") }
    }
}

struct AgentEntry: Codable, Identifiable, Hashable {
    let id: String
    var name: String
    var role: String?
    var status: String?
    var createdAt: String?
    var createdFrom: String?
    var avatar: String?
    var description: String?
    var allowedConnections: [String]?

    // UI-only
    var isDefault: Bool?
    var platforms: [String]?

    enum CodingKeys: String, CodingKey {
        case id, name, role, status, avatar, description
        case createdAt = "created_at"
        case createdFrom = "created_from"
        case allowedConnections = "allowed_connections"
        case isDefault = "is_default"
        case platforms
    }

    func hash(into hasher: inout Hasher) { hasher.combine(id) }
    static func == (lhs: AgentEntry, rhs: AgentEntry) -> Bool { lhs.id == rhs.id }
}

struct RelationshipEntry: Codable, Identifiable {
    var id: String { "\(source)-\(target)" }
    var source: String
    var target: String
    var type: String?
}

struct OwnerEntry: Codable {
    var name: String?
    var about: String?
}

// MARK: - Agent Config (matches ~/.vulti/agents/{id}/config.yaml)

struct AgentConfig: Codable {
    var model: String?
    var toolsets: [String]?
    var reasoningEffort: String?
    var terminalBackend: String?
    var tools: [String]?

    enum CodingKeys: String, CodingKey {
        case model, toolsets, tools
        case reasoningEffort = "reasoning_effort"
        case terminalBackend = "terminal_backend"
    }
}

// MARK: - Permission Request (matches ~/.vulti/permissions/pending.json)

struct PermissionRequest: Codable, Identifiable {
    let id: String
    let agentId: String?
    let connectionName: String?
    let reason: String?
    let status: String  // "pending", "approved", "denied"
    let createdAt: String?
    let resolvedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, reason, status
        case agentId = "agent_id"
        case connectionName = "connection_name"
        case createdAt = "created_at"
        case resolvedAt = "resolved_at"
    }
}

// MARK: - Connection (matches ~/.vulti/connections.yaml entries)

struct ConnectionEntry: Codable, Identifiable {
    var id: String { name }
    var name: String
    var type: String?
    var description: String?
    var tags: [String]?
    var credentials: [String: String]?
    var mcp: [String: AnyCodable]?
    var providesToolsets: [String]?
    var enabled: Bool?

    enum CodingKeys: String, CodingKey {
        case name, type, description, tags, credentials, mcp, enabled
        case providesToolsets = "provides_toolsets"
    }
}

// MARK: - Secrets & Providers

struct SecretEntry: Identifiable {
    var id: String { key }
    let key: String
    let maskedValue: String
    let category: String
}

struct ProviderInfo: Identifiable {
    var id: String { name }
    let name: String
    let authenticated: Bool
    let models: [String]
    let envKeys: [String]
}

struct OAuthStatus: Identifiable {
    var id: String { service }
    let service: String
    let connected: Bool
    let scopes: [String]?
    let hasRefreshToken: Bool
}

// MARK: - Skill

struct Skill: Codable, Identifiable {
    var id: String { name }
    var name: String
    var description: String?
    var category: String?
    var installed: Bool?
    var path: String?
}

// MARK: - Integration

struct IntegrationInfo: Identifiable {
    var id: String { platformId }
    let platformId: String
    let name: String
    let category: String
    let status: String  // "connected", "error", "unknown"
    let details: [String: String]
    let updatedAt: String?
}

// MARK: - Audit Event (matches JSONL from Rust audit.rs)

struct AuditEvent: Codable, Identifiable {
    let id: String
    let timestamp: String
    let eventType: String
    let agentId: String
    let traceId: String?
    let details: [String: AnyCodable]?

    enum CodingKeys: String, CodingKey {
        case timestamp = "ts"
        case eventType = "event"
        case agentId = "agent_id"
        case traceId = "trace_id"
        case details
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        timestamp = try container.decode(String.self, forKey: .timestamp)
        eventType = try container.decode(String.self, forKey: .eventType)
        agentId = try container.decode(String.self, forKey: .agentId)
        traceId = try container.decodeIfPresent(String.self, forKey: .traceId)
        details = try container.decodeIfPresent([String: AnyCodable].self, forKey: .details)
        // Use trace_id as stable identifier, fall back to a composite key
        id = traceId ?? "\(timestamp)-\(agentId)-\(eventType)"
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

// MARK: - Inbox & Contacts

struct InboxItem: Codable, Identifiable {
    let id: String
    let source: String?
    let sender: String?
    let preview: String?
    let timestamp: String?
    let read: Bool?
    let agentId: String?

    enum CodingKeys: String, CodingKey {
        case id, source, sender, preview, timestamp, read
        case agentId = "agent_id"
    }
}

struct Contact: Codable, Identifiable {
    let id: String
    let name: String
    let platforms: [ContactPlatform]?
    let lastInteraction: String?
    let tags: [String]?

    enum CodingKeys: String, CodingKey {
        case id, name, platforms, tags
        case lastInteraction = "last_interaction"
    }
}

struct ContactPlatform: Codable {
    let platform: String
    let handle: String
}

// MARK: - AnyCodable helper

struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) { self.value = value }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { value = NSNull() }
        else if let b = try? container.decode(Bool.self) { value = b }
        else if let i = try? container.decode(Int.self) { value = i }
        else if let d = try? container.decode(Double.self) { value = d }
        else if let s = try? container.decode(String.self) { value = s }
        else if let arr = try? container.decode([AnyCodable].self) { value = arr.map(\.value) }
        else if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues(\.value)
        }
        else { value = "" }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let s as String: try container.encode(s)
        case let i as Int: try container.encode(i)
        case let d as Double: try container.encode(d)
        case let b as Bool: try container.encode(b)
        case let arr as [Any]: try container.encode(arr.map { AnyCodable($0) })
        case let dict as [String: Any]: try container.encode(dict.mapValues { AnyCodable($0) })
        default: try container.encodeNil()
        }
    }
}
