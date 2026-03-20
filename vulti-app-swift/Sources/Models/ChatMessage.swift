import Foundation

struct ChatMessage: Codable, Identifiable {
    var id: String { messageId ?? UUID().uuidString }
    var messageId: String?
    var type: String?  // "chunk", "message", "typing", "notification", "error"
    var role: String?
    var content: String?
    var agentId: String?
    var timestamp: String?

    enum CodingKeys: String, CodingKey {
        case messageId = "message_id"
        case type, role, content
        case agentId = "agent_id"
        case timestamp
    }
}

struct AppNotification: Identifiable {
    let id = UUID()
    var source: String
    var summary: String
    var date = Date()
}
