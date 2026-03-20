import Foundation

/// Reads and resolves permission requests from ~/.vulti/permissions/pending.json.
/// Replaces Tauri's permissions.rs commands.
enum PermissionsStore {

    static var pendingPath: URL { VultiHome.permissionsPendingPath }

    // MARK: - Load / Save

    private static func loadPending() -> [PermissionRequest] {
        VultiHome.readJSON([PermissionRequest].self, from: pendingPath) ?? []
    }

    private static func savePending(_ requests: [PermissionRequest]) throws {
        try VultiHome.atomicWriteJSON(requests, to: pendingPath)
    }

    // MARK: - List pending (matches list_permission_requests)

    static func listPending(agentId: String? = nil) -> [PermissionRequest] {
        loadPending()
            .filter { $0.status == "pending" }
            .filter { req in
                guard let agentId else { return true }
                return req.agentId == agentId
            }
    }

    // MARK: - Resolve (matches resolve_permission)

    @discardableResult
    static func resolve(requestId: String, approved: Bool, agentStore: AgentStore? = nil) throws -> PermissionRequest {
        var requests = loadPending()
        let now = ISO8601DateFormatter().string(from: Date())

        guard let index = requests.firstIndex(where: { $0.id == requestId && $0.status == "pending" }) else {
            throw PermissionsError.notFound(requestId)
        }

        var req = requests[index]
        req = PermissionRequest(
            id: req.id,
            agentId: req.agentId,
            connectionName: req.connectionName,
            reason: req.reason,
            status: approved ? "approved" : "denied",
            createdAt: req.createdAt,
            resolvedAt: now
        )
        requests[index] = req
        try savePending(requests)

        // If approved, add connection to agent's allow list
        if approved, let agentId = req.agentId, let connectionName = req.connectionName {
            try addToAllowList(agentId: agentId, connectionName: connectionName, agentStore: agentStore)
        }

        return req
    }

    // MARK: - Allow list (matches add_to_allow_list)

    private static func addToAllowList(agentId: String, connectionName: String, agentStore: AgentStore?) throws {
        if let store = agentStore, var entry = store.registry.agents[agentId] {
            var conns = entry.allowedConnections ?? []
            if !conns.contains(connectionName) {
                conns.append(connectionName)
                entry.allowedConnections = conns
                store.registry.agents[agentId] = entry
                try store.saveRegistry()
            }
        } else {
            // Fallback: read/write registry directly (no AgentStore available)
            guard let data = VultiHome.readData(from: VultiHome.registryPath),
                  var json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  var agents = json["agents"] as? [String: Any],
                  var agent = agents[agentId] as? [String: Any] else {
                return
            }

            var conns = agent["allowed_connections"] as? [String] ?? []
            if !conns.contains(connectionName) {
                conns.append(connectionName)
                agent["allowed_connections"] = conns
                agents[agentId] = agent
                json["agents"] = agents

                let output = try JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted, .sortedKeys])
                try VultiHome.atomicWrite(to: VultiHome.registryPath, data: output)
            }
        }
    }

    // MARK: - Errors

    enum PermissionsError: Error, LocalizedError {
        case notFound(String)

        var errorDescription: String? {
            switch self {
            case .notFound(let id): "Permission request '\(id)' not found or already resolved"
            }
        }
    }
}
