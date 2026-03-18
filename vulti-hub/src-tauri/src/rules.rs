use crate::types::{RuleResponse, RulesFile};
use crate::vulti_home::{atomic_write_json, read_json_file, vulti_home};

fn rules_path() -> std::path::PathBuf {
    vulti_home().join("rules").join("rules.json")
}

fn load_rules_file() -> RulesFile {
    read_json_file(&rules_path())
}

fn save_rules_file(file: &RulesFile) -> Result<(), String> {
    let path = rules_path();
    if let Some(parent) = path.parent() {
        crate::vulti_home::ensure_dir(parent)?;
    }
    atomic_write_json(&path, file)
}

fn rule_to_response(v: &serde_json::Value) -> RuleResponse {
    RuleResponse {
        id: v
            .get("id")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        name: v
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        condition: v
            .get("condition")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        action: v
            .get("action")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        enabled: v.get("enabled").and_then(|v| v.as_bool()).unwrap_or(true),
        priority: v.get("priority").and_then(|v| v.as_i64()).unwrap_or(0),
        trigger_count: v
            .get("trigger_count")
            .and_then(|v| v.as_i64())
            .unwrap_or(0),
        max_triggers: v.get("max_triggers").and_then(|v| v.as_i64()),
        cooldown_minutes: v.get("cooldown_minutes").and_then(|v| v.as_i64()),
        last_triggered_at: v
            .get("last_triggered_at")
            .and_then(|v| v.as_str())
            .map(String::from),
        tags: v
            .get("tags")
            .and_then(|v| v.as_array())
            .map(|a| {
                a.iter()
                    .filter_map(|v| v.as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default(),
    }
}

#[tauri::command]
pub fn list_rules(agent_id: Option<String>) -> Result<Vec<RuleResponse>, String> {
    let file = load_rules_file();
    let rules: Vec<RuleResponse> = file
        .rules
        .iter()
        .filter(|r| {
            if let Some(ref aid) = agent_id {
                r.get("agent")
                    .and_then(|v| v.as_str())
                    .map(|a| a == aid)
                    .unwrap_or(false)
            } else {
                true
            }
        })
        .map(|r| rule_to_response(r))
        .collect();
    Ok(rules)
}

#[tauri::command]
pub fn create_rule(data: serde_json::Value, agent_id: Option<String>) -> Result<serde_json::Value, String> {
    let mut file = load_rules_file();
    let rule_id = uuid::Uuid::new_v4().to_string().replace("-", "")[..12].to_string();
    let now = chrono::Utc::now().to_rfc3339();

    let effective_agent = agent_id
        .or_else(|| {
            data.get("agent")
                .and_then(|v| v.as_str())
                .map(String::from)
        })
        .unwrap_or_else(|| "default".to_string());

    let rule = serde_json::json!({
        "id": rule_id,
        "name": data.get("name").and_then(|v| v.as_str()).unwrap_or_else(||
            data.get("condition").and_then(|v| v.as_str()).unwrap_or("rule")
        ),
        "condition": data.get("condition").and_then(|v| v.as_str()).unwrap_or(""),
        "action": data.get("action").and_then(|v| v.as_str()).unwrap_or(""),
        "enabled": data.get("enabled").and_then(|v| v.as_bool()).unwrap_or(true),
        "priority": data.get("priority").and_then(|v| v.as_i64()).unwrap_or(0),
        "created_at": now,
        "last_triggered_at": null,
        "trigger_count": 0,
        "max_triggers": data.get("max_triggers").and_then(|v| v.as_i64()),
        "cooldown_minutes": data.get("cooldown_minutes").and_then(|v| v.as_i64()),
        "tags": data.get("tags").cloned().unwrap_or(serde_json::json!([])),
        "agent": effective_agent,
    });

    file.rules.push(rule.clone());
    file.updated_at = Some(now.clone());
    save_rules_file(&file)?;

    Ok(serde_json::json!({
        "success": true,
        "rule_id": rule_id,
        "name": rule.get("name"),
        "rule": rule,
    }))
}

#[tauri::command]
pub fn update_rule(rule_id: String, updates: serde_json::Value) -> Result<RuleResponse, String> {
    let mut file = load_rules_file();
    let now = chrono::Utc::now().to_rfc3339();

    for rule in file.rules.iter_mut() {
        if rule.get("id").and_then(|v| v.as_str()) == Some(&rule_id) {
            if let (Some(rule_obj), Some(updates_obj)) = (rule.as_object_mut(), updates.as_object())
            {
                for (k, v) in updates_obj {
                    rule_obj.insert(k.clone(), v.clone());
                }
            }
            let response = rule_to_response(rule);
            file.updated_at = Some(now);
            save_rules_file(&file)?;
            return Ok(response);
        }
    }
    Err(format!("Rule '{}' not found", rule_id))
}

#[tauri::command]
pub fn delete_rule(rule_id: String) -> Result<serde_json::Value, String> {
    let mut file = load_rules_file();
    let original_len = file.rules.len();
    file.rules
        .retain(|r| r.get("id").and_then(|v| v.as_str()) != Some(&rule_id));

    if file.rules.len() < original_len {
        file.updated_at = Some(chrono::Utc::now().to_rfc3339());
        save_rules_file(&file)?;
        Ok(serde_json::json!({"ok": true}))
    } else {
        Err(format!("Rule '{}' not found", rule_id))
    }
}
