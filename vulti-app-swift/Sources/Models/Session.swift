import Foundation
import GRDB

struct Session: Codable, FetchableRecord, Identifiable {
    let id: String
    var source: String?
    var model: String?
    var agentId: String?
    var parentSessionId: String?
    var startedAt: String?
    var endedAt: String?
    var messageCount: Int?
    var tokenCount: Int?

    enum CodingKeys: String, CodingKey {
        case id, source, model
        case agentId = "agent_id"
        case parentSessionId = "parent_session_id"
        case startedAt = "started_at"
        case endedAt = "ended_at"
        case messageCount = "message_count"
        case tokenCount = "token_count"
    }
}

struct Message: Codable, FetchableRecord, Identifiable {
    var id: Int64?
    let sessionId: String
    var role: String
    var content: String?
    var toolCalls: String?
    var createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id = "rowid"
        case sessionId = "session_id"
        case role, content
        case toolCalls = "tool_calls"
        case createdAt = "created_at"
    }
}
