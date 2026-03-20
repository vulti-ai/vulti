import Foundation
import GRDB

/// Read-only analytics queries against ~/.vulti/state.db.
/// Ported from src-tauri/src/analytics.rs.
enum AnalyticsStore {

    // MARK: - Public

    static func getAnalytics(days: Int = 30, agentId: String? = nil) throws -> AnalyticsData {
        let dbPath = VultiHome.stateDbPath
        guard FileManager.default.fileExists(atPath: dbPath) else {
            return AnalyticsData(empty: true, error: "No session database found")
        }

        var config = Configuration()
        config.readonly = true
        let pool = try DatabasePool(path: dbPath, configuration: config)

        let cutoff = Date().timeIntervalSince1970 - Double(days) * 86400

        return try pool.read { db in
            // Session count
            let (whereClause, args) = buildFilter(cutoff: cutoff, agentId: agentId)
            let countSQL = "SELECT COUNT(*) FROM sessions s WHERE \(whereClause)"
            let sessionCount = try Int.fetchOne(db, sql: countSQL, arguments: StatementArguments(args)) ?? 0

            if sessionCount == 0 {
                return AnalyticsData(empty: true)
            }

            // Overview
            let overview = try fetchOverview(db, cutoff: cutoff, agentId: agentId)

            // Models
            let models = try fetchModels(db, cutoff: cutoff, agentId: agentId)

            // Platforms
            let platforms = try fetchPlatforms(db, cutoff: cutoff, agentId: agentId)

            // Tools
            let tools = try fetchTools(db, cutoff: cutoff, agentId: agentId)

            // Activity
            let activity = try fetchActivity(db, cutoff: cutoff, agentId: agentId)

            return AnalyticsData(
                empty: false,
                overview: overview,
                models: models,
                platforms: platforms,
                tools: tools,
                activity: activity
            )
        }
    }

    // MARK: - Private helpers

    private static func buildFilter(cutoff: Double, agentId: String?) -> (String, [any DatabaseValueConvertible]) {
        var conditions = ["s.started_at >= ?"]
        var args: [any DatabaseValueConvertible] = [cutoff]
        if let agentId {
            conditions.append("(s.agent_id = ? OR s.agent_id IS NULL)")
            args.append(agentId)
        }
        return (conditions.joined(separator: " AND "), args)
    }

    private static func fetchOverview(_ db: Database, cutoff: Double, agentId: String?) throws -> AnalyticsOverview {
        let (wc, args) = buildFilter(cutoff: cutoff, agentId: agentId)
        let sql = """
            SELECT COUNT(*),
                   COALESCE(SUM(s.message_count), 0),
                   COALESCE(SUM(s.tool_call_count), 0),
                   COALESCE(SUM(s.input_tokens), 0),
                   COALESCE(SUM(s.output_tokens), 0),
                   COALESCE(SUM(CASE WHEN s.ended_at IS NOT NULL THEN s.ended_at - s.started_at ELSE 0 END), 0)
            FROM sessions s WHERE \(wc)
            """
        let row = try Row.fetchOne(db, sql: sql, arguments: StatementArguments(args))!
        let totalSessions: Int = row[0]
        let totalMessages: Int = row[1]
        let totalToolCalls: Int = row[2]
        let inputTokens: Int = row[3]
        let outputTokens: Int = row[4]
        let totalSeconds: Double = row[5]
        let totalTokens = inputTokens + outputTokens
        let avgMsgs = totalSessions > 0 ? Double(totalMessages) / Double(totalSessions) : 0
        let avgDur = totalSessions > 0 ? totalSeconds / Double(totalSessions) : 0

        return AnalyticsOverview(
            totalSessions: totalSessions,
            totalMessages: totalMessages,
            totalToolCalls: totalToolCalls,
            totalInputTokens: inputTokens,
            totalOutputTokens: outputTokens,
            totalTokens: totalTokens,
            estimatedCost: 0,
            totalHours: totalSeconds / 3600,
            avgMessagesPerSession: avgMsgs,
            avgDuration: avgDur
        )
    }

    private static func fetchModels(_ db: Database, cutoff: Double, agentId: String?) throws -> [ModelStats] {
        let (wc, args) = buildFilter(cutoff: cutoff, agentId: agentId)
        let sql = """
            SELECT s.model, COUNT(*), COALESCE(SUM(s.input_tokens + s.output_tokens), 0)
            FROM sessions s WHERE \(wc) AND s.model IS NOT NULL
            GROUP BY s.model ORDER BY 2 DESC
            """
        return try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args)).map { row in
            ModelStats(
                model: row[0] as String? ?? "unknown",
                sessions: row[1],
                totalTokens: row[2],
                cost: 0
            )
        }
    }

    private static func fetchPlatforms(_ db: Database, cutoff: Double, agentId: String?) throws -> [PlatformStats] {
        let (wc, args) = buildFilter(cutoff: cutoff, agentId: agentId)
        let sql = """
            SELECT s.source, COUNT(*), COALESCE(SUM(s.message_count), 0), COALESCE(SUM(s.input_tokens + s.output_tokens), 0)
            FROM sessions s WHERE \(wc) AND s.source IS NOT NULL
            GROUP BY s.source ORDER BY 2 DESC
            """
        return try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args)).map { row in
            PlatformStats(
                platform: row[0] as String? ?? "unknown",
                sessions: row[1],
                messages: row[2],
                totalTokens: row[3]
            )
        }
    }

    private static func fetchTools(_ db: Database, cutoff: Double, agentId: String?) throws -> [ToolStats] {
        let (wc, args) = buildFilter(cutoff: cutoff, agentId: agentId)
        let sql = """
            SELECT m.tool_name, COUNT(*), COUNT(DISTINCT m.session_id)
            FROM messages m JOIN sessions s ON s.id = m.session_id
            WHERE \(wc) AND m.role = 'tool' AND m.tool_name IS NOT NULL
            GROUP BY m.tool_name ORDER BY 2 DESC LIMIT 20
            """
        return try Row.fetchAll(db, sql: sql, arguments: StatementArguments(args)).map { row in
            ToolStats(
                toolName: row[0] as String? ?? "unknown",
                callCount: row[1],
                sessions: row[2]
            )
        }
    }

    private static func fetchActivity(_ db: Database, cutoff: Double, agentId: String?) throws -> ActivityStats {
        // Hourly distribution
        let (wc1, args1) = buildFilter(cutoff: cutoff, agentId: agentId)
        let hourlySql = """
            SELECT CAST(strftime('%H', s.started_at, 'unixepoch') AS INTEGER) AS hr, COUNT(*)
            FROM sessions s WHERE \(wc1) GROUP BY hr ORDER BY hr
            """
        var hourly = [Int](repeating: 0, count: 24)
        for row in try Row.fetchAll(db, sql: hourlySql, arguments: StatementArguments(args1)) {
            let hr: Int = row[0]
            let count: Int = row[1]
            if hr >= 0 && hr < 24 { hourly[hr] = count }
        }

        // Daily distribution (day of week: 0=Sun..6=Sat)
        let (wc2, args2) = buildFilter(cutoff: cutoff, agentId: agentId)
        let dailySql = """
            SELECT CAST(strftime('%w', s.started_at, 'unixepoch') AS INTEGER) AS dow, COUNT(*)
            FROM sessions s WHERE \(wc2) GROUP BY dow ORDER BY dow
            """
        var daily = [Int](repeating: 0, count: 7)
        for row in try Row.fetchAll(db, sql: dailySql, arguments: StatementArguments(args2)) {
            let dow: Int = row[0]
            let count: Int = row[1]
            if dow >= 0 && dow < 7 { daily[dow] = count }
        }

        return ActivityStats(hourly: hourly, daily: daily)
    }
}
