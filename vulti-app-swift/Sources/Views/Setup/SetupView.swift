import SwiftUI

/// Gateway setup — warm paper background, centered content with live boot log.
struct SetupView: View {
    @Environment(AppState.self) private var app
    @State private var isStarting = false
    @State private var error: String?
    @State private var logLines: [String] = []
    @State private var logTask: Task<Void, Never>?

    var body: some View {
        ZStack {
            VStack(spacing: 24) {
                Spacer()

                Image(systemName: "brain.head.profile")
                    .font(.system(size: 64))
                    .foregroundStyle(VultiTheme.primary)

                Text("Vulti")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .foregroundStyle(VultiTheme.inkSoft)

                Text("Start the gateway to connect your agents")
                    .foregroundStyle(VultiTheme.inkDim)

                if let error {
                    Text(error)
                        .foregroundStyle(VultiTheme.rose)
                        .font(.caption)
                }

                Button {
                    isStarting = true
                    error = nil
                    Task {
                        do {
                            try await app.startGateway()
                        } catch {
                            self.error = error.localizedDescription
                        }
                        try? await Task.sleep(for: .seconds(1))
                        isStarting = false
                        logTask?.cancel()
                    }
                } label: {
                    if isStarting {
                        ProgressView()
                            .controlSize(.small)
                            .frame(width: 140)
                    } else {
                        Text("Start Gateway")
                            .frame(width: 140)
                    }
                }
                .buttonStyle(.vultiPrimary)
                .tint(VultiTheme.primary)
                .controlSize(.large)
                .disabled(isStarting)

                Spacer().frame(height: 8)

                // Live boot log
                ScrollViewReader { proxy in
                    ScrollView {
                        Text(logAttributedString)
                            .font(.system(size: 10, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                            .id("log-bottom")
                    }
                    .frame(maxHeight: 180)
                    .background(Color.black.opacity(0.3), in: RoundedRectangle(cornerRadius: 8))
                    .onChange(of: logLines.count) { _, _ in
                        withAnimation(.easeOut(duration: 0.1)) {
                            proxy.scrollTo("log-bottom", anchor: .bottom)
                        }
                    }
                }

                Spacer()
            }
            .frame(maxWidth: 520)
        }
        .onAppear { startLogTail() }
        .onDisappear { logTask?.cancel() }
    }

    private func startLogTail() {
        logLines = []
        let logPath = VultiHome.root.appending(path: "logs/gateway.log")

        // Load last 20 lines from existing log immediately
        if let existing = try? String(contentsOf: logPath, encoding: .utf8) {
            let tail = existing.components(separatedBy: .newlines)
                .filter { !$0.isEmpty }
                .suffix(20)
                .map { formatLogLine($0) }
            logLines = Array(tail)
        }

        logTask = Task.detached {
            // Wait for log file to appear if it doesn't exist yet
            for _ in 0..<40 {
                if FileManager.default.fileExists(atPath: logPath.path()) { break }
                try? await Task.sleep(for: .milliseconds(250))
            }

            guard let handle = try? FileHandle(forReadingFrom: logPath) else { return }
            defer { try? handle.close() }

            // Seek to end so we only show new lines going forward
            handle.seekToEndOfFile()

            while !Task.isCancelled {
                let data = handle.availableData
                if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
                    let lines = text.components(separatedBy: .newlines).filter { !$0.isEmpty }
                    let formatted = lines.map { formatLogLine($0) }
                    await MainActor.run {
                        logLines.append(contentsOf: formatted)
                        if logLines.count > 50 {
                            logLines = Array(logLines.suffix(50))
                        }
                    }
                }
                try? await Task.sleep(for: .milliseconds(200))
            }
        }
    }

    private func formatLogLine(_ line: String) -> String {
        // Strip timestamp prefix (2026-03-22 13:22:26,013) for compact display
        if line.count > 24, line.dropFirst(4).prefix(1) == "-" {
            let afterTimestamp = line.dropFirst(24)
            return String(afterTimestamp).trimmingCharacters(in: .whitespaces)
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
        if line.contains("ERROR") || line.contains("error") { return .red.opacity(0.8) }
        if line.contains("WARNING") || line.contains("warning") { return .orange.opacity(0.8) }
        if line.contains("INFO") { return VultiTheme.inkDim }
        return VultiTheme.inkMuted
    }
}
