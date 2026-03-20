import Foundation

/// Reads gateway_state.json and aggregates integration status.
/// Replaces Tauri's status.rs commands.
final class IntegrationsStore {

    // MARK: - System status (matches get_system_status)

    static func systemStatus() -> [String: Any] {
        VultiHome.readRawJSON(from: VultiHome.gatewayStatePath)
            ?? ["gateway_state": "unknown", "platforms": [:] as [String: Any]]
    }

    // MARK: - Channel directory (matches get_channel_directory)

    static func channelDirectory() -> [String: Any] {
        VultiHome.readRawJSON(from: VultiHome.channelDirectoryPath)
            ?? ["platforms": [:] as [String: Any]]
    }

    // MARK: - Integrations (matches get_integrations)

    static func listIntegrations() -> [IntegrationInfo] {
        var results: [IntegrationInfo] = []

        // Read gateway state for platform statuses
        let state = VultiHome.readRawJSON(from: VultiHome.gatewayStatePath) ?? [:]
        let platforms = state["platforms"] as? [String: Any] ?? [:]

        let platformNames: [String: (String, String)] = [
            "matrix": ("Matrix", "Messaging"),
            "telegram": ("Telegram", "Messaging"),
            "discord": ("Discord", "Messaging"),
            "slack": ("Slack", "Messaging"),
            "whatsapp": ("WhatsApp", "Messaging"),
            "signal": ("Signal", "Messaging"),
            "email": ("Email", "Messaging"),
            "home_assistant": ("Home Assistant", "Smart Home"),
            "google": ("Google", "Productivity"),
        ]

        for (key, value) in platforms {
            let info = value as? [String: Any] ?? [:]
            let status = info["status"] as? String ?? "unknown"
            let (name, category) = platformNames[key] ?? (key.capitalized, "Other")

            var details: [String: String] = [:]
            for (k, v) in info {
                if let s = v as? String { details[k] = s }
            }

            results.append(IntegrationInfo(
                platformId: key, name: name, category: category,
                status: status, details: details,
                updatedAt: info["updated_at"] as? String
            ))
        }

        // Matrix special handling
        let ownerCreds = VultiHome.readRawJSON(
            from: VultiHome.continuwuityDir.appending(path: "owner_credentials.json")
        )
        if let creds = ownerCreds {
            if !results.contains(where: { $0.platformId == "matrix" }) {
                var details: [String: String] = [:]
                if let u = creds["username"] as? String { details["owner_username"] = u }
                if let p = creds["password"] as? String { details["owner_password"] = p }
                if let h = creds["homeserver_url"] as? String { details["homeserver_url"] = h }
                results.append(IntegrationInfo(
                    platformId: "matrix", name: "Matrix", category: "Messaging",
                    status: "connected", details: details, updatedAt: nil
                ))
            }
        }

        return results.sorted { $0.name < $1.name }
    }
}
