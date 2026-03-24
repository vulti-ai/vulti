import SwiftUI

/// Gateway setup — detects whether vulti is installed, runs install.sh if needed,
/// then starts the gateway. Fully automatic with live log streaming.
struct SetupView: View {
    @Environment(AppState.self) private var app
    @State private var phase: Phase = .checking
    @State private var error: String?
    @State private var logLines: [String] = []
    @State private var logTask: Task<Void, Never>?
    @State private var installProcess: Process?

    enum Phase: Int, CaseIterable {
        case checking = 0
        case installing = 1
        case starting = 2
        case failed = -1
    }

    private static let steps: [(icon: String, label: String)] = [
        ("magnifyingglass", "Check"),
        ("arrow.down.circle", "Install"),
        ("bolt.fill", "Start"),
    ]

    /// The step index for the progress indicator (0-2), or nil if failed.
    private var currentStepIndex: Int? {
        switch phase {
        case .checking: return 0
        case .installing: return 1
        case .starting: return 2
        case .failed: return nil
        }
    }

    var body: some View {
        ZStack {
            VStack(spacing: 20) {
                Spacer()

                Image(systemName: phase == .failed ? "exclamationmark.triangle" : "brain.head.profile")
                    .font(.system(size: 48))
                    .foregroundStyle(phase == .failed ? VultiTheme.coral : VultiTheme.primary)

                Text("Vulti")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .foregroundStyle(VultiTheme.inkSoft)

                // Step progress indicator
                HStack(spacing: 0) {
                    ForEach(Array(Self.steps.enumerated()), id: \.offset) { index, step in
                        let state = stepState(for: index)

                        HStack(spacing: 6) {
                            ZStack {
                                Circle()
                                    .fill(state == .active ? VultiTheme.primary : (state == .done ? VultiTheme.teal : VultiTheme.paperDeep))
                                    .frame(width: 28, height: 28)

                                if state == .done {
                                    Image(systemName: "checkmark")
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundStyle(.white)
                                } else if state == .active {
                                    ProgressView()
                                        .controlSize(.mini)
                                        .tint(.white)
                                } else {
                                    Image(systemName: step.icon)
                                        .font(.system(size: 11))
                                        .foregroundStyle(VultiTheme.inkMuted)
                                }
                            }

                            Text(step.label)
                                .font(.system(size: 12, weight: state == .active ? .semibold : .regular))
                                .foregroundStyle(state == .pending ? VultiTheme.inkMuted : VultiTheme.inkSoft)
                        }

                        if index < Self.steps.count - 1 {
                            Rectangle()
                                .fill(state == .done ? VultiTheme.teal : VultiTheme.paperShadow)
                                .frame(height: 2)
                                .frame(maxWidth: 40)
                                .padding(.horizontal, 8)
                        }
                    }
                }
                .padding(.horizontal, 20)

                // Error message + retry
                if phase == .failed {
                    Text(error ?? "Something went wrong")
                        .foregroundStyle(VultiTheme.rose)
                        .font(.caption)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 400)

                    Button {
                        phase = .checking
                        error = nil
                        logLines = []
                        beginSetup()
                    } label: {
                        Text("Retry")
                            .frame(width: 140)
                    }
                    .buttonStyle(.vultiPrimary)
                    .tint(VultiTheme.primary)
                    .controlSize(.large)
                }

                // API key suggestion — shown during install
                if phase == .installing {
                    VStack(spacing: 10) {
                        Text("This may take a few minutes — why not grab your AI API keys?")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(VultiTheme.inkSoft)
                            .multilineTextAlignment(.center)

                        VStack(alignment: .leading, spacing: 6) {
                            apiKeyRow(name: "Anthropic", detail: "Claude — reasoning & code", url: "https://console.anthropic.com/settings/keys")
                            apiKeyRow(name: "OpenAI", detail: "GPT & image generation", url: "https://platform.openai.com/api-keys")
                            apiKeyRow(name: "ElevenLabs", detail: "Voice & speech synthesis", url: "https://elevenlabs.io/app/settings/api-keys")
                            apiKeyRow(name: "Bland", detail: "AI phone calls", url: "https://app.bland.ai/dashboard/api-keys")
                            apiKeyRow(name: "Fal.ai", detail: "Fast image & video generation", url: "https://fal.ai/dashboard/keys")
                        }
                    }
                    .padding(16)
                    .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
                    .frame(maxWidth: 420)
                }

                Spacer().frame(height: 8)

                // Live log
                ScrollViewReader { proxy in
                    ScrollView {
                        Text(logAttributedString)
                            .font(.system(size: 10, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                            .id("log-bottom")
                    }
                    .frame(maxHeight: 220)
                    .background(Color.black.opacity(0.3), in: RoundedRectangle(cornerRadius: 8))
                    .onChange(of: logLines.count) { _, _ in
                        withAnimation(.easeOut(duration: 0.1)) {
                            proxy.scrollTo("log-bottom", anchor: .bottom)
                        }
                    }
                }

                Spacer()
            }
            .frame(maxWidth: 560)
        }
        .onDisappear {
            logTask?.cancel()
            installProcess?.terminate()
        }
        .task {
            beginSetup()
        }
    }

    // MARK: - Main flow: check → install → start

    private func beginSetup() {
        Task {
            // Step 1: Check if all components are installed
            phase = .checking
            appendLog("Checking installation...")

            let hasBinary = await app.gateway.isInstalled
            let preflightOk = await app.preflightCheck()

            if hasBinary && preflightOk {
                appendLog("All components found")
                app.needsInstall = false
                await startGateway()
                return
            }

            // Step 2: Missing components — run install.sh
            if !hasBinary {
                appendLog("vulti binary not found, starting installation...")
            } else {
                appendLog("Missing components detected, running installer...")
            }
            phase = .installing

            let success = await runInstall()
            guard success else { return } // error already set

            // Step 3: Verify binary exists after install
            appendLog("Verifying installation...")
            let nowInstalled = await app.gateway.isInstalled
            guard nowInstalled else {
                fail("Install completed but vulti binary was not found. Check the log for errors.")
                return
            }
            appendLog("Installation complete")
            app.needsInstall = false

            // Step 4: Start gateway
            await startGateway()
        }
    }

    private func startGateway() async {
        phase = .starting
        appendLog("Starting gateway...")
        startGatewayLogTail()

        do {
            try await app.startGateway()
        } catch {
            fail(error.localizedDescription)
            return
        }

        // Poll for health in case startGateway didn't confirm
        for _ in 0..<60 {
            try? await Task.sleep(for: .seconds(2))
            if await app.client.checkHealth() {
                app.isGatewayRunning = true
                await app.refreshAgents()
                return
            }
        }

        if !app.isGatewayRunning {
            fail("Gateway started but is not responding. Check logs at ~/.vulti/logs/gateway.log")
        }
    }

    // MARK: - Install process with live output

    private func runInstall() async -> Bool {
        do {
            let process = try await app.gateway.install()

            // Set up pipes to stream output into the log view
            let outPipe = Pipe()
            let errPipe = Pipe()
            process.standardOutput = outPipe
            process.standardError = errPipe

            // Stream both stdout and stderr
            let streamTask = Task.detached { [weak outPipe, weak errPipe] in
                guard let outPipe, let errPipe else { return }
                await withTaskGroup(of: Void.self) { group in
                    group.addTask {
                        await self.streamPipe(outPipe)
                    }
                    group.addTask {
                        await self.streamPipe(errPipe)
                    }
                }
            }

            try process.run()
            installProcess = process
            process.waitUntilExit()
            installProcess = nil
            streamTask.cancel()

            if process.terminationStatus != 0 {
                fail("Install script exited with code \(process.terminationStatus)")
                return false
            }
            return true
        } catch {
            fail(error.localizedDescription)
            return false
        }
    }

    private func streamPipe(_ pipe: Pipe) async {
        let handle = pipe.fileHandleForReading
        while true {
            let data = handle.availableData
            if data.isEmpty { break } // EOF
            if let text = String(data: data, encoding: .utf8) {
                let lines = text.components(separatedBy: .newlines).filter { !$0.isEmpty }
                let cleaned = lines.map { stripANSI($0) }
                await MainActor.run {
                    logLines.append(contentsOf: cleaned)
                    if logLines.count > 200 {
                        logLines = Array(logLines.suffix(200))
                    }
                }
            }
        }
    }

    // MARK: - Gateway log tail (for the starting phase)

    private func startGatewayLogTail() {
        logTask?.cancel()
        let logPath = VultiHome.root.appending(path: "logs/gateway.log")

        logTask = Task.detached {
            // Wait for log file to appear
            for _ in 0..<40 {
                if FileManager.default.fileExists(atPath: logPath.path()) { break }
                try? await Task.sleep(for: .milliseconds(250))
            }

            guard let handle = try? FileHandle(forReadingFrom: logPath) else { return }
            defer { try? handle.close() }
            handle.seekToEndOfFile()

            let fd = handle.fileDescriptor
            // Use DispatchSource to get notified when new data is written — no polling
            let source = DispatchSource.makeReadSource(fileDescriptor: fd, queue: .global(qos: .utility))
            let stream = AsyncStream<Void> { continuation in
                source.setEventHandler { continuation.yield() }
                source.setCancelHandler { continuation.finish() }
                source.resume()
            }

            for await _ in stream {
                if Task.isCancelled { break }
                let data = handle.availableData
                guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { continue }
                let lines = text.components(separatedBy: .newlines)
                    .filter { !$0.isEmpty }
                    .map { self.formatGatewayLog($0) }
                await MainActor.run {
                    logLines.append(contentsOf: lines)
                    if logLines.count > 200 {
                        logLines = Array(logLines.suffix(200))
                    }
                }
            }
            source.cancel()
        }
    }

    // MARK: - Helpers

    private func fail(_ message: String) {
        error = message
        phase = .failed
        appendLog("ERROR: \(message)")
    }

    private func appendLog(_ line: String) {
        logLines.append(line)
    }

    /// Strip ANSI color codes from install script output
    private func stripANSI(_ str: String) -> String {
        str.replacingOccurrences(
            of: "\\x1B\\[[0-9;]*[a-zA-Z]|\\[0[;]?[0-9]*m",
            with: "",
            options: .regularExpression
        )
    }

    private nonisolated func formatGatewayLog(_ line: String) -> String {
        if line.count > 24, line.dropFirst(4).prefix(1) == "-" {
            return String(line.dropFirst(24)).trimmingCharacters(in: .whitespaces)
        }
        return line
    }

    private var logAttributedString: AttributedString {
        var result = AttributedString()
        for (i, line) in logLines.enumerated() {
            var attr = AttributedString(line)
            attr.foregroundColor = logLineColor(line)
            result.append(attr)
            if i < logLines.count - 1 {
                result.append(AttributedString("\n"))
            }
        }
        return result
    }

    private func logLineColor(_ line: String) -> Color {
        if line.contains("ERROR") || line.contains("error") || line.contains("✗") { return .red.opacity(0.8) }
        if line.contains("WARNING") || line.contains("warning") { return .orange.opacity(0.8) }
        if line.contains("✓") || line.contains("success") { return .green.opacity(0.8) }
        if line.contains("→") { return .cyan.opacity(0.7) }
        if line.contains("INFO") { return VultiTheme.inkDim }
        return VultiTheme.inkMuted
    }

    // MARK: - API key row

    private func apiKeyRow(name: String, detail: String, url: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "key.fill")
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.primary)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 1) {
                Text(name)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(VultiTheme.inkSoft)
                Text(detail)
                    .font(.system(size: 10))
                    .foregroundStyle(VultiTheme.inkMuted)
            }

            Spacer()

            Link("Get Key", destination: URL(string: url)!)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(VultiTheme.primary)
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 10)
        .background(VultiTheme.paperDeep.opacity(0.4), in: RoundedRectangle(cornerRadius: 6))
    }

    // MARK: - Step state

    enum StepState { case done, active, pending, error }

    private func stepState(for index: Int) -> StepState {
        guard let current = currentStepIndex else {
            // Failed — mark everything up to and including the failed step
            // We don't know which step failed precisely, so mark none as done
            return .pending
        }
        if index < current { return .done }
        if index == current { return .active }
        return .pending
    }
}
