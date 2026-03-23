import Foundation
import IOKit.pwr_mgt

/// Manages macOS energy settings for optimal gateway operation.
/// - Runtime: IOPMAssertion prevents sleep while gateway is running (no privileges needed).
/// - Persistent: Configures pmset on first install (one-time admin prompt).
final class PowerManager {
    private var assertionID: IOPMAssertionID = 0
    private var isAssertionActive = false

    // MARK: - Runtime sleep prevention (IOKit — no sudo)

    /// Prevent system sleep while the gateway is running.
    func preventSleep() {
        guard !isAssertionActive else { return }
        let result = IOPMAssertionCreateWithName(
            kIOPMAssertionTypePreventSystemSleep as CFString,
            IOPMAssertionLevel(kIOPMAssertionLevelOn),
            "VultiHub gateway is running" as CFString,
            &assertionID
        )
        isAssertionActive = (result == kIOReturnSuccess)
    }

    /// Release the sleep assertion (e.g. when gateway stops).
    func allowSleep() {
        guard isAssertionActive else { return }
        IOPMAssertionRelease(assertionID)
        isAssertionActive = false
        assertionID = 0
    }

    // MARK: - Persistent energy settings (pmset — one-time admin prompt)

    /// Check whether we've already configured energy settings.
    static var hasConfiguredEnergy: Bool {
        get { UserDefaults.standard.bool(forKey: "vulti.energyConfigured") }
        set { UserDefaults.standard.set(newValue, forKey: "vulti.energyConfigured") }
    }

    /// Current pmset values for the settings we care about.
    struct EnergyStatus {
        var sleepDisabled: Bool       // sleep = 0
        var diskSleepDisabled: Bool   // disksleep = 0
        var wakeOnNetwork: Bool       // womp = 1
        var autoRestart: Bool         // autorestart = 1

        var allOptimal: Bool {
            sleepDisabled && diskSleepDisabled && wakeOnNetwork && autoRestart
        }
    }

    /// Read current pmset settings (no privileges needed).
    func currentEnergyStatus() -> EnergyStatus {
        let output = shell("pmset -g custom")
        return EnergyStatus(
            sleepDisabled: pmsetValue("sleep", in: output) == 0,
            diskSleepDisabled: pmsetValue("disksleep", in: output) == 0,
            wakeOnNetwork: pmsetValue("womp", in: output) == 1,
            autoRestart: pmsetValue("autorestart", in: output) == 1
        )
    }

    /// Apply optimal energy settings via admin prompt. Returns true on success.
    @discardableResult
    func applyOptimalSettings() -> Bool {
        let commands = [
            "pmset -a sleep 0",
            "pmset -a disksleep 0",
            "pmset -a womp 1",
            "pmset -a autorestart 1",
        ]
        let joined = commands.joined(separator: " && ")
        let script = "do shell script \"\(joined)\" with administrator privileges"

        guard let appleScript = NSAppleScript(source: script) else { return false }
        var error: NSDictionary?
        appleScript.executeAndReturnError(&error)

        if error == nil {
            Self.hasConfiguredEnergy = true
            return true
        }
        return false
    }

    // MARK: - Helpers

    private func shell(_ command: String) -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-c", command]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        try? process.run()
        process.waitUntilExit()
        return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    }

    private func pmsetValue(_ key: String, in output: String) -> Int? {
        // pmset output format: " sleep		0"
        for line in output.components(separatedBy: .newlines) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix(key) {
                let parts = trimmed.components(separatedBy: .whitespaces).filter { !$0.isEmpty }
                if parts.count >= 2, let val = Int(parts.last ?? "") {
                    return val
                }
            }
        }
        return nil
    }
}
