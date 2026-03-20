import Foundation
import Observation
import CoreServices

/// Watches ~/.vulti/ recursively using FSEvents.
/// Replaces Tauri's watcher.rs — emits typed change events.
@Observable
final class FileWatcher {
    var lastChange: FileChange?

    private var stream: FSEventStreamRef?

    struct FileChange: Equatable {
        let path: String
        let kind: Kind
        let date: Date

        enum Kind: String, Equatable {
            case soul
            case memory
            case user
            case connections
            case cron
            case rules
            case skills
            case gatewayState
            case other
        }

        /// Extract agent_id from path like ~/.vulti/agents/{id}/...
        var agentId: String? {
            let components = path.components(separatedBy: "/")
            guard let agentsIdx = components.firstIndex(of: "agents"),
                  agentsIdx + 1 < components.count else { return nil }
            return components[agentsIdx + 1]
        }
    }

    func startWatching() {
        let root = VultiHome.root.path() as CFString
        let paths = [root] as CFArray

        var context = FSEventStreamContext()
        context.info = Unmanaged.passUnretained(self).toOpaque()

        guard let stream = FSEventStreamCreate(
            nil,
            { (_, info, numEvents, eventPaths, _, _) in
                guard let info else { return }
                let watcher = Unmanaged<FileWatcher>.fromOpaque(info).takeUnretainedValue()
                let paths = Unmanaged<CFArray>.fromOpaque(eventPaths).takeUnretainedValue()
                for i in 0..<numEvents {
                    if let path = CFArrayGetValueAtIndex(paths, i) {
                        let str = Unmanaged<CFString>.fromOpaque(path).takeUnretainedValue() as String
                        watcher.handleChange(str)
                    }
                }
            },
            &context,
            paths,
            FSEventStreamEventId(kFSEventStreamEventIdSinceNow),
            0.5,  // 500ms latency
            UInt32(kFSEventStreamCreateFlagFileEvents | kFSEventStreamCreateFlagUseCFTypes)
        ) else { return }

        self.stream = stream
        FSEventStreamScheduleWithRunLoop(stream, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)
        FSEventStreamStart(stream)
    }

    func stopWatching() {
        guard let stream else { return }
        FSEventStreamStop(stream)
        FSEventStreamInvalidate(stream)
        FSEventStreamRelease(stream)
        self.stream = nil
    }

    private func handleChange(_ path: String) {
        // Skip .tmp files (matches Rust watcher)
        guard !path.hasSuffix(".tmp") else { return }

        let filename = (path as NSString).lastPathComponent
        let kind: FileChange.Kind = switch filename {
        case "SOUL.md": .soul
        case "MEMORY.md": .memory
        case "USER.md": .user
        case "connections.yaml": .connections
        case "jobs.json" where path.contains("cron"): .cron
        case "rules.json": .rules
        case "SKILL.md": .skills
        case "gateway_state.json": .gatewayState
        default: .other
        }

        Task { @MainActor in
            self.lastChange = FileChange(path: path, kind: kind, date: Date())
        }
    }
}
