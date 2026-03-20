import Foundation
import GRDB

/// Read-only access to vulti's SQLite state.db.
/// Replaces Tauri's session/history commands.
final class SessionStore: Sendable {
    private let dbPool: DatabasePool?
    private let writablePool: DatabasePool?
    private let dbPath: String

    init(dbPath: String) {
        self.dbPath = dbPath
        do {
            var config = Configuration()
            config.readonly = true
            self.dbPool = try DatabasePool(path: dbPath, configuration: config)
        } catch {
            self.dbPool = nil
        }
        // Writable pool for delete operations
        do {
            self.writablePool = try DatabasePool(path: dbPath)
        } catch {
            self.writablePool = nil
        }
    }

    // MARK: - Sessions

    func listSessions(agentId: String? = nil, limit: Int = 50) throws -> [Session] {
        guard let db = dbPool else { return [] }
        return try db.read { db in
            var sql = "SELECT * FROM sessions"
            var args: [any DatabaseValueConvertible] = []

            if let agentId {
                sql += " WHERE agent_id = ?"
                args.append(agentId)
            }

            sql += " ORDER BY started_at DESC LIMIT ?"
            args.append(limit)

            return try Session.fetchAll(db, sql: sql, arguments: StatementArguments(args))
        }
    }

    // MARK: - Messages

    func messages(sessionId: String) throws -> [Message] {
        guard let db = dbPool else { return [] }
        return try db.read { db in
            try Message.fetchAll(
                db,
                sql: "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                arguments: [sessionId]
            )
        }
    }

    // MARK: - Delete

    func deleteSession(id: String) throws {
        guard let db = writablePool else { return }
        try db.write { db in
            try db.execute(sql: "DELETE FROM messages WHERE session_id = ?", arguments: [id])
            try db.execute(sql: "DELETE FROM sessions WHERE id = ?", arguments: [id])
        }
    }

    // MARK: - Search

    func search(query: String, limit: Int = 20) throws -> [Message] {
        guard let db = dbPool else { return [] }
        return try db.read { db in
            try Message.fetchAll(
                db,
                sql: """
                    SELECT m.* FROM messages m
                    JOIN messages_fts fts ON m.rowid = fts.rowid
                    WHERE messages_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                arguments: [query, limit]
            )
        }
    }
}
