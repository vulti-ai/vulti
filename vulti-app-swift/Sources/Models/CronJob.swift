import Foundation

// Matches ~/.vulti/agents/{id}/cron/jobs.json or ~/.vulti/cron/jobs.json
struct CronFile: Codable {
    var jobs: [[String: AnyCodable]]?
    var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case jobs
        case updatedAt = "updated_at"
    }
}

struct CronJob: Identifiable {
    let id: String
    var name: String
    var prompt: String
    var schedule: String
    var scheduleDisplay: String?
    var enabled: Bool
    var state: String?
    var agentId: String?
    var createdAt: String?
    var lastOutput: String?
}

struct Rule: Identifiable {
    let id: String
    var name: String
    var condition: String
    var action: String
    var enabled: Bool
    var priority: Int
    var triggerCount: Int
    var maxTriggers: Int?
    var cooldownMinutes: Int?
    var createdAt: String?
    var lastTriggered: String?
    var agentId: String?
    var tags: [String]?
}

// Matches ~/.vulti/rules/rules.json
struct RulesFile: Codable {
    var rules: [[String: AnyCodable]]?
    var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case rules
        case updatedAt = "updated_at"
    }
}
