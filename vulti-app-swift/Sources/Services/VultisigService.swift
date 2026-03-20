import Foundation

/// Spawns vultisig CLI commands and parses JSON output.
/// Replaces Tauri's agents.rs vault commands (create_fast_vault, verify_fast_vault, etc.)
actor VultisigService {

    // MARK: - Vault lifecycle (matches create_fast_vault, verify_fast_vault, resend_vault_verification)

    func createFastVault(name: String, email: String, password: String) async throws -> String {
        let output = try await run([
            "create", "fast",
            "--two-step",
            "--name", name,
            "--email", email,
            "--password", password,
            "-o", "json", "--silent"
        ])

        // Parse vault ID — matches Rust's multi-key lookup + hex fallback
        if let json = try? JSONSerialization.jsonObject(with: output) as? [String: Any] {
            if let id = json["vaultId"] as? String ?? json["vault_id"] as? String ?? json["id"] as? String {
                return id
            }
            if let data = json["data"] as? [String: Any],
               let id = data["vaultId"] as? String ?? data["vault_id"] as? String {
                return id
            }
        }

        // Fallback: scan for 60+ char hex string
        let text = String(data: output, encoding: .utf8) ?? ""
        if let match = text.range(of: #"[a-fA-F0-9]{60,}"#, options: .regularExpression) {
            return String(text[match])
        }

        throw VultisigError.commandFailed("Could not extract vault ID from response")
    }

    func verifyVault(vaultId: String, code: String, agentId: String? = nil) async throws -> String {
        _ = try await run([
            "verify", vaultId,
            "--code", code,
            "-o", "json", "--silent"
        ])

        // If agent_id provided, export keyshare and save to agent dir
        if let agentId {
            // Get vault name from ~/.vultisig/
            let vaultName = vaultNameFromStore(vaultId: vaultId) ?? "vault"
            let exportPath = VultiHome.agentDir(agentId).appending(path: "\(vaultName).vult").path()

            _ = try await run([
                "export",
                "--vault", vaultId,
                "--password", "", // uses stored credentials
                "--silent",
                "-o", exportPath
            ])

            // Auto-save crypto entry to wallet.json
            let wallet = WalletFile(crypto: CryptoWalletEntry(vaultId: vaultId, name: vaultName))
            try VultiHome.atomicWriteJSON(wallet, to: VultiHome.agentWallet(agentId))
        }

        return vaultId
    }

    func resendVerification(vaultId: String, email: String, password: String) async throws {
        _ = try await run([
            "verify", vaultId,
            "--resend",
            "--email", email,
            "--password", password,
            "--silent"
        ])
    }

    // MARK: - Wallet operations (matches vault_addresses, vault_balance, vault_send, etc.)

    func addresses(vaultId: String) async throws -> [String: Any] {
        let data = try await runForVault(vaultId, ["addresses"])
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    func balance(vaultId: String, chain: String? = nil, includeTokens: Bool = false) async throws -> Any {
        var args = ["balance"]
        if let chain { args.append(chain) }
        if includeTokens { args.append("-t") }
        let data = try await runForVault(vaultId, args)
        return try JSONSerialization.jsonObject(with: data)
    }

    func send(
        vaultId: String, chain: String, to: String,
        amount: String? = nil, token: String? = nil,
        max: Bool = false, memo: String? = nil, password: String
    ) async throws -> Any {
        var args = ["send", chain, to]
        if let amount { args.append(amount) }
        if max { args.append("--max") }
        if let token { args += ["--token", token] }
        if let memo { args += ["--memo", memo] }
        args += ["-y", "--password", password]
        let data = try await runForVault(vaultId, args)
        return try JSONSerialization.jsonObject(with: data)
    }

    func swap(
        vaultId: String, fromChain: String, toChain: String,
        amount: String? = nil, max: Bool = false, password: String
    ) async throws -> Any {
        var args = ["swap", fromChain, toChain]
        if let amount { args.append(amount) }
        if max { args.append("--max") }
        args += ["-y", "--password", password]
        let data = try await runForVault(vaultId, args)
        return try JSONSerialization.jsonObject(with: data)
    }

    func swapQuote(vaultId: String, fromChain: String, toChain: String, amount: String? = nil) async throws -> Any {
        var args = ["swap-quote", fromChain, toChain]
        if let amount { args.append(amount) }
        let data = try await runForVault(vaultId, args)
        return try JSONSerialization.jsonObject(with: data)
    }

    func portfolio(vaultId: String) async throws -> Any {
        let data = try await runForVault(vaultId, ["portfolio"])
        return try JSONSerialization.jsonObject(with: data)
    }

    // MARK: - Ensure installed (matches ensure_vultisig)

    func ensureInstalled() async throws -> String {
        let binPath = VultiHome.vultisigBin.path()
        if FileManager.default.fileExists(atPath: binPath) { return binPath }

        let installDir = VultiHome.root.appending(path: "vultisig-cli").path()
        try FileManager.default.createDirectory(atPath: installDir, withIntermediateDirectories: true)

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", "cd \(shellEscape(installDir)) && npm install --save @vultisig/cli@latest"]
        process.standardOutput = FileHandle.nullDevice
        try process.run()
        process.waitUntilExit()

        guard process.terminationStatus == 0 else {
            throw VultisigError.installFailed
        }
        return binPath
    }

    // MARK: - Internal

    private func vaultNameFromStore(vaultId: String) -> String? {
        let vultisigHome = FileManager.default.homeDirectoryForCurrentUser.appending(path: ".vultisig")
        let storePath = vultisigHome.appending(path: "vault:\(vaultId).json")
        guard let data = try? Data(contentsOf: storePath),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        return json["name"] as? String
    }

    private func runForVault(_ vaultId: String, _ args: [String]) async throws -> Data {
        try await run(args + ["--vault", vaultId, "-o", "json", "--silent"])
    }

    private func run(_ args: [String]) async throws -> Data {
        let bin = VultiHome.vultisigBin.path()
        let escaped = args.map { shellEscape($0) }.joined(separator: " ")
        let command = "\(shellEscape(bin)) \(escaped)"

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", command]

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()
        process.waitUntilExit()

        let data = stdout.fileHandleForReading.readDataToEndOfFile()

        guard process.terminationStatus == 0 else {
            // Try JSON error from output
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let error = json["error"] as? [String: Any],
               let message = error["message"] as? String {
                throw VultisigError.commandFailed(message)
            }
            let errData = stderr.fileHandleForReading.readDataToEndOfFile()
            let errStr = String(data: errData, encoding: .utf8) ?? "unknown error"
            throw VultisigError.commandFailed(errStr)
        }

        return data
    }

    private func shellEscape(_ s: String) -> String {
        "'" + s.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }

    enum VultisigError: Error, LocalizedError {
        case installFailed
        case commandFailed(String)

        var errorDescription: String? {
            switch self {
            case .installFailed: "Failed to install vultisig CLI"
            case .commandFailed(let msg): "Vultisig: \(msg)"
            }
        }
    }
}
