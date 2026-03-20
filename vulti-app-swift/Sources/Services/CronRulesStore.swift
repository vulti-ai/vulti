import Foundation

/// Cron job and rule CRUD — reads/writes jobs.json and rules.json files.
/// Replaces Tauri's cron.rs and rules.rs commands.
final class CronRulesStore {

    // MARK: - Cron Jobs

    static func listCronJobs(agentId: String) -> [CronJob] {
        let path = VultiHome.agentCron(agentId)
        guard let data = VultiHome.readData(from: path),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let jobs = json["jobs"] as? [[String: Any]] else { return [] }

        return jobs.compactMap { job in
            guard let id = job["id"] as? String,
                  let prompt = job["prompt"] as? String else { return nil }

            // Read latest output
            let outputDir = VultiHome.root.appending(path: "cron/output/\(id)")
            var lastOutput: String?
            if let files = try? FileManager.default.contentsOfDirectory(at: outputDir, includingPropertiesForKeys: [.contentModificationDateKey]) {
                let sorted = files.sorted {
                    let d1 = (try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? Date.distantPast
                    let d2 = (try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? Date.distantPast
                    return d1 > d2
                }
                if let latest = sorted.first {
                    lastOutput = VultiHome.readString(from: latest)
                    if let output = lastOutput, output.count > 500 {
                        lastOutput = String(output.prefix(500)) + "..."
                    }
                }
            }

            let schedule = job["schedule"] as? [String: Any]
            let scheduleDisplay = job["schedule_display"] as? String
                ?? schedule?["display"] as? String
                ?? "unknown"

            return CronJob(
                id: id,
                name: job["name"] as? String ?? "Untitled",
                prompt: prompt,
                schedule: scheduleDisplay,
                scheduleDisplay: scheduleDisplay,
                enabled: job["enabled"] as? Bool ?? true,
                state: job["state"] as? String,
                agentId: job["agent"] as? String ?? agentId,
                createdAt: job["created_at"] as? String,
                lastOutput: lastOutput
            )
        }
    }

    static func createCronJob(agentId: String, name: String, prompt: String, schedule: String) throws -> CronJob {
        let path = VultiHome.agentCron(agentId)
        var file = loadCronFile(from: path)

        let id = String(UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(12))
        let now = ISO8601DateFormatter().string(from: Date())

        let job: [String: Any] = [
            "id": id,
            "name": name.isEmpty ? "Job \(id.prefix(4))" : name,
            "prompt": prompt,
            "schedule": ["kind": "interval", "display": schedule],
            "schedule_display": schedule,
            "enabled": true,
            "state": "scheduled",
            "agent": agentId,
            "created_at": now,
        ]

        file.append(job)
        try saveCronFile(file, to: path)

        return CronJob(id: id, name: name, prompt: prompt, schedule: schedule, enabled: true, agentId: agentId, createdAt: now)
    }

    static func updateCronJob(agentId: String, jobId: String, updates: [String: Any]) throws {
        let path = VultiHome.agentCron(agentId)
        var file = loadCronFile(from: path)

        guard let idx = file.firstIndex(where: { ($0["id"] as? String) == jobId }) else { return }

        for (key, val) in updates {
            file[idx][key] = val
        }

        // Map status to enabled/state
        if let status = updates["status"] as? String {
            file[idx]["enabled"] = status != "paused"
            file[idx]["state"] = status == "paused" ? "paused" : "scheduled"
        }

        try saveCronFile(file, to: path)
    }

    static func deleteCronJob(agentId: String, jobId: String) throws {
        let path = VultiHome.agentCron(agentId)
        var file = loadCronFile(from: path)
        file.removeAll { ($0["id"] as? String) == jobId }
        try saveCronFile(file, to: path)
    }

    // MARK: - Rules

    static func listRules(agentId: String? = nil) -> [Rule] {
        guard let data = VultiHome.readData(from: VultiHome.rulesPath),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let rules = json["rules"] as? [[String: Any]] else { return [] }

        return rules.compactMap { r in
            guard let id = r["id"] as? String else { return nil }
            let rAgentId = r["agent"] as? String

            if let filterAgent = agentId, rAgentId != filterAgent { return nil }

            return Rule(
                id: id,
                name: r["name"] as? String ?? "Untitled",
                condition: r["condition"] as? String ?? "",
                action: r["action"] as? String ?? "",
                enabled: r["enabled"] as? Bool ?? true,
                priority: r["priority"] as? Int ?? 0,
                triggerCount: r["trigger_count"] as? Int ?? 0,
                maxTriggers: r["max_triggers"] as? Int,
                cooldownMinutes: r["cooldown_minutes"] as? Int,
                createdAt: r["created_at"] as? String,
                lastTriggered: r["last_triggered_at"] as? String,
                agentId: rAgentId,
                tags: r["tags"] as? [String]
            )
        }
    }

    static func createRule(agentId: String, name: String, condition: String, action: String, priority: Int = 0, cooldown: Int? = nil) throws -> Rule {
        let id = String(UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(12))
        let now = ISO8601DateFormatter().string(from: Date())

        var rulesFile = loadRulesFile()
        let rule: [String: Any] = [
            "id": id, "name": name, "condition": condition, "action": action,
            "enabled": true, "priority": priority, "trigger_count": 0,
            "cooldown_minutes": cooldown as Any, "created_at": now, "agent": agentId
        ]
        rulesFile.append(rule)
        try saveRulesFile(rulesFile)

        return Rule(id: id, name: name, condition: condition, action: action, enabled: true, priority: priority, triggerCount: 0, cooldownMinutes: cooldown, createdAt: now, agentId: agentId)
    }

    static func updateRule(ruleId: String, updates: [String: Any]) throws {
        var rulesFile = loadRulesFile()
        guard let idx = rulesFile.firstIndex(where: { ($0["id"] as? String) == ruleId }) else { return }
        for (key, val) in updates { rulesFile[idx][key] = val }
        try saveRulesFile(rulesFile)
    }

    static func deleteRule(ruleId: String) throws {
        var rulesFile = loadRulesFile()
        rulesFile.removeAll { ($0["id"] as? String) == ruleId }
        try saveRulesFile(rulesFile)
    }

    // MARK: - Internal helpers

    private static func loadCronFile(from path: URL) -> [[String: Any]] {
        guard let data = VultiHome.readData(from: path),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let jobs = json["jobs"] as? [[String: Any]] else { return [] }
        return jobs
    }

    private static func saveCronFile(_ jobs: [[String: Any]], to path: URL) throws {
        let wrapper: [String: Any] = ["jobs": jobs, "updated_at": ISO8601DateFormatter().string(from: Date())]
        let data = try JSONSerialization.data(withJSONObject: wrapper, options: [.prettyPrinted, .sortedKeys])
        try VultiHome.atomicWrite(to: path, data: data)
    }

    private static func loadRulesFile() -> [[String: Any]] {
        guard let data = VultiHome.readData(from: VultiHome.rulesPath),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let rules = json["rules"] as? [[String: Any]] else { return [] }
        return rules
    }

    private static func saveRulesFile(_ rules: [[String: Any]]) throws {
        let wrapper: [String: Any] = ["rules": rules, "updated_at": ISO8601DateFormatter().string(from: Date())]
        let data = try JSONSerialization.data(withJSONObject: wrapper, options: [.prettyPrinted, .sortedKeys])
        try VultiHome.atomicWrite(to: VultiHome.rulesPath, data: data)
    }
}
