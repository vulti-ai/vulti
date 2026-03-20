import Foundation

/// Manages the vulti gateway process (Python backend on localhost:8080).
/// Replaces Tauri's gateway start/stop/health + API proxy commands.
actor GatewayService {
    private var gatewayProcess: Process?
    private let baseURL = URL(string: "http://localhost:8080")!

    // MARK: - Process management (matches start_gateway, stop_gateway, check_gateway)

    func start() throws {
        guard gatewayProcess == nil else { return }

        // Find vulti binary (matches Rust search order)
        let home = FileManager.default.homeDirectoryForCurrentUser.path()
        let candidates = [
            "\(home)/.local/bin/vulti",
            "\(home)/.vulti/bin/vulti",
            "/usr/local/bin/vulti",
        ]

        var vultiPath: String?
        for path in candidates {
            if FileManager.default.isExecutableFile(atPath: path) {
                vultiPath = path
                break
            }
        }

        // Fallback: which via login shell
        if vultiPath == nil {
            let which = Process()
            which.executableURL = URL(fileURLWithPath: "/bin/zsh")
            which.arguments = ["-lc", "which vulti"]
            let pipe = Pipe()
            which.standardOutput = pipe
            try which.run()
            which.waitUntilExit()
            let output = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if let output, !output.isEmpty, which.terminationStatus == 0 {
                vultiPath = output
            }
        }

        guard let path = vultiPath else {
            throw GatewayError.binaryNotFound
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", "\(path) gateway run --replace"]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice

        try process.run()
        gatewayProcess = process
    }

    func stop() {
        guard let process = gatewayProcess, process.isRunning else {
            gatewayProcess = nil
            return
        }
        process.terminate()
        process.waitUntilExit()
        gatewayProcess = nil
    }

    func checkHealth() async -> Bool {
        let url = baseURL.appending(path: "api/status")
        var request = URLRequest(url: url)
        request.timeoutInterval = 2

        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            // Any HTTP response (including 401) means gateway is running
            return (response as? HTTPURLResponse) != nil
        } catch {
            return false
        }
    }

    // MARK: - API client (proxies to gateway REST API)

    func get<T: Decodable>(_ type: T.Type, path: String) async throws -> T {
        try await apiRequest(type, path: path)
    }

    func getRaw(path: String) async throws -> [String: Any] {
        let url = URL(string: "api/\(path)", relativeTo: baseURL)!
        var request = URLRequest(url: url)
        addAuth(&request)
        let (data, _) = try await URLSession.shared.data(for: request)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    func post<T: Decodable>(_ type: T.Type, path: String, body: any Encodable) async throws -> T {
        try await apiRequest(type, path: path, method: "POST", body: body)
    }

    func put<T: Decodable>(_ type: T.Type, path: String, body: any Encodable) async throws -> T {
        try await apiRequest(type, path: path, method: "PUT", body: body)
    }

    func postRaw(path: String, body: any Encodable) async throws -> [String: Any] {
        let url = URL(string: "api/\(path)", relativeTo: baseURL)!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuth(&request)
        request.httpBody = try JSONEncoder().encode(body)
        let (data, _) = try await URLSession.shared.data(for: request)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    func putRaw(path: String, body: any Encodable) async throws -> [String: Any] {
        let url = URL(string: "api/\(path)", relativeTo: baseURL)!
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuth(&request)
        request.httpBody = try JSONEncoder().encode(body)
        let (data, _) = try await URLSession.shared.data(for: request)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    func delete(path: String) async throws {
        let url = URL(string: "api/\(path)", relativeTo: baseURL)!
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        addAuth(&request)
        _ = try await URLSession.shared.data(for: request)
    }

    private func apiRequest<T: Decodable>(
        _ type: T.Type,
        path: String,
        method: String = "GET",
        body: (any Encodable)? = nil
    ) async throws -> T {
        let url = URL(string: "api/\(path)", relativeTo: baseURL)!
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuth(&request)

        if let body {
            request.httpBody = try JSONEncoder().encode(body)
        }

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw GatewayError.badStatus((response as? HTTPURLResponse)?.statusCode ?? 0)
        }

        return try JSONDecoder().decode(type, from: data)
    }

    private func addAuth(_ request: inout URLRequest) {
        if let token = VultiHome.webToken() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
    }

    // MARK: - Inbox & Contacts

    func getInbox() async throws -> [InboxItem] {
        try await get([InboxItem].self, path: "inbox")
    }

    func getContacts() async throws -> [Contact] {
        try await get([Contact].self, path: "contacts")
    }

    // MARK: - Agent onboarding / avatar

    /// POST /api/agents/{id}/generate-avatar — fire-and-forget avatar generation.
    func generateAvatar(agentId: String) async throws {
        let url = baseURL.appending(path: "api/agents/\(agentId)/generate-avatar")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuth(&request)
        _ = try await URLSession.shared.data(for: request)
    }

    /// POST /api/agents/{id}/finalize-onboarding — marks onboarding complete.
    func finalizeOnboarding(agentId: String) async throws {
        let url = baseURL.appending(path: "api/agents/\(agentId)/finalize-onboarding")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuth(&request)
        _ = try await URLSession.shared.data(for: request)
    }

    // MARK: - Matrix

    /// POST /api/matrix/register — create the owner's Matrix account on the homeserver.
    func registerMatrix(username: String, password: String) async throws {
        _ = try await postRaw(path: "matrix/register", body: ["username": username, "password": password])
    }

    /// POST /api/matrix/relationship-room — create a Matrix room for a relationship between two agents.
    func createRelationshipRoom(fromId: String, toId: String) async throws {
        struct Body: Encodable {
            let from_agent_id: String
            let to_agent_id: String
        }
        let url = baseURL.appending(path: "api/matrix/relationship-room")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuth(&request)
        request.httpBody = try JSONEncoder().encode(Body(from_agent_id: fromId, to_agent_id: toId))
        _ = try await URLSession.shared.data(for: request)
    }

    /// POST /api/matrix/owner-dm — create a DM room between owner and an agent.
    func createOwnerDM(agentId: String) async throws {
        struct Body: Encodable {
            let agent_id: String
        }
        let url = baseURL.appending(path: "api/matrix/owner-dm")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuth(&request)
        request.httpBody = try JSONEncoder().encode(Body(agent_id: agentId))
        _ = try await URLSession.shared.data(for: request)
    }

    /// POST /api/matrix/onboard-agent — onboard an agent to Matrix (create user + DM room).
    func onboardAgentToMatrix(agentId: String) async throws {
        struct Body: Encodable {
            let agent_id: String
        }
        let url = baseURL.appending(path: "api/matrix/onboard-agent")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuth(&request)
        request.httpBody = try JSONEncoder().encode(Body(agent_id: agentId))
        _ = try await URLSession.shared.data(for: request)
    }

    /// POST /api/matrix/squad-room — create a shared Matrix room for a squad of agents.
    func createSquadRoom(name: String, agentIds: [String]) async throws {
        struct Body: Encodable {
            let name: String
            let agent_ids: [String]
        }
        let url = baseURL.appending(path: "api/matrix/squad-room")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuth(&request)
        request.httpBody = try JSONEncoder().encode(Body(name: name, agent_ids: agentIds))
        _ = try await URLSession.shared.data(for: request)
    }

    /// POST /api/matrix/reset-rooms — delete all Matrix rooms and recreate from current relationships.
    func resetMatrixRooms() async throws {
        let url = baseURL.appending(path: "api/matrix/reset-rooms")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuth(&request)
        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw GatewayError.badStatus((response as? HTTPURLResponse)?.statusCode ?? 0)
        }
    }

    enum GatewayError: Error, LocalizedError {
        case badStatus(Int)
        case binaryNotFound

        var errorDescription: String? {
            switch self {
            case .badStatus(let code): "Gateway returned status \(code)"
            case .binaryNotFound: "vulti binary not found in PATH"
            }
        }
    }
}
