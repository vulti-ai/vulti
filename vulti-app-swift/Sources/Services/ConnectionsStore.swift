import Foundation
import Yams

/// Manages ~/.vulti/connections.yaml + env-based connections.
/// Replaces Tauri's connections.rs commands.
final class ConnectionsStore {

    // MARK: - CRUD (matches list_connections, add_connection, etc.)

    static func listConnections() -> [ConnectionEntry] {
        guard let string = VultiHome.readString(from: VultiHome.connectionsPath),
              let dict = try? YAMLDecoder().decode([String: ConnectionEntry].self, from: string) else {
            return []
        }
        return dict.values.sorted { $0.name < $1.name }
    }

    static func addConnection(_ entry: ConnectionEntry) throws {
        var dict = loadDict()
        guard dict[entry.name] == nil else {
            throw ConnectionError.alreadyExists(entry.name)
        }
        dict[entry.name] = entry
        try saveDict(dict)
    }

    static func updateConnection(name: String, updates: [String: Any]) throws -> ConnectionEntry {
        var dict = loadDict()
        guard var entry = dict[name] else { throw ConnectionError.notFound(name) }

        if let desc = updates["description"] as? String { entry.description = desc }
        if let tags = updates["tags"] as? [String] { entry.tags = tags }
        if let enabled = updates["enabled"] as? Bool { entry.enabled = enabled }
        if let creds = updates["credentials"] as? [String: String] { entry.credentials = creds }

        dict[name] = entry
        try saveDict(dict)
        return entry
    }

    static func deleteConnection(name: String) throws {
        var dict = loadDict()
        guard dict[name] != nil else { throw ConnectionError.notFound(name) }
        dict.removeValue(forKey: name)
        try saveDict(dict)
    }

    // MARK: - Internal

    private static func loadDict() -> [String: ConnectionEntry] {
        guard let string = VultiHome.readString(from: VultiHome.connectionsPath) else { return [:] }
        return (try? YAMLDecoder().decode([String: ConnectionEntry].self, from: string)) ?? [:]
    }

    private static func saveDict(_ dict: [String: ConnectionEntry]) throws {
        let yaml = try YAMLEncoder().encode(dict)
        try VultiHome.atomicWriteString(yaml, to: VultiHome.connectionsPath)
    }

    enum ConnectionError: Error, LocalizedError {
        case alreadyExists(String)
        case notFound(String)

        var errorDescription: String? {
            switch self {
            case .alreadyExists(let n): "Connection '\(n)' already exists"
            case .notFound(let n): "Connection '\(n)' not found"
            }
        }
    }
}
