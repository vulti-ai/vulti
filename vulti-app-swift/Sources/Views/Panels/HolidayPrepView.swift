import SwiftUI

/// Pre-departure checklist — prepares the Mac for unattended operation while the owner is away.
/// Covers: energy settings, FileVault auth restart, SSH, auto-login, software updates, disk space, gateway health.
struct HolidayPrepView: View {
    @Environment(AppState.self) private var app
    @State private var checks: [PrepCheck] = []
    @State private var isRunning = false
    @State private var hasRun = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                HStack(spacing: 12) {
                    Image(systemName: "airplane")
                        .font(.system(size: 28))
                        .foregroundStyle(VultiTheme.primary)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Away Mode Prep")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundStyle(VultiTheme.inkSoft)
                        Text("Make sure your Mac can run unattended while you\u{2019}re away.")
                            .font(.system(size: 12))
                            .foregroundStyle(VultiTheme.inkDim)
                    }
                }

                if !hasRun {
                    Button {
                        runChecks()
                    } label: {
                        if isRunning {
                            ProgressView()
                                .controlSize(.small)
                                .frame(maxWidth: .infinity)
                        } else {
                            Label("Run Checklist", systemImage: "checklist")
                                .font(.system(size: 13, weight: .medium))
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.vultiPrimary)
                    .controlSize(.large)
                    .disabled(isRunning)
                } else {
                    // Summary
                    let passed = checks.filter { $0.status == .ok }.count
                    let warnings = checks.filter { $0.status == .warning }.count
                    let failures = checks.filter { $0.status == .fail }.count

                    HStack(spacing: 16) {
                        summaryBadge(count: passed, label: "Ready", color: VultiTheme.teal)
                        summaryBadge(count: warnings, label: "Warning", color: .orange)
                        summaryBadge(count: failures, label: "Action needed", color: VultiTheme.coral)
                    }
                }

                // Check results
                if !checks.isEmpty {
                    VStack(spacing: 1) {
                        ForEach(checks) { check in
                            PrepCheckRow(check: check)
                        }
                    }
                    .background(VultiTheme.paperDeep.opacity(0.3), in: RoundedRectangle(cornerRadius: 10))
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(VultiTheme.border))

                    // Fix-all button (for items that can be auto-fixed)
                    let fixable = checks.filter { $0.status != .ok && $0.fixAction != nil }
                    if !fixable.isEmpty {
                        Button {
                            applyFixes()
                        } label: {
                            Label("Fix All (\(fixable.count) items)", systemImage: "wrench.and.screwdriver")
                                .font(.system(size: 13, weight: .medium))
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.vultiPrimary)
                        .controlSize(.large)
                    }

                    // Recheck
                    Button {
                        runChecks()
                    } label: {
                        Label("Re-check", systemImage: "arrow.clockwise")
                            .font(.system(size: 12))
                    }
                    .buttonStyle(.vultiSecondary)
                }
            }
            .padding(24)
        }
    }

    // MARK: - Summary badge

    private func summaryBadge(count: Int, label: String, color: Color) -> some View {
        HStack(spacing: 6) {
            Text("\(count)")
                .font(.system(size: 18, weight: .bold, design: .rounded))
                .foregroundStyle(color)
            Text(label)
                .font(.system(size: 11))
                .foregroundStyle(VultiTheme.inkDim)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - Check runner

    private func runChecks() {
        isRunning = true
        checks = []
        Task.detached {
            let results = await performAllChecks()
            await MainActor.run {
                checks = results
                hasRun = true
                isRunning = false
            }
        }
    }

    private func applyFixes() {
        for i in checks.indices {
            if checks[i].status != .ok, let fix = checks[i].fixAction {
                fix()
            }
        }
        // Re-run checks after fixes
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            runChecks()
        }
    }

    // MARK: - All checks

    private func performAllChecks() async -> [PrepCheck] {
        var results: [PrepCheck] = []

        // 1. Energy settings
        let power = app.power
        let energy = power.currentEnergyStatus()

        results.append(PrepCheck(
            id: "sleep",
            title: "System Sleep Disabled",
            detail: energy.sleepDisabled ? "Sleep is off — Mac will stay awake" : "Mac may sleep and agents will stop responding",
            icon: "moon.zzz",
            status: energy.sleepDisabled ? .ok : .fail,
            fixAction: energy.sleepDisabled ? nil : { power.applyOptimalSettings() }
        ))

        results.append(PrepCheck(
            id: "disksleep",
            title: "Disk Sleep Disabled",
            detail: energy.diskSleepDisabled ? "Disks stay active" : "Disks may spin down, causing database delays",
            icon: "internaldrive",
            status: energy.diskSleepDisabled ? .ok : .warning,
            fixAction: energy.diskSleepDisabled ? nil : { power.applyOptimalSettings() }
        ))

        results.append(PrepCheck(
            id: "womp",
            title: "Wake on Network Access",
            detail: energy.wakeOnNetwork ? "Mac will wake when contacted" : "Mac won\u{2019}t respond to network wake signals",
            icon: "wifi",
            status: energy.wakeOnNetwork ? .ok : .fail,
            fixAction: energy.wakeOnNetwork ? nil : { power.applyOptimalSettings() }
        ))

        results.append(PrepCheck(
            id: "autorestart",
            title: "Auto-Restart After Power Failure",
            detail: energy.autoRestart ? "Mac restarts on power restore" : "Mac stays off after a power outage",
            icon: "bolt.circle",
            status: energy.autoRestart ? .ok : .fail,
            fixAction: energy.autoRestart ? nil : { power.applyOptimalSettings() }
        ))

        // 2. FileVault authenticated restart
        let fvStatus = checkFileVault()
        results.append(fvStatus)

        // 3. SSH / Remote Login
        let sshStatus = checkSSH()
        results.append(sshStatus)

        // 4. Screen Sharing / VNC
        let screenSharing = checkScreenSharing()
        results.append(screenSharing)

        // 5. Auto-login
        let autoLogin = checkAutoLogin()
        results.append(autoLogin)

        // 6. Software Update auto-install (we want it OFF during holidays)
        let softwareUpdate = checkSoftwareUpdate()
        results.append(softwareUpdate)

        // 7. Disk space
        let diskSpace = checkDiskSpace()
        results.append(diskSpace)

        // 8. Gateway health
        let gwHealth = await checkGatewayHealth()
        results.append(gwHealth)

        // 9. Tailscale
        let tailscale = checkTailscale()
        results.append(tailscale)

        return results
    }

    // MARK: - Individual checks

    private func checkFileVault() -> PrepCheck {
        let output = shell("fdesetup status")
        let isOn = output.contains("FileVault is On")
        let authRestartSupported = shell("fdesetup supportsauthrestart").contains("true")

        if !isOn {
            return PrepCheck(
                id: "filevault",
                title: "FileVault Auth Restart",
                detail: "FileVault is off — no pre-boot password needed, restarts are fine",
                icon: "lock.shield",
                status: .ok,
                fixAction: nil
            )
        }

        if !authRestartSupported {
            return PrepCheck(
                id: "filevault",
                title: "FileVault Auth Restart",
                detail: "FileVault is on but auth restart is not supported on this Mac. After a reboot you\u{2019}ll need to enter your password at the login screen.",
                icon: "lock.shield",
                status: .warning,
                fixAction: nil
            )
        }

        // Check if an auth restart has been recently queued
        // We can't check this directly, so offer to queue one
        return PrepCheck(
            id: "filevault",
            title: "FileVault Auth Restart",
            detail: "FileVault is on. Run `sudo fdesetup authrestart` before leaving so the Mac can reboot without your password at the pre-boot screen.",
            icon: "lock.shield",
            status: .warning,
            fixAction: {
                // Needs admin prompt
                let script = "do shell script \"fdesetup authrestart\" with administrator privileges"
                if let appleScript = NSAppleScript(source: script) {
                    var error: NSDictionary?
                    appleScript.executeAndReturnError(&error)
                }
            }
        )
    }

    private func checkSSH() -> PrepCheck {
        let output = shell("sudo launchctl print system/com.openssh.sshd 2>/dev/null || systemsetup -getremotelogin 2>/dev/null || echo unknown")

        let remoteLoginOn = output.contains("Remote Login: On") || output.contains("state = running")

        if remoteLoginOn {
            // Check for authorized_keys
            let home = FileManager.default.homeDirectoryForCurrentUser.path()
            let hasKeys = FileManager.default.fileExists(atPath: "\(home)/.ssh/authorized_keys")

            return PrepCheck(
                id: "ssh",
                title: "SSH / Remote Login",
                detail: hasKeys
                    ? "SSH is enabled with authorized keys"
                    : "SSH is enabled but no authorized_keys found — you\u{2019}ll need a password to connect",
                icon: "terminal",
                status: hasKeys ? .ok : .warning,
                fixAction: nil
            )
        }

        return PrepCheck(
            id: "ssh",
            title: "SSH / Remote Login",
            detail: "Remote Login is off. Enable it in System Settings > General > Sharing to access your Mac remotely.",
            icon: "terminal",
            status: .fail,
            fixAction: {
                let script = "do shell script \"systemsetup -setremotelogin on\" with administrator privileges"
                if let appleScript = NSAppleScript(source: script) {
                    var error: NSDictionary?
                    appleScript.executeAndReturnError(&error)
                }
            }
        )
    }

    private func checkScreenSharing() -> PrepCheck {
        let output = shell("launchctl print system/com.apple.screensharing 2>/dev/null || echo disabled")
        let isOn = output.contains("state = running") || output.contains("state = waiting")

        return PrepCheck(
            id: "screensharing",
            title: "Screen Sharing",
            detail: isOn
                ? "Screen Sharing is enabled — you can connect via VNC"
                : "Screen Sharing is off. Enable in System Settings > General > Sharing for remote desktop access.",
            icon: "display",
            status: isOn ? .ok : .warning,
            fixAction: nil // Requires System Settings UI
        )
    }

    private func checkAutoLogin() -> PrepCheck {
        let output = shell("defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser 2>/dev/null")
        let hasAutoLogin = !output.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !output.contains("does not exist")

        return PrepCheck(
            id: "autologin",
            title: "Auto-Login",
            detail: hasAutoLogin
                ? "Auto-login is configured — Mac will boot to desktop"
                : "Auto-login is off. After a restart, the Mac will wait at the login screen until you enter your password.",
            icon: "person.crop.circle.badge.checkmark",
            status: hasAutoLogin ? .ok : .warning,
            fixAction: nil // Requires System Settings UI and is security-sensitive
        )
    }

    private func checkSoftwareUpdate() -> PrepCheck {
        let output = shell("defaults read /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates 2>/dev/null")
        let autoInstall = output.trimmingCharacters(in: .whitespacesAndNewlines) == "1"

        return PrepCheck(
            id: "softwareupdate",
            title: "Auto-Install Updates",
            detail: autoInstall
                ? "macOS may auto-install updates and restart unexpectedly while you\u{2019}re away"
                : "Auto-install is off — no surprise reboots",
            icon: "arrow.down.circle",
            status: autoInstall ? .warning : .ok,
            fixAction: autoInstall ? {
                let script = "do shell script \"defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool false\" with administrator privileges"
                if let appleScript = NSAppleScript(source: script) {
                    var error: NSDictionary?
                    appleScript.executeAndReturnError(&error)
                }
            } : nil
        )
    }

    private func checkDiskSpace() -> PrepCheck {
        let home = FileManager.default.homeDirectoryForCurrentUser
        guard let values = try? home.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]),
              let available = values.volumeAvailableCapacityForImportantUsage else {
            return PrepCheck(
                id: "disk",
                title: "Disk Space",
                detail: "Could not determine available disk space",
                icon: "externaldrive",
                status: .warning,
                fixAction: nil
            )
        }

        let gbAvailable = Double(available) / 1_073_741_824
        let formatted = String(format: "%.1f GB", gbAvailable)

        return PrepCheck(
            id: "disk",
            title: "Disk Space",
            detail: "\(formatted) available",
            icon: "externaldrive",
            status: gbAvailable > 20 ? .ok : (gbAvailable > 5 ? .warning : .fail),
            fixAction: nil
        )
    }

    private func checkGatewayHealth() async -> PrepCheck {
        let healthy = await app.client.checkHealth()
        return PrepCheck(
            id: "gateway",
            title: "Gateway Running",
            detail: healthy ? "Gateway is healthy and responding" : "Gateway is not running — agents are offline",
            icon: "server.rack",
            status: healthy ? .ok : .fail,
            fixAction: healthy ? nil : {
                Task { try? await app.startGateway() }
            }
        )
    }

    private func checkTailscale() -> PrepCheck {
        let output = shell("tailscale status --self --json 2>/dev/null")
        if output.isEmpty || output.contains("command not found") {
            return PrepCheck(
                id: "tailscale",
                title: "Tailscale VPN",
                detail: "Tailscale is not installed — you won\u{2019}t be able to reach your Mac remotely",
                icon: "network",
                status: .fail,
                fixAction: nil
            )
        }

        let isOnline = output.contains("\"Online\":true") || output.contains("\"Online\": true")
        return PrepCheck(
            id: "tailscale",
            title: "Tailscale VPN",
            detail: isOnline
                ? "Tailscale is connected — your Mac is reachable from your devices"
                : "Tailscale is installed but not connected",
            icon: "network",
            status: isOnline ? .ok : .fail,
            fixAction: nil
        )
    }

    // MARK: - Helpers

    private func shell(_ command: String) -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", command]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        try? process.run()
        process.waitUntilExit()
        return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    }
}

// MARK: - Models

struct PrepCheck: Identifiable {
    let id: String
    let title: String
    let detail: String
    let icon: String
    let status: Status
    var fixAction: (() -> Void)?

    enum Status {
        case ok, warning, fail
    }
}

// MARK: - Row

struct PrepCheckRow: View {
    let check: PrepCheck

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: check.icon)
                .font(.system(size: 14))
                .foregroundStyle(statusColor)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(check.title)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(VultiTheme.inkSoft)
                Text(check.detail)
                    .font(.system(size: 11))
                    .foregroundStyle(VultiTheme.inkMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer()

            statusIcon
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    private var statusColor: Color {
        switch check.status {
        case .ok: return VultiTheme.teal
        case .warning: return .orange
        case .fail: return VultiTheme.coral
        }
    }

    @ViewBuilder
    private var statusIcon: some View {
        switch check.status {
        case .ok:
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(VultiTheme.teal)
                .font(.system(size: 16))
        case .warning:
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
                .font(.system(size: 16))
        case .fail:
            Image(systemName: "xmark.circle.fill")
                .foregroundStyle(VultiTheme.coral)
                .font(.system(size: 16))
        }
    }
}
