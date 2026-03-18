use crate::types::SessionMeta;
use crate::vulti_home::{atomic_write_json, ensure_dir, vulti_home};
use std::fs;

fn sessions_dir() -> std::path::PathBuf {
    vulti_home().join("web").join("sessions")
}

fn history_dir() -> std::path::PathBuf {
    vulti_home().join("web").join("history")
}

#[tauri::command]
pub fn list_sessions(agent_id: Option<String>) -> Result<Vec<SessionMeta>, String> {
    let dir = sessions_dir();
    if !dir.exists() {
        return Ok(vec![]);
    }

    let mut sessions: Vec<(SessionMeta, std::time::SystemTime)> = Vec::new();

    if let Ok(entries) = fs::read_dir(&dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().map(|e| e == "json").unwrap_or(false) {
                if let Ok(content) = fs::read_to_string(&path) {
                    if let Ok(meta) = serde_json::from_str::<SessionMeta>(&content) {
                        let mtime = entry
                            .metadata()
                            .and_then(|m| m.modified())
                            .unwrap_or(std::time::SystemTime::UNIX_EPOCH);

                        // Filter by agent_id if provided
                        if let Some(ref aid) = agent_id {
                            if meta
                                .agent_id
                                .as_ref()
                                .map(|a| a != aid)
                                .unwrap_or(false)
                            {
                                continue;
                            }
                        }

                        sessions.push((meta, mtime));
                    }
                }
            }
        }
    }

    // Sort by modification time, newest first
    sessions.sort_by(|a, b| b.1.cmp(&a.1));
    Ok(sessions.into_iter().map(|(s, _)| s).collect())
}

#[tauri::command]
pub fn create_session(
    agent_id: Option<String>,
    name: Option<String>,
) -> Result<SessionMeta, String> {
    let session_id = uuid::Uuid::new_v4().to_string().replace("-", "")[..12].to_string();
    let now = chrono::Local::now().format("%b %d %H:%M").to_string();
    let session_name = name.unwrap_or_else(|| format!("Chat {}", now));
    let iso_now = chrono::Utc::now().to_rfc3339();

    let meta = SessionMeta {
        id: session_id.clone(),
        name: session_name,
        agent_id,
        created_at: iso_now.clone(),
        updated_at: iso_now,
        preview: String::new(),
    };

    let dir = sessions_dir();
    ensure_dir(&dir)?;
    atomic_write_json(&dir.join(format!("{}.json", session_id)), &meta)?;

    Ok(meta)
}

#[tauri::command]
pub fn delete_session(session_id: String) -> Result<serde_json::Value, String> {
    let session_file = sessions_dir().join(format!("{}.json", session_id));
    if session_file.exists() {
        fs::remove_file(&session_file).map_err(|e| format!("Failed to delete session: {}", e))?;
    }

    let history_file = history_dir().join(format!("{}.jsonl", session_id));
    if history_file.exists() {
        fs::remove_file(&history_file)
            .map_err(|e| format!("Failed to delete history: {}", e))?;
    }

    Ok(serde_json::json!({"ok": true}))
}

#[tauri::command]
pub fn get_history(session_id: String) -> Result<Vec<serde_json::Value>, String> {
    let path = history_dir().join(format!("{}.jsonl", session_id));
    if !path.exists() {
        return Ok(vec![]);
    }

    let content = fs::read_to_string(&path).map_err(|e| format!("Failed to read history: {}", e))?;
    let messages: Vec<serde_json::Value> = content
        .lines()
        .filter(|line| !line.trim().is_empty())
        .filter_map(|line| serde_json::from_str(line).ok())
        .collect();

    Ok(messages)
}
