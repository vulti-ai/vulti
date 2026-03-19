use serde::{Deserialize, Serialize};

use crate::vulti_home::vulti_home;

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct PermissionRequest {
    pub id: String,
    pub agent_id: String,
    pub connection_name: String,
    #[serde(default)]
    pub reason: String,
    pub status: String,
    pub created_at: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub resolved_at: Option<String>,
}

fn load_pending() -> Vec<PermissionRequest> {
    let path = vulti_home().join("permissions").join("pending.json");
    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return vec![],
    };
    serde_json::from_str(&content).unwrap_or_default()
}

fn save_pending(requests: &[PermissionRequest]) -> Result<(), String> {
    let path = vulti_home().join("permissions").join("pending.json");
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let content = serde_json::to_string_pretty(requests).map_err(|e| e.to_string())?;
    std::fs::write(&path, content).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn list_permission_requests(agent_id: Option<String>) -> Vec<PermissionRequest> {
    let all = load_pending();
    all.into_iter()
        .filter(|r| r.status == "pending")
        .filter(|r| agent_id.as_ref().map_or(true, |id| &r.agent_id == id))
        .collect()
}

#[tauri::command]
pub fn resolve_permission(request_id: String, approved: bool) -> Result<PermissionRequest, String> {
    let mut requests = load_pending();
    let now = chrono::Utc::now().to_rfc3339();

    let req = requests.iter_mut()
        .find(|r| r.id == request_id && r.status == "pending")
        .ok_or_else(|| format!("Request '{}' not found or already resolved", request_id))?;

    req.status = if approved { "approved".to_string() } else { "denied".to_string() };
    req.resolved_at = Some(now);
    let result = req.clone();

    save_pending(&requests)?;

    // If approved, add to agent's allow list
    if approved {
        add_to_allow_list(&result.agent_id, &result.connection_name)?;
    }

    Ok(result)
}

fn add_to_allow_list(agent_id: &str, connection_name: &str) -> Result<(), String> {
    let registry_path = vulti_home().join("registry.json");
    let content = std::fs::read_to_string(&registry_path)
        .map_err(|e| format!("Failed to read registry: {}", e))?;
    let mut registry: serde_json::Value = serde_json::from_str(&content)
        .map_err(|e| format!("Failed to parse registry: {}", e))?;

    if let Some(agents) = registry.get_mut("agents").and_then(|a| a.as_array_mut()) {
        for agent in agents.iter_mut() {
            if agent.get("id").and_then(|id| id.as_str()) == Some(agent_id) {
                let allowed = agent
                    .as_object_mut()
                    .unwrap()
                    .entry("allowed_connections")
                    .or_insert_with(|| serde_json::json!([]));

                if let Some(arr) = allowed.as_array_mut() {
                    let name_val = serde_json::Value::String(connection_name.to_string());
                    if !arr.contains(&name_val) {
                        arr.push(name_val);
                    }
                }
                break;
            }
        }
    }

    let output = serde_json::to_string_pretty(&registry)
        .map_err(|e| format!("Failed to serialize registry: {}", e))?;
    std::fs::write(&registry_path, output)
        .map_err(|e| format!("Failed to write registry: {}", e))?;

    Ok(())
}
