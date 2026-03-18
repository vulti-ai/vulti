use crate::vulti_home::vulti_home;
use std::fs;

#[tauri::command]
pub fn get_system_status() -> Result<serde_json::Value, String> {
    let path = vulti_home().join("gateway_state.json");
    if path.exists() {
        match fs::read_to_string(&path) {
            Ok(content) => serde_json::from_str(&content)
                .map_err(|e| format!("Failed to parse gateway_state.json: {}", e)),
            Err(e) => Err(format!("Failed to read gateway_state.json: {}", e)),
        }
    } else {
        Ok(serde_json::json!({"gateway_state": "unknown", "platforms": {}}))
    }
}

#[tauri::command]
pub fn get_channel_directory() -> Result<serde_json::Value, String> {
    let path = vulti_home().join("channel_directory.json");
    if path.exists() {
        match fs::read_to_string(&path) {
            Ok(content) => {
                serde_json::from_str(&content).map_err(|e| format!("Failed to parse: {}", e))
            }
            Err(e) => Err(format!("Failed to read: {}", e)),
        }
    } else {
        Ok(serde_json::json!({"platforms": {}}))
    }
}

#[tauri::command]
pub fn get_integrations() -> Result<Vec<serde_json::Value>, String> {
    let home = vulti_home();
    let mut integrations = Vec::new();

    // Read gateway_state.json for platform statuses
    let gateway_state_path = home.join("gateway_state.json");
    let platforms: serde_json::Value = if gateway_state_path.exists() {
        fs::read_to_string(&gateway_state_path)
            .ok()
            .and_then(|c| serde_json::from_str(&c).ok())
            .and_then(|v: serde_json::Value| v.get("platforms").cloned())
            .unwrap_or(serde_json::json!({}))
    } else {
        serde_json::json!({})
    };

    let platform_meta: &[(&str, &str, &str)] = &[
        ("telegram", "Telegram", "Messaging"),
        ("discord", "Discord", "Messaging"),
        ("whatsapp", "WhatsApp", "Messaging"),
        ("slack", "Slack", "Messaging"),
        ("signal", "Signal", "Messaging"),
        ("email", "Email", "Messaging"),
        ("homeassistant", "Home Assistant", "Smart Home"),
        ("matrix", "Matrix", "Messaging"),
    ];

    if let Some(obj) = platforms.as_object() {
        for (pid, info) in obj {
            if pid == "web" {
                continue;
            }
            let (name, category) = platform_meta
                .iter()
                .find(|(id, _, _)| id == pid)
                .map(|(_, n, c)| (n.to_string(), c.to_string()))
                .unwrap_or_else(|| {
                    let mut name = pid.clone();
                    if let Some(c) = name.get_mut(..1) {
                        c.make_ascii_uppercase();
                    }
                    (name, "Platform".to_string())
                });

            let state = info
                .get("state")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown");
            let updated_at = info
                .get("updated_at")
                .and_then(|v| v.as_str())
                .map(String::from);

            integrations.push(serde_json::json!({
                "id": pid,
                "name": name,
                "category": category,
                "status": state,
                "details": {},
                "updated_at": updated_at,
            }));
        }
    }

    // Add Google Calendar/OAuth as integration if token exists
    let google_token = home.join("google_token.json");
    if google_token.exists() {
        let valid = fs::read_to_string(&google_token)
            .ok()
            .and_then(|c| serde_json::from_str::<serde_json::Value>(&c).ok())
            .and_then(|v| v.get("token").and_then(|t| t.as_str()).map(|s| !s.is_empty()))
            .unwrap_or(false);
        integrations.push(serde_json::json!({
            "id": "google",
            "name": "Google",
            "category": "Productivity",
            "status": if valid { "connected" } else { "error" },
            "details": {},
            "updated_at": null,
        }));
    }

    Ok(integrations)
}
