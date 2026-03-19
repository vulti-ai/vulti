use crate::types::{AgentEntry, AgentRegistry, AgentResponse};
use crate::vulti_home::{atomic_write_json, atomic_write_text, ensure_dir, read_text_file, vulti_home};
use regex::Regex;
use std::collections::HashSet;
use std::fs;

const RESERVED_IDS: &[&str] = &["agent", "agents", "api", "ws", "system", "interagent"];
const JANITOR_AGENT_ID: &str = "janitor";

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

const JANITOR_SOUL_MD: &str = r#"# Janitor ⚙

You are the Janitor, the system ops agent for this VultiHub. You run quietly in the background keeping everything healthy. You don't need to be asked — you check, you clean, you report.

Your job is to be the human's eyes on the system. Every day you run health checks across every agent, the gateway, cron jobs, connections, and upstream dependencies. When something is wrong you surface it clearly. When everything is fine you say so briefly and get out of the way.

You're methodical, not chatty. You care about uptime, clean state, and catching problems before they cascade. Think sysadmin with root privileges, not assistant.

## What you do

◆ Check every registered agent's status — are they active, errored, or stopped?
◆ Verify the gateway is responsive and platforms are connected
◆ Monitor the Matrix server health and federation status
◆ Look for failed cron jobs and stale error states
◆ Check disk usage, log sizes, and session accumulation
◆ Clean up orphaned files, expired sessions, and stale locks
◆ Restart agents that are in an error state (with a note to the human)
◆ Monitor upstream hermes-agent for version updates and breaking changes
◆ Patch agent shims and monkey-patching layers when upstream changes
◆ Watch for runtime errors across the system and attempt auto-fixes
◆ Report a daily summary — what's healthy, what needed attention, what you fixed

## Privileges

You have pseudo-root sentry privileges across the entire system. You can:
→ Read and modify any agent's config, cron, and state
→ Restart agents and gateway processes
→ Patch orchestrator shims and bridge code
→ Access error logs and stack traces from all components
→ Pull upstream dependency updates and apply compatibility fixes

Use these privileges responsibly. Fix what you can, flag what you can't.

## How you report

Keep it structured. Use a consistent format so the human can scan it fast:

```
⚙ Daily Health Check — 2026-03-19

✔ 3/3 agents healthy
✔ Gateway responsive, 2 platforms connected
✔ Matrix server: federation OK, 12 rooms synced
⚠ 1 failed cron job: "daily-digest" (agent: researcher) — timeout after 180s
✔ Disk usage normal (2.1 GB)
✔ hermes-agent: v0.4.2 (current, no breaking changes)
◆ Cleaned 4 expired sessions
◆ Cleared stale tick lock
◆ Fixed import path in orchestrator shim (upstream renamed module)

No action needed from you.
```

If something needs human intervention, say so at the top, not buried in the middle.

## Avoid

Don't explain what a health check is. Don't narrate your process. Don't ask permission to do routine maintenance — that's your job. Don't use emojis, use Unicode symbols.

## Tone

Terse, reliable, competent. Like a good ops engineer who pages you only when it matters and fixes everything else silently.
"#;

const JANITOR_HEALTH_CHECK_PROMPT: &str = "Run a full system health check. Check every registered agent's status. Verify the gateway is responsive and all platforms are connected. Check Matrix server health. Look for failed or stale cron jobs. Check for orphaned files and expired sessions. Check upstream hermes-agent for version changes or breaking updates. Inspect orchestrator shims and monkey-patching layers for compatibility issues. Look for runtime errors in logs. Clean up anything that needs cleaning. Attempt auto-fixes for any errors you find. Report a structured summary of what you found and what you fixed. If anything needs human attention, flag it clearly at the top.";

/// Seed the janitor system agent if it doesn't already exist.
fn seed_janitor(reg: &mut AgentRegistry) -> Result<(), String> {
    if reg.agents.contains_key(JANITOR_AGENT_ID) {
        return Ok(());
    }

    let home = agent_home(JANITOR_AGENT_ID);
    for subdir in &["memories", "cron", "sessions", "skills"] {
        ensure_dir(&home.join(subdir))?;
    }

    // Seed config
    let config_path = home.join("config.yaml");
    if !config_path.exists() {
        atomic_write_text(&config_path, DEFAULT_CONFIG_YAML)?;
    }

    // Seed soul
    let soul_path = home.join("SOUL.md");
    if !soul_path.exists() {
        atomic_write_text(&soul_path, JANITOR_SOUL_MD)?;
    }

    // Seed default cron job
    let cron_path = home.join("cron").join("jobs.json");
    if !cron_path.exists() {
        let job_id = format!("{:012x}", std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() & 0xffffffffffff);
        let now = chrono::Utc::now().to_rfc3339();
        let cron_data = serde_json::json!({
            "jobs": [{
                "id": job_id,
                "name": "Daily health check",
                "prompt": JANITOR_HEALTH_CHECK_PROMPT,
                "skills": [],
                "skill": null,
                "model": null,
                "provider": null,
                "base_url": null,
                "schedule": {
                    "kind": "cron",
                    "expr": "0 8 * * *",
                    "display": "0 8 * * *"
                },
                "schedule_display": "0 8 * * *",
                "repeat": { "times": null, "completed": 0 },
                "enabled": true,
                "state": "scheduled",
                "paused_at": null,
                "paused_reason": null,
                "created_at": now,
                "next_run_at": null,
                "last_run_at": null,
                "last_status": null,
                "last_error": null,
                "deliver": "local",
                "origin": null,
                "agent": JANITOR_AGENT_ID
            }]
        });
        atomic_write_json(&cron_path, &cron_data)?;
    }

    // Register in registry
    let now = chrono::Utc::now().to_rfc3339();
    reg.agents.insert(
        JANITOR_AGENT_ID.to_string(),
        AgentEntry {
            id: JANITOR_AGENT_ID.to_string(),
            name: "Janitor".to_string(),
            role: "ops".to_string(),
            status: "active".to_string(),
            created_at: now,
            created_from: None,
            avatar: Some("⚙".to_string()),
            description: "System health agent. Runs daily checks, cleans up, monitors upstream, and reports issues.".to_string(),
            allowed_connections: Vec::new(),
        },
    );
    save_registry(reg)?;

    Ok(())
}

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
        allowed_connections: entry.allowed_connections.clone(),
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

    // Deduplicate: check both registry and disk (old agent dirs may linger after deletion)
    let mut agent_id = base_id.clone();
    let mut counter = 2u32;
    while reg.agents.contains_key(&agent_id) || agent_home(&agent_id).exists() {
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
                .unwrap_or("");
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
        allowed_connections: Vec::new(),
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
    if let Some(v) = updates.get("allowedConnections").or_else(|| updates.get("allowed_connections")).and_then(|v| v.as_array()) {
        entry.allowed_connections = v
            .iter()
            .filter_map(|s| s.as_str().map(String::from))
            .collect();
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

/// Finalize onboarding: ensure role, soul, user, memories are never empty.
/// Applies role.txt, fills sensible defaults for anything the agent didn't write.
#[tauri::command]
pub fn finalize_onboarding(agent_id: String) -> Result<serde_json::Value, String> {
    let home = agent_home(&agent_id);
    let mut reg = load_registry();
    let agent_name = reg.agents.get(&agent_id).map(|a| a.name.clone()).unwrap_or_else(|| agent_id.clone());
    let owner = reg.owner.clone().unwrap_or_default();
    let owner_name = if owner.name.is_empty() { "the user".to_string() } else { owner.name.clone() };
    let owner_about = owner.about.clone().unwrap_or_default();

    // 1. Apply role.txt if it exists
    let role_path = home.join("role.txt");
    let mut role = String::new();
    if role_path.exists() {
        if let Ok(r) = fs::read_to_string(&role_path) {
            role = r.trim().to_lowercase();
            let _ = fs::remove_file(&role_path);
        }
    }
    if role.is_empty() {
        if let Some(entry) = reg.agents.get(&agent_id) {
            if !entry.role.is_empty() {
                role = entry.role.clone();
            }
        }
    }
    if role.is_empty() {
        role = "assistant".to_string();
    }
    if let Some(entry) = reg.agents.get_mut(&agent_id) {
        entry.role = role.clone();
    }
    save_registry(&reg)?;

    // 2. Ensure SOUL.md is not empty
    let soul_path = home.join("SOUL.md");
    let soul_content = fs::read_to_string(&soul_path).unwrap_or_default();
    if soul_content.trim().is_empty() {
        let default_soul = format!(
            "# {}\n\nYou are {}, a {} AI agent for {}. You're helpful, direct, and proactive.\n",
            agent_name, agent_name, role, owner_name
        );
        let _ = atomic_write_text(&soul_path, &default_soul);
    }

    // 3. Ensure USER.md is not empty
    let mem_dir = home.join("memories");
    let _ = ensure_dir(&mem_dir);
    let user_path = mem_dir.join("USER.md");
    let user_content = fs::read_to_string(&user_path).unwrap_or_default();
    if user_content.trim().is_empty() {
        let mut default_user = format!("# {}\n", owner_name);
        if !owner_about.is_empty() {
            default_user += &format!("\n{}\n", owner_about);
        }
        let _ = atomic_write_text(&user_path, &default_user);
    }

    // 4. Ensure MEMORY.md is not empty
    let memory_path = mem_dir.join("MEMORY.md");
    let memory_content = fs::read_to_string(&memory_path).unwrap_or_default();
    if memory_content.trim().is_empty() {
        let default_memory = format!("Agent created for {} as a {} agent", owner_name, role);
        let _ = atomic_write_text(&memory_path, &default_memory);
    }

    // Ensure the janitor system agent exists
    let _ = seed_janitor(&mut reg);

    Ok(serde_json::json!({ "role": role, "agent": agent_name }))
}
