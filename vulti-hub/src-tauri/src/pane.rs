use crate::vulti_home::vulti_home;

#[tauri::command]
pub fn get_pane_widgets(agent_id: String) -> serde_json::Value {
    let path = vulti_home()
        .join("agents")
        .join(&agent_id)
        .join("pane_widgets.json");
    match std::fs::read_to_string(&path) {
        Ok(content) => serde_json::from_str(&content).unwrap_or(serde_json::json!({"version": 1, "tabs": {}})),
        Err(_) => serde_json::json!({"version": 1, "tabs": {}}),
    }
}

#[tauri::command]
pub fn clear_pane_widgets(agent_id: String, tab: Option<String>) -> Result<(), String> {
    let path = vulti_home()
        .join("agents")
        .join(&agent_id)
        .join("pane_widgets.json");

    if !path.exists() {
        return Ok(());
    }

    if let Some(tab_name) = tab {
        // Remove just one tab
        let content = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
        let mut data: serde_json::Value =
            serde_json::from_str(&content).map_err(|e| e.to_string())?;
        if let Some(tabs) = data.get_mut("tabs").and_then(|t| t.as_object_mut()) {
            tabs.remove(&tab_name);
        }
        let output = serde_json::to_string_pretty(&data).map_err(|e| e.to_string())?;
        std::fs::write(&path, output).map_err(|e| e.to_string())?;
    } else {
        // Remove entire file
        std::fs::remove_file(&path).map_err(|e| e.to_string())?;
    }
    Ok(())
}
