import Foundation

/// Reads audit events from ~/.vulti/audit/events.jsonl.
/// Port of src-tauri/src/audit.rs list_audit_events.
struct AuditStore {

    static var eventsPath: URL {
        VultiHome.root.appending(path: "audit/events.jsonl")
    }

    /// List audit events with optional filters. Returns last `limit` events in reverse chronological order.
    static func listEvents(
        limit: Int = 200,
        agentId: String? = nil,
        traceId: String? = nil,
        eventType: String? = nil
    ) -> [AuditEvent] {
        guard let data = VultiHome.readData(from: eventsPath) else { return [] }
        guard let content = String(data: data, encoding: .utf8) else { return [] }

        let decoder = JSONDecoder()
        var events: [AuditEvent] = []

        for line in content.components(separatedBy: .newlines) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty,
                  let lineData = trimmed.data(using: .utf8) else { continue }

            guard let ev = try? decoder.decode(AuditEvent.self, from: lineData) else { continue }

            // Apply filters (matches Rust implementation)
            if let filterAgent = agentId, ev.agentId != filterAgent { continue }
            if let filterTrace = traceId, ev.traceId != filterTrace { continue }
            if let filterType = eventType, ev.eventType != filterType { continue }

            events.append(ev)
        }

        // Return last N events, reversed for reverse-chronological order
        let start = max(0, events.count - limit)
        return Array(events[start...].reversed())
    }
}
