import Foundation
import Yams

/// File I/O layer for ~/.vulti/ directory tree.
/// Replaces Tauri's vulti_home.rs — atomic writes, directory resolution, file watching.
final class VultiHome: Sendable {

    // MARK: - Paths (matches Rust vulti_home() + agents.rs paths)

    static let root: URL = {
        if let custom = ProcessInfo.processInfo.environment["VULTI_HOME"] {
            return URL(fileURLWithPath: custom)
        }
        return FileManager.default.homeDirectoryForCurrentUser.appending(path: ".vulti")
    }()

    static var stateDbPath: String { root.appending(path: "state.db").path() }
    static var webTokenPath: URL { root.appending(path: "web_token") }
    static var gatewayStatePath: URL { root.appending(path: "gateway_state.json") }
    static var channelDirectoryPath: URL { root.appending(path: "channel_directory.json") }
    static var configPath: URL { root.appending(path: "config.yaml") }
    static var gatewayConfigPath: URL { root.appending(path: "gateway.json") }
    static var connectionsPath: URL { root.appending(path: "connections.yaml") }
    static var envPath: URL { root.appending(path: ".env") }
    static var registryPath: URL { root.appending(path: "agents/registry.json") }
    static var rulesPath: URL { root.appending(path: "rules/rules.json") }
    static var globalCronPath: URL { root.appending(path: "cron/jobs.json") }
    static var permissionsPendingPath: URL { root.appending(path: "permissions/pending.json") }
    static var skillsDir: URL { root.appending(path: "skills") }
    static var continuwuityDir: URL { root.appending(path: "continuwuity") }

    static var vultisigBin: URL {
        root.appending(path: "vultisig-cli/node_modules/.bin/vultisig")
    }

    static func agentDir(_ id: String) -> URL { root.appending(path: "agents/\(id)") }
    static func agentConfig(_ id: String) -> URL { agentDir(id).appending(path: "config.yaml") }
    static func agentSoul(_ id: String) -> URL { agentDir(id).appending(path: "SOUL.md") }
    static func agentWallet(_ id: String) -> URL { agentDir(id).appending(path: "creditcard.json") }
    static func agentCron(_ id: String) -> URL { agentDir(id).appending(path: "cron/jobs.json") }
    static func agentUser(_ id: String) -> URL { agentDir(id).appending(path: "memories/USER.md") }
    static func agentMemory(_ id: String) -> URL { agentDir(id).appending(path: "memories/MEMORY.md") }
    static func agentSkillsDir(_ id: String) -> URL { agentDir(id).appending(path: "skills") }
    static func agentAvatar(_ id: String) -> URL { agentDir(id).appending(path: "avatar.png") }

    // MARK: - Atomic write (write tmp, fsync, rename — matches Rust impl)

    static func atomicWrite(to url: URL, data: Data) throws {
        let dir = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])

        let tmp = url.appendingPathExtension("tmp")
        try data.write(to: tmp)

        // fsync
        if let fh = try? FileHandle(forWritingTo: tmp) {
            fh.synchronizeFile()
            fh.closeFile()
        }

        // Set permissions 0o600 for sensitive files
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: tmp.path())

        // Atomic rename
        if FileManager.default.fileExists(atPath: url.path()) {
            try FileManager.default.removeItem(at: url)
        }
        try FileManager.default.moveItem(at: tmp, to: url)
    }

    static func atomicWriteString(_ content: String, to url: URL) throws {
        guard let data = content.data(using: .utf8) else { return }
        try atomicWrite(to: url, data: data)
    }

    static func atomicWriteJSON<T: Encodable>(_ value: T, to url: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(value)
        try atomicWrite(to: url, data: data)
    }

    // MARK: - Read helpers

    static func readString(from url: URL) -> String? {
        try? String(contentsOf: url, encoding: .utf8)
    }

    static func readData(from url: URL) -> Data? {
        try? Data(contentsOf: url)
    }

    static func readJSON<T: Decodable>(_ type: T.Type, from url: URL) -> T? {
        guard let data = readData(from: url) else { return nil }
        return try? JSONDecoder().decode(type, from: data)
    }

    static func readRawJSON(from url: URL) -> [String: Any]? {
        guard let data = readData(from: url) else { return nil }
        return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    }

    static func readYAML<T: Decodable>(_ type: T.Type, from url: URL) -> T? {
        guard let string = readString(from: url) else { return nil }
        return try? YAMLDecoder().decode(type, from: string)
    }

    static func webToken() -> String? {
        readString(from: webTokenPath)?.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - Directory helpers

    static func ensureDir(_ url: URL) throws {
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    }

    static func fileExists(_ url: URL) -> Bool {
        FileManager.default.fileExists(atPath: url.path())
    }

    static func listFiles(in dir: URL, withExtension ext: String? = nil) -> [URL] {
        guard let contents = try? FileManager.default.contentsOfDirectory(
            at: dir, includingPropertiesForKeys: [.contentModificationDateKey]
        ) else { return [] }
        if let ext {
            return contents.filter { $0.pathExtension == ext }
        }
        return contents
    }
}
