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

            let mut details = serde_json::json!({});

            // For Matrix, include owner credentials and homeserver URL if they exist
            if pid == "matrix" {
                let continuwuity_dir = home.join("continuwuity");

                // Compute homeserver URL — prefer Tailscale HTTPS, fall back to localhost
                let port: u16 = std::env::var("MATRIX_CONTINUWUITY_PORT")
                    .ok()
                    .and_then(|p| p.parse().ok())
                    .unwrap_or(6167);
                let server_name = std::env::var("MATRIX_SERVER_NAME").unwrap_or_else(|_| "localhost".to_string());

                // Try Tailscale DNS name for remote access
                let homeserver_url = if server_name != "localhost" {
                    format!("https://{}", server_name)
                } else {
                    // Auto-detect Tailscale
                    std::process::Command::new("tailscale")
                        .args(["status", "--json"])
                        .output()
                        .ok()
                        .and_then(|output| {
                            if !output.status.success() { return None; }
                            let ts: serde_json::Value = serde_json::from_slice(&output.stdout).ok()?;
                            let dns_name = ts.get("Self")?.get("DNSName")?.as_str()?;
                            let dns_name = dns_name.trim_end_matches('.');
                            if dns_name.is_empty() { return None; }
                            Some(format!("https://{}:{}", dns_name, port))
                        })
                        .unwrap_or_else(|| format!("http://localhost:{}", port))
                };
                details["homeserver_url"] = serde_json::json!(homeserver_url);
                details["server_name"] = serde_json::json!(server_name);
                details["port"] = serde_json::json!(port);

                let owner_creds_path = continuwuity_dir.join("owner_credentials.json");
                if owner_creds_path.exists() {
                    if let Ok(creds_str) = fs::read_to_string(&owner_creds_path) {
                        if let Ok(creds) = serde_json::from_str::<serde_json::Value>(&creds_str) {
                            details["owner_username"] = serde_json::json!(
                                creds.get("username").and_then(|v| v.as_str()).unwrap_or("")
                            );
                            details["owner_password"] = serde_json::json!(
                                creds.get("password").and_then(|v| v.as_str()).unwrap_or("")
                            );
                        }
                    }
                }

                // Count registered agent tokens
                let tokens_dir = continuwuity_dir.join("tokens");
                if tokens_dir.exists() {
                    if let Ok(entries) = fs::read_dir(&tokens_dir) {
                        let count = entries
                            .filter_map(|e| e.ok())
                            .filter(|e| e.path().extension().map_or(false, |ext| ext == "json"))
                            .count();
                        details["registered_agents"] = serde_json::json!(count);
                    }
                }
            }

            integrations.push(serde_json::json!({
                "id": pid,
                "name": name,
                "category": category,
                "status": state,
                "details": details,
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
