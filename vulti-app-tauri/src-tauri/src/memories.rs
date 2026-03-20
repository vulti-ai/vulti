use crate::types::{MemoriesResponse, OkResponse, SoulResponse};
use crate::vulti_home::{atomic_write_text, ensure_dir, read_text_file, vulti_home};

fn memories_dir(agent_id: Option<&str>) -> std::path::PathBuf {
    match agent_id {
        Some(id) if !id.is_empty() => vulti_home().join("agents").join(id).join("memories"),
        _ => vulti_home().join("memories"),
    }
}

fn soul_path(agent_id: Option<&str>) -> std::path::PathBuf {
    match agent_id {
        Some(id) if !id.is_empty() => vulti_home().join("agents").join(id).join("SOUL.md"),
        _ => vulti_home().join("SOUL.md"),
    }
}

#[tauri::command]
pub fn get_memories(agent_id: Option<String>) -> Result<MemoriesResponse, String> {
    let dir = memories_dir(agent_id.as_deref());
    let memory = read_text_file(&dir.join("MEMORY.md"));
    let user = read_text_file(&dir.join("USER.md"));
    Ok(MemoriesResponse { memory, user })
}

#[tauri::command]
pub fn update_memory(
    agent_id: Option<String>,
    file: String,
    content: String,
) -> Result<OkResponse, String> {
    let dir = memories_dir(agent_id.as_deref());
    ensure_dir(&dir)?;
    let filename = if file == "memory" {
        "MEMORY.md"
    } else {
        "USER.md"
    };
    atomic_write_text(&dir.join(filename), &content)?;
    Ok(OkResponse { ok: true })
}

#[tauri::command]
pub fn get_soul(agent_id: Option<String>) -> Result<SoulResponse, String> {
    let path = soul_path(agent_id.as_deref());
    let content = read_text_file(&path);
    Ok(SoulResponse { content })
}

#[tauri::command]
pub fn update_soul(agent_id: Option<String>, content: String) -> Result<OkResponse, String> {
    let path = soul_path(agent_id.as_deref());
    if let Some(parent) = path.parent() {
        ensure_dir(parent)?;
    }
    atomic_write_text(&path, &content)?;
    Ok(OkResponse { ok: true })
}
