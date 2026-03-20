import Foundation

/// Manages ~/.vulti/.env secrets and provider detection.
/// Replaces Tauri's secrets.rs commands.
final class SecretsStore {

    // MARK: - Secrets (matches list_secrets, add_secret, delete_secret)

    static func listSecrets() -> [SecretEntry] {
        guard let content = VultiHome.readString(from: VultiHome.envPath) else { return [] }
        return content.components(separatedBy: .newlines)
            .compactMap { line -> SecretEntry? in
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                guard !trimmed.isEmpty, !trimmed.hasPrefix("#") else { return nil }
                let parts = trimmed.split(separator: "=", maxSplits: 1)
                guard parts.count == 2 else { return nil }
                let key = String(parts[0]).trimmingCharacters(in: .whitespaces)
                var value = String(parts[1]).trimmingCharacters(in: .whitespaces)
                // Strip quotes
                if (value.hasPrefix("\"") && value.hasSuffix("\"")) ||
                   (value.hasPrefix("'") && value.hasSuffix("'")) {
                    value = String(value.dropFirst().dropLast())
                }
                return SecretEntry(key: key, maskedValue: maskValue(value), category: categorize(key))
            }
    }

    static func addSecret(key: String, value: String) throws {
        guard key.range(of: #"^[A-Z][A-Z0-9_]*$"#, options: .regularExpression) != nil else {
            throw SecretsError.invalidKey(key)
        }
        guard !value.isEmpty else { throw SecretsError.emptyValue }

        var lines = (VultiHome.readString(from: VultiHome.envPath) ?? "")
            .components(separatedBy: .newlines)

        // Update existing or append
        let prefix = "\(key)="
        if let idx = lines.firstIndex(where: { $0.hasPrefix(prefix) || $0.hasPrefix("\(key) =") }) {
            lines[idx] = "\(key)=\(value)"
        } else {
            lines.append("\(key)=\(value)")
        }

        try VultiHome.atomicWriteString(lines.joined(separator: "\n"), to: VultiHome.envPath)
    }

    static func deleteSecret(key: String) throws {
        let content = VultiHome.readString(from: VultiHome.envPath) ?? ""
        let lines = content.components(separatedBy: .newlines)
            .filter { !$0.hasPrefix("\(key)=") && !$0.hasPrefix("\(key) =") }
        try VultiHome.atomicWriteString(lines.joined(separator: "\n"), to: VultiHome.envPath)
    }

    // MARK: - Providers (matches list_providers)

    static let providerDefs: [(name: String, envKeys: [String], models: [String])] = [
        ("Anthropic", ["ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN"],
         ["claude-opus-4.6", "claude-sonnet-4.6", "claude-haiku-4.5"]),
        ("OpenRouter", ["OPENROUTER_API_KEY"],
         ["anthropic/claude-opus-4.6", "anthropic/claude-sonnet-4.6", "google/gemini-2.5-pro",
          "google/gemini-2.5-flash", "deepseek/deepseek-chat", "deepseek/deepseek-reasoner"]),
        ("OpenAI", ["OPENAI_API_KEY"], ["gpt-4o", "gpt-4.1", "o3"]),
        ("DeepSeek", ["DEEPSEEK_API_KEY"], ["deepseek-chat", "deepseek-reasoner"]),
        ("Google", ["GOOGLE_API_KEY", "GEMINI_API_KEY"], ["gemini-2.5-pro", "gemini-2.5-flash"]),
    ]

    static func listProviders() -> [ProviderInfo] {
        let envContent = VultiHome.readString(from: VultiHome.envPath) ?? ""
        let envKeys = Set(envContent.components(separatedBy: .newlines)
            .compactMap { line -> String? in
                let parts = line.split(separator: "=", maxSplits: 1)
                guard parts.count == 2 else { return nil }
                let key = String(parts[0]).trimmingCharacters(in: .whitespaces)
                let val = String(parts[1]).trimmingCharacters(in: .whitespaces)
                    .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
                return val.isEmpty ? nil : key
            })

        return providerDefs.map { def in
            let authed = def.envKeys.contains { envKeys.contains($0) }
            return ProviderInfo(name: def.name, authenticated: authed, models: def.models, envKeys: def.envKeys)
        }
    }

    // MARK: - OAuth status (matches get_oauth_status)

    static func oauthStatus() -> [OAuthStatus] {
        var results: [OAuthStatus] = []

        // Google
        if let json = VultiHome.readRawJSON(from: VultiHome.root.appending(path: "google_token.json")) {
            let connected = json["token"] != nil
            let scopes = (json["scopes"] as? [String])
            let hasRefresh = json["refresh_token"] != nil
            results.append(OAuthStatus(service: "Google", connected: connected, scopes: scopes, hasRefreshToken: hasRefresh))
        }

        // X/Twitter
        if let json = VultiHome.readRawJSON(from: VultiHome.root.appending(path: "x_oauth2_token.json")) {
            let connected = json["access_token"] != nil
            let hasRefresh = json["refresh_token"] != nil
            results.append(OAuthStatus(service: "X", connected: connected, scopes: nil, hasRefreshToken: hasRefresh))
        }

        // Telegram
        let telegramPath = VultiHome.root.appending(path: "telegram_user_session.session")
        if VultiHome.fileExists(telegramPath) {
            results.append(OAuthStatus(service: "Telegram", connected: true, scopes: nil, hasRefreshToken: false))
        }

        return results
    }

    // MARK: - Helpers

    private static func maskValue(_ value: String) -> String {
        if value.count <= 5 { return "***" }
        if value.count <= 12 { return "***...\(value.suffix(2))" }
        return "\(value.prefix(5))...\(value.suffix(4))"
    }

    private static func categorize(_ key: String) -> String {
        let k = key.uppercased()
        if ["ANTHROPIC", "OPENROUTER", "OPENAI", "DEEPSEEK", "GEMINI", "GOOGLE_API"].contains(where: { k.hasPrefix($0) }) {
            return "LLM Providers"
        }
        if ["TELEGRAM", "DISCORD", "SLACK", "SIGNAL", "WHATSAPP", "MATRIX"].contains(where: { k.hasPrefix($0) }) {
            return "Messaging"
        }
        if ["ELEVENLABS", "EDGE_TTS"].contains(where: { k.hasPrefix($0) }) {
            return "Voice & Audio"
        }
        if k.hasPrefix("GOOGLE") { return "Google" }
        return "Other"
    }

    enum SecretsError: Error, LocalizedError {
        case invalidKey(String)
        case emptyValue

        var errorDescription: String? {
            switch self {
            case .invalidKey(let k): "Invalid key '\(k)': must be uppercase alphanumeric + underscores"
            case .emptyValue: "Value cannot be empty"
            }
        }
    }
}
