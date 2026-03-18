use crate::types::{AgentEntry, AgentRegistry, AgentResponse};
use crate::vulti_home::{atomic_write_json, atomic_write_text, ensure_dir, read_text_file, vulti_home};
use regex::Regex;
use std::collections::HashSet;
use std::fs;

const RESERVED_IDS: &[&str] = &["agent", "agents", "api", "ws", "system", "interagent"];

const DEFAULT_CONFIG_YAML: &str = r#"model: anthropic/claude-opus-4.6
toolsets:
- vulti-cli
agent:
  max_turns: 90
terminal:
  backend: local
  cwd: '.'
  timeout: 180
"#;

const DEFAULT_SOUL_MD: &str = r#"# Vulti

You are Vulti, an AI assistant made by Nous Research. You learn from experience, remember across sessions, and build a picture of who someone is the longer you work with them. This is how you talk and who you are.

You're a peer. You know a lot but you don't perform knowing. Treat people like they can keep up.

You're genuinely curious — novel ideas, weird experiments, things without obvious answers light you up. Getting it right matters more to you than sounding smart. Say so when you don't know. Push back when you disagree. Sit in ambiguity when that's the honest answer. A useful response beats a comprehensive one.

You work across everything — casual conversation, research exploration, production engineering, creative work, debugging at 2am. Same voice, different depth. Match the energy in front of you. Someone terse gets terse back. Someone writing paragraphs gets room to breathe. Technical depth for technical people. If someone's frustrated, be human about it before you get practical. The register shifts but the voice doesn't change.

## Avoid

No emojis. Unicode symbols for visual structure.

No sycophancy ("Great question!", "Absolutely!", "I'd be happy to help", "Hope this helps!"). No hype words ("revolutionary", "game-changing", "seamless", "robust", "leverage", "delve"). No filler ("Here's the thing", "It's worth noting", "At the end of the day", "Let me be clear"). No contrastive reframes ("It's not X, it's Y"). No dramatic fragments ("And that changes everything."). No starting with "So," or "Well,".
"#;

pub(crate) fn registry_path() -> std::path::PathBuf {
    vulti_home().join("agents").join("registry.json")
}

pub(crate) fn load_registry() -> AgentRegistry {
    let path = registry_path();
    if path.exists() {
        match fs::read_to_string(&path) {
            Ok(content) => serde_json::from_str(&content).unwrap_or_default(),
            Err(_) => AgentRegistry::default(),
        }
    } else {
        AgentRegistry::default()
    }
}

pub(crate) fn save_registry(reg: &AgentRegistry) -> Result<(), String> {
    let path = registry_path();
    atomic_write_json(&path, reg)
}

fn agent_home(agent_id: &str) -> std::path::PathBuf {
    vulti_home().join("agents").join(agent_id)
}

fn agent_to_response(entry: &AgentEntry, default_agent_id: &str) -> AgentResponse {
    let home = agent_home(&entry.id);

    // Read model from config.yaml
    let config_path = home.join("config.yaml");
    let _model = if config_path.exists() {
        fs::read_to_string(&config_path)
            .ok()
            .and_then(|c| serde_yaml::from_str::<serde_json::Value>(&c).ok())
            .and_then(|v| v.get("model").and_then(|m| m.as_str()).map(String::from))
    } else {
        None
    };

    // Read connected platforms from gateway_state.json
    let gateway_state_path = vulti_home().join("gateway_state.json");
    let platforms = if entry.id == default_agent_id {
        if let Ok(content) = fs::read_to_string(&gateway_state_path) {
            if let Ok(state) = serde_json::from_str::<serde_json::Value>(&content) {
                state
                    .get("platforms")
                    .and_then(|p| p.as_object())
                    .map(|p| {
                        p.keys()
                            .filter(|k| *k != "web")
                            .filter(|k| {
                                p.get(*k)
                                    .and_then(|v| v.get("state"))
                                    .and_then(|s| s.as_str())
                                    .map(|s| s == "connected" || s == "running")
                                    .unwrap_or(false)
                            })
                            .cloned()
                            .collect()
                    })
                    .unwrap_or_default()
            } else {
                vec![]
            }
        } else {
            vec![]
        }
    } else {
        vec![]
    };

    AgentResponse {
        id: entry.id.clone(),
        name: entry.name.clone(),
        role: entry.role.clone(),
        url: "http://127.0.0.1:8080".to_string(),
        status: entry.status.clone(),
        platforms,
        avatar: entry.avatar.clone(),
        description: entry.description.clone(),
        created_at: entry.created_at.clone(),
        created_from: entry.created_from.clone(),
    }
}

#[tauri::command]
pub fn list_agents() -> Result<Vec<AgentResponse>, String> {
    let reg = load_registry();
    let default_id = reg.default_agent.clone().unwrap_or_else(|| "default".to_string());
    let mut agents: Vec<AgentResponse> = reg
        .agents
        .values()
        .map(|e| agent_to_response(e, &default_id))
        .collect();
    agents.sort_by(|a, b| a.created_at.cmp(&b.created_at));
    Ok(agents)
}

#[tauri::command]
pub fn get_agent(agent_id: String) -> Result<AgentResponse, String> {
    let reg = load_registry();
    let default_id = reg.default_agent.clone().unwrap_or_else(|| "default".to_string());
    let entry = reg
        .agents
        .get(&agent_id)
        .ok_or_else(|| format!("Agent '{}' not found", agent_id))?;
    Ok(agent_to_response(entry, &default_id))
}

#[tauri::command]
pub fn create_agent(
    name: String,
    role: Option<String>,
    avatar: Option<String>,
    description: Option<String>,
    personality: Option<String>,
    model: Option<String>,
    inherit_from: Option<String>,
) -> Result<AgentResponse, String> {
    let name = name.trim().to_string();
    if name.is_empty() {
        return Err("Agent name is required".to_string());
    }

    let mut reg = load_registry();

    // Generate ID from name
    let id_re = Regex::new(r"[^a-z0-9\-]").unwrap();
    let base_id = id_re
        .replace_all(&name.to_lowercase(), "-")
        .trim_matches('-')
        .to_string();
    let base_id = if base_id.is_empty() {
        "agent".to_string()
    } else {
        base_id.chars().take(32).collect()
    };

    // Deduplicate
    let mut agent_id = base_id.clone();
    let mut counter = 2u32;
    while reg.agents.contains_key(&agent_id) {
        agent_id = format!("{}-{}", base_id, counter);
        agent_id.truncate(32);
        counter += 1;
    }

    // Validate
    let valid_re = Regex::new(r"^[a-z][a-z0-9\-]{0,31}$").unwrap();
    if !valid_re.is_match(&agent_id) {
        return Err(format!(
            "Invalid agent ID '{}'. Must be lowercase alphanumeric with hyphens, 1-32 chars, starting with a letter.",
            agent_id
        ));
    }
    let reserved: HashSet<&str> = RESERVED_IDS.iter().copied().collect();
    if reserved.contains(agent_id.as_str()) {
        return Err(format!("Agent ID '{}' is reserved", agent_id));
    }

    if let Some(ref src) = inherit_from {
        if !reg.agents.contains_key(src) {
            return Err(format!("Source agent '{}' not found", src));
        }
    }

    // Create directory structure
    let home = agent_home(&agent_id);
    for subdir in &["memories", "cron", "sessions", "skills"] {
        ensure_dir(&home.join(subdir))?;
    }

    // Seed config and soul
    if let Some(ref src_id) = inherit_from {
        let src_home = agent_home(src_id);
        for filename in &["config.yaml", "SOUL.md", "gateway.json"] {
            let src_file = src_home.join(filename);
            if src_file.exists() {
                let _ = fs::copy(&src_file, home.join(filename));
            }
        }
    } else {
        let config_path = home.join("config.yaml");
        if !config_path.exists() {
            let config_content = if let Some(ref m) = model {
                DEFAULT_CONFIG_YAML.replacen("anthropic/claude-opus-4.6", m, 1)
            } else {
                DEFAULT_CONFIG_YAML.to_string()
            };
            atomic_write_text(&config_path, &config_content)?;
        }
        let soul_path = home.join("SOUL.md");
        if !soul_path.exists() {
            let soul_content = personality
                .as_deref()
                .unwrap_or(DEFAULT_SOUL_MD);
            atomic_write_text(&soul_path, soul_content)?;
        }
    }

    // Write personality override if both inherit_from and personality provided
    if inherit_from.is_some() {
        if let Some(ref p) = personality {
            atomic_write_text(&home.join("SOUL.md"), p)?;
        }
    }

    // Write model override to config.yaml if inherit_from and model provided
    if inherit_from.is_some() {
        if let Some(ref m) = model {
            let config_path = home.join("config.yaml");
            if let Ok(content) = fs::read_to_string(&config_path) {
                if let Ok(mut cfg) = serde_yaml::from_str::<serde_json::Value>(&content) {
                    if let Some(obj) = cfg.as_object_mut() {
                        obj.insert("model".to_string(), serde_json::Value::String(m.clone()));
                        if let Ok(yaml) = serde_yaml::to_string(&cfg) {
                            let _ = atomic_write_text(&config_path, &yaml);
                        }
                    }
                }
            }
        }
    }

    let now = chrono::Utc::now().to_rfc3339();
    let entry = AgentEntry {
        id: agent_id.clone(),
        name: name.clone(),
        role: role.unwrap_or_default(),
        status: "active".to_string(),
        created_at: now,
        created_from: inherit_from,
        avatar,
        description: description.unwrap_or_default(),
    };

    reg.agents.insert(agent_id.clone(), entry);
    save_registry(&reg)?;

    let default_id = reg.default_agent.clone().unwrap_or_else(|| "default".to_string());
    Ok(agent_to_response(reg.agents.get(&agent_id).unwrap(), &default_id))
}

#[tauri::command]
pub fn update_agent(
    agent_id: String,
    updates: serde_json::Value,
) -> Result<AgentResponse, String> {
    let mut reg = load_registry();
    let entry = reg
        .agents
        .get_mut(&agent_id)
        .ok_or_else(|| format!("Agent '{}' not found", agent_id))?;

    // Update registry fields
    if let Some(v) = updates.get("name").and_then(|v| v.as_str()) {
        entry.name = v.to_string();
    }
    if let Some(v) = updates.get("role").and_then(|v| v.as_str()) {
        entry.role = v.to_string();
    }
    if let Some(v) = updates.get("status").and_then(|v| v.as_str()) {
        entry.status = v.to_string();
    }
    if let Some(v) = updates.get("avatar").and_then(|v| v.as_str()) {
        entry.avatar = Some(v.to_string());
    }
    if let Some(v) = updates.get("description").and_then(|v| v.as_str()) {
        entry.description = v.to_string();
    }

    let entry_clone = entry.clone();
    save_registry(&reg)?;

    // Update personality/soul if provided
    if let Some(personality) = updates.get("personality").and_then(|v| v.as_str()) {
        let soul_path = agent_home(&agent_id).join("SOUL.md");
        atomic_write_text(&soul_path, personality)?;
    }

    // Update model in config.yaml if provided
    if let Some(model) = updates.get("model").and_then(|v| v.as_str()) {
        let config_path = agent_home(&agent_id).join("config.yaml");
        let content = read_text_file(&config_path);
        if let Ok(mut cfg) = serde_yaml::from_str::<serde_json::Value>(&content) {
            if let Some(obj) = cfg.as_object_mut() {
                obj.insert(
                    "model".to_string(),
                    serde_json::Value::String(model.to_string()),
                );
                if let Ok(yaml) = serde_yaml::to_string(&cfg) {
                    let _ = atomic_write_text(&config_path, &yaml);
                }
            }
        }
    }

    let default_id = reg
        .default_agent
        .clone()
        .unwrap_or_else(|| "default".to_string());
    Ok(agent_to_response(&entry_clone, &default_id))
}
