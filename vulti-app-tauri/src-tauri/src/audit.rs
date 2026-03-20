use serde::{Deserialize, Serialize};
use std::io::BufRead;

use crate::vulti_home::vulti_home;

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct AuditEvent {
    pub ts: String,
    pub event: String,
    pub agent_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trace_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<serde_json::Value>,
}

#[tauri::command]
pub fn list_audit_events(
    n: Option<usize>,
    agent_id: Option<String>,
    trace_id: Option<String>,
    event_type: Option<String>,
) -> Vec<AuditEvent> {
    let limit = n.unwrap_or(50);
    let path = vulti_home().join("audit").join("events.jsonl");

    let file = match std::fs::File::open(&path) {
        Ok(f) => f,
        Err(_) => return vec![],
    };

    let reader = std::io::BufReader::new(file);
    let mut events: Vec<AuditEvent> = Vec::new();

    for line in reader.lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => continue,
        };
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let ev: AuditEvent = match serde_json::from_str(trimmed) {
            Ok(e) => e,
            Err(_) => continue,
        };

        if let Some(ref filter_agent) = agent_id {
            if &ev.agent_id != filter_agent {
                continue;
            }
        }
        if let Some(ref filter_trace) = trace_id {
            if ev.trace_id.as_deref() != Some(filter_trace.as_str()) {
                continue;
            }
        }
        if let Some(ref filter_type) = event_type {
            if &ev.event != filter_type {
                continue;
            }
        }

        events.push(ev);
    }

    // Return last N events
    let start = events.len().saturating_sub(limit);
    events[start..].to_vec()
}
