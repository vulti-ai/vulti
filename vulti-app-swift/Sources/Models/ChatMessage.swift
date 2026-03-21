import Foundation

struct ChatMessage: Codable, Identifiable {
    let id: String
    var messageId: String?
    var type: String?  // "chunk", "message", "typing", "notification", "error"
    var role: String?
    var content: String?
    var agentId: String?
    var timestamp: String?

    /// Primary initializer — id is derived from messageId (stable identity for SwiftUI).
    init(messageId: String, type: String? = nil, role: String? = nil,
         content: String? = nil, agentId: String? = nil, timestamp: String? = nil) {
        self.id = messageId
        self.messageId = messageId
        self.type = type
        self.role = role
        self.content = content
        self.agentId = agentId
        self.timestamp = timestamp
    }

    enum CodingKeys: String, CodingKey {
        case messageId = "message_id"
        case type, role, content
        case agentId = "agent_id"
        case timestamp
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.messageId = try c.decodeIfPresent(String.self, forKey: .messageId)
        self.id = messageId ?? UUID().uuidString
        self.type = try c.decodeIfPresent(String.self, forKey: .type)
        self.role = try c.decodeIfPresent(String.self, forKey: .role)
        self.content = try c.decodeIfPresent(String.self, forKey: .content)
        self.agentId = try c.decodeIfPresent(String.self, forKey: .agentId)
        self.timestamp = try c.decodeIfPresent(String.self, forKey: .timestamp)
    }
}

struct AppNotification: Identifiable {
    let id = UUID()
    var source: String
    var summary: String
    var date = Date()
}
