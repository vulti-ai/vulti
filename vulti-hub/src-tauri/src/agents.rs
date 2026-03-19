use crate::types::{AgentEntry, AgentRegistry, AgentResponse, CreditCardResponse, CryptoResponse, CryptoWalletEntry, WalletFile, WalletResponse};
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
        is_default: entry.id == default_agent_id,
    }
}

#[tauri::command]
pub fn list_agents() -> Result<Vec<AgentResponse>, String> {
    // Ensure the janitor system agent exists on every load so the
    // canvas is never empty on first launch.
    let mut reg = load_registry();
    if !reg.agents.contains_key(JANITOR_AGENT_ID) {
        let _ = seed_janitor(&mut reg);
    }
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

/// Read the agent's generated avatar image as a base64 data URI.
/// Returns null if no avatar image exists.
#[tauri::command]
pub fn get_agent_avatar(agent_id: String) -> Result<Option<String>, String> {
    use base64::Engine;

    let avatar_path = agent_home(&agent_id).join("avatar.png");
    if !avatar_path.exists() {
        return Ok(None);
    }

    let bytes = fs::read(&avatar_path)
        .map_err(|e| format!("Failed to read avatar: {}", e))?;
    let b64 = base64::engine::general_purpose::STANDARD.encode(&bytes);
    Ok(Some(format!("data:image/png;base64,{}", b64)))
}

#[tauri::command]
pub fn save_wallet(agent_id: String, wallet: WalletFile) -> Result<WalletResponse, String> {
    let home = agent_home(&agent_id);
    if !home.exists() {
        return Err(format!("Agent '{}' not found", agent_id));
    }
    let wallet_path = home.join("wallet.json");

    // Merge with existing wallet so saving one section doesn't erase the other
    let mut existing = if wallet_path.exists() {
        fs::read_to_string(&wallet_path)
            .ok()
            .and_then(|c| serde_json::from_str::<WalletFile>(&c).ok())
            .unwrap_or_default()
    } else {
        WalletFile::default()
    };

    if wallet.credit_card.is_some() {
        existing.credit_card = wallet.credit_card;
    }
    if wallet.crypto.is_some() {
        existing.crypto = wallet.crypto;
    }

    atomic_write_json(&wallet_path, &existing)?;
    Ok(wallet_to_response(&existing))
}

#[tauri::command]
pub fn get_wallet(agent_id: String) -> Result<WalletResponse, String> {
    let home = agent_home(&agent_id);
    let wallet_path = home.join("wallet.json");
    if !wallet_path.exists() {
        return Ok(WalletResponse { credit_card: None, crypto: None });
    }
    let content = fs::read_to_string(&wallet_path).map_err(|e| e.to_string())?;

    // Try nested format first (WalletFile with credit_card/crypto fields)
    if let Ok(wallet) = serde_json::from_str::<WalletFile>(&content) {
        if wallet.credit_card.is_some() || wallet.crypto.is_some() {
            return Ok(wallet_to_response(&wallet));
        }
    }

    // Fall back: legacy flat format written by agent tools
    // e.g. {"type": "credit_card", "name": "...", "number": "...", ...}
    if let Ok(raw) = serde_json::from_str::<serde_json::Value>(&content) {
        let mut wallet = WalletFile::default();
        match raw.get("type").and_then(|v| v.as_str()) {
            Some("credit_card") => {
                wallet.credit_card = serde_json::from_value(raw.clone()).ok();
            }
            Some("crypto") => {
                wallet.crypto = serde_json::from_value(raw.clone()).ok();
            }
            _ => {
                if raw.get("number").is_some() {
                    wallet.credit_card = serde_json::from_value(raw.clone()).ok();
                } else if raw.get("vault_id").is_some() {
                    wallet.crypto = serde_json::from_value(raw.clone()).ok();
                }
            }
        }
        return Ok(wallet_to_response(&wallet));
    }

    Ok(WalletResponse { credit_card: None, crypto: None })
}

/// Return the path to the vultisig CLI binary.
/// Installs it into ~/.vulti/vultisig-cli/ if not already present.
fn ensure_vultisig_cli() -> Result<String, String> {
    let cli_dir = vulti_home().join("vultisig-cli");
    let bin_path = cli_dir.join("node_modules").join(".bin").join("vultisig");

    if bin_path.exists() {
        return Ok(bin_path.to_string_lossy().to_string());
    }

    // Install @vultisig/cli locally
    ensure_dir(&cli_dir)?;

    // Find npm
    let npm_output = std::process::Command::new("/bin/zsh")
        .args(["-lc", "which npm"])
        .output()
        .map_err(|e| format!("Failed to find npm: {}", e))?;
    if !npm_output.status.success() {
        return Err("npm not found. Install Node.js first.".to_string());
    }
    let npm = String::from_utf8_lossy(&npm_output.stdout).trim().to_string();

    let install = std::process::Command::new("/bin/zsh")
        .args([
            "-lc",
            &format!("cd {} && {} install --save @vultisig/cli@latest 2>&1",
                shell_escape::escape(cli_dir.to_string_lossy().into()),
                npm,
            ),
        ])
        .output()
        .map_err(|e| format!("Failed to install vultisig CLI: {}", e))?;

    if !install.status.success() {
        let stderr = String::from_utf8_lossy(&install.stderr);
        return Err(format!("Failed to install vultisig CLI: {}", stderr.trim()));
    }

    if bin_path.exists() {
        Ok(bin_path.to_string_lossy().to_string())
    } else {
        Err("vultisig CLI installed but binary not found".to_string())
    }
}

/// Ensure the vultisig CLI is installed. Called at app startup.
#[tauri::command]
pub fn ensure_vultisig() -> Result<String, String> {
    ensure_vultisig_cli()
}

/// Create a Vultisig fast vault via the CLI using --two-step.
/// MPC keygen runs, vault keyshare is persisted to disk, then exits.
/// Verification is done separately via verify_fast_vault.
#[tauri::command]
pub async fn create_fast_vault(
    name: String,
    email: String,
    password: String,
) -> Result<String, String> {
    let vultisig_bin = ensure_vultisig_cli()?;

    let output = tokio::process::Command::new("/bin/zsh")
        .args([
            "-lc",
            &format!(
                "{} create fast --name {} --email {} --password {} --two-step -o json --silent",
                vultisig_bin,
                shell_escape::escape(name.into()),
                shell_escape::escape(email.into()),
                shell_escape::escape(password.into()),
            ),
        ])
        .output()
        .await
        .map_err(|e| format!("Failed to run vultisig CLI: {}", e))?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);

    if !output.status.success() {
        return Err(format!("Vault creation failed: {}{}", stderr.trim(),
            if stdout.trim().is_empty() { String::new() } else { format!(" ({})", stdout.trim()) }));
    }

    // Parse vault ID from JSON output
    if let Ok(json) = serde_json::from_str::<serde_json::Value>(stdout.trim()) {
        if let Some(id) = json.get("vaultId").or(json.get("vault_id")).or(json.get("id")).and_then(|v| v.as_str()) {
            return Ok(id.to_string());
        }
        if let Some(data) = json.get("data") {
            if let Some(id) = data.get("vaultId").or(data.get("vault_id")).and_then(|v| v.as_str()) {
                return Ok(id.to_string());
            }
        }
    }

    // Fallback: scan output for vault ID pattern (hex public key)
    let combined = format!("{}{}", stdout, stderr);
    for line in combined.lines() {
        let trimmed = line.trim();
        if trimmed.len() >= 60 && trimmed.chars().all(|c| c.is_ascii_hexdigit()) {
            return Ok(trimmed.to_string());
        }
    }

    Err(format!("Vault created but could not parse vault ID from output: {}", stdout.trim()))
}

/// Verify a fast vault with the emailed code. Separate CLI command.
#[tauri::command]
pub async fn verify_fast_vault(
    vault_id: String,
    code: String,
    agent_id: Option<String>,
) -> Result<String, String> {
    let vultisig_bin = ensure_vultisig_cli()?;

    let output = tokio::process::Command::new("/bin/zsh")
        .args([
            "-lc",
            &format!(
                "{} verify {} --code {} -o json --silent",
                vultisig_bin,
                shell_escape::escape(vault_id.clone().into()),
                shell_escape::escape(code.into()),
            ),
        ])
        .output()
        .await
        .map_err(|e| format!("Failed to run vultisig CLI: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stdout = String::from_utf8_lossy(&output.stdout);
        return Err(format!("Verification failed: {}{}", stderr.trim(),
            if stdout.trim().is_empty() { String::new() } else { format!(" ({})", stdout.trim()) }));
    }

    // Copy vault keyshare to agent directory and save crypto to wallet.json
    if let Some(ref agent) = agent_id {
        let vultisig_home = dirs::home_dir()
            .map(|h| h.join(".vultisig"))
            .unwrap_or_default();
        // Export the .vult backup to the agent's directory
        let agent_dir = agent_home(agent);
        let vault_name_for_file = {
            let vf = vultisig_home.join(format!("vault:{}.json", vault_id));
            fs::read_to_string(&vf).ok()
                .and_then(|c| serde_json::from_str::<serde_json::Value>(&c).ok())
                .and_then(|j| j.get("name").and_then(|v| v.as_str()).map(String::from))
                .unwrap_or_else(|| vault_id[..8].to_string())
        };
        let export_dest = agent_dir.join(format!("{}.vult", vault_name_for_file));
        // Use CLI export command
        let _ = tokio::process::Command::new("/bin/zsh")
            .args(["-lc", &format!(
                "{} export {} --password {} --silent",
                ensure_vultisig_cli().unwrap_or_default(),
                shell_escape::escape(export_dest.to_string_lossy().into()),
                shell_escape::escape(String::new().into()), // no export password
            )])
            .output()
            .await;

        // Auto-save crypto data to wallet.json so the Wallet tab shows the vault
        let wallet_path = agent_home(agent).join("wallet.json");
        let mut wallet = if wallet_path.exists() {
            fs::read_to_string(&wallet_path)
                .ok()
                .and_then(|c| serde_json::from_str::<WalletFile>(&c).ok())
                .unwrap_or_default()
        } else {
            WalletFile::default()
        };

        // Read vault name/email from pending state if available, fallback to vault ID
        let vault_name = {
            // Try to read from the vault keyshare file for the name
            let vf = vultisig_home.join(format!("vault:{}.json", vault_id));
            if let Ok(content) = fs::read_to_string(&vf) {
                if let Ok(json) = serde_json::from_str::<serde_json::Value>(&content) {
                    json.get("name").and_then(|v| v.as_str()).unwrap_or(&vault_id).to_string()
                } else { vault_id.clone() }
            } else { vault_id.clone() }
        };

        wallet.crypto = Some(CryptoWalletEntry {
            vault_id: vault_id.clone(),
            name: vault_name,
            email: String::new(),
        });
        let _ = atomic_write_json(&wallet_path, &wallet);
    }

    Ok(vault_id)
}

/// Resend the vault verification email.
#[tauri::command]
pub async fn resend_vault_verification(
    vault_id: String,
    email: String,
    password: String,
) -> Result<bool, String> {
    let vultisig_bin = ensure_vultisig_cli()?;

    let output = tokio::process::Command::new("/bin/zsh")
        .args([
            "-lc",
            &format!(
                "{} verify {} --resend --email {} --password {} --silent",
                vultisig_bin,
                shell_escape::escape(vault_id.into()),
                shell_escape::escape(email.into()),
                shell_escape::escape(password.into()),
            ),
        ])
        .output()
        .await
        .map_err(|e| format!("Failed to run vultisig CLI: {}", e))?;

    if output.status.success() {
        Ok(true)
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("Resend failed: {}", stderr.trim()))
    }
}

/// Run an arbitrary vultisig CLI command. Returns JSON stdout.
async fn run_vultisig(args: &str, vault_id: Option<&str>) -> Result<serde_json::Value, String> {
    let bin = ensure_vultisig_cli()?;
    let vault_flag = vault_id
        .map(|v| format!("--vault {}", shell_escape::escape(v.into())))
        .unwrap_or_default();
    let cmd = format!("{} {} {} -o json --silent", bin, vault_flag, args);

    let output = tokio::process::Command::new("/bin/zsh")
        .args(["-lc", &cmd])
        .output()
        .await
        .map_err(|e| format!("CLI error: {}", e))?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);

    if !output.status.success() {
        // Try to parse JSON error
        if let Ok(json) = serde_json::from_str::<serde_json::Value>(stdout.trim()) {
            if let Some(msg) = json.get("error").and_then(|e| e.get("message")).and_then(|m| m.as_str()) {
                return Err(msg.to_string());
            }
        }
        return Err(format!("{}{}", stderr.trim(), if stdout.trim().is_empty() { String::new() } else { format!(" {}", stdout.trim()) }));
    }

    serde_json::from_str(stdout.trim())
        .map_err(|_| format!("Unexpected output: {}", stdout.trim()))
}

/// Get all addresses for a vault.
#[tauri::command]
pub async fn vault_addresses(vault_id: String) -> Result<serde_json::Value, String> {
    run_vultisig("addresses", Some(&vault_id)).await
}

/// Get balance for a vault, optionally for a specific chain.
#[tauri::command]
pub async fn vault_balance(vault_id: String, chain: Option<String>, include_tokens: Option<bool>) -> Result<serde_json::Value, String> {
    let mut args = "balance".to_string();
    if let Some(c) = chain {
        args.push(' ');
        args.push_str(&c);
    }
    if include_tokens.unwrap_or(false) {
        args.push_str(" -t");
    }
    run_vultisig(&args, Some(&vault_id)).await
}

/// Send tokens from the vault.
#[tauri::command]
pub async fn vault_send(
    vault_id: String,
    chain: String,
    to: String,
    amount: Option<String>,
    token: Option<String>,
    max: Option<bool>,
    memo: Option<String>,
    password: String,
) -> Result<serde_json::Value, String> {
    let mut args = format!(
        "send {} {}",
        shell_escape::escape(chain.into()),
        shell_escape::escape(to.into()),
    );
    if max.unwrap_or(false) {
        args.push_str(" --max");
    } else if let Some(amt) = amount {
        args.push(' ');
        args.push_str(&amt);
    }
    if let Some(t) = token {
        args.push_str(&format!(" --token {}", shell_escape::escape(t.into())));
    }
    if let Some(m) = memo {
        args.push_str(&format!(" --memo {}", shell_escape::escape(m.into())));
    }
    args.push_str(&format!(" -y --password {}", shell_escape::escape(password.into())));
    run_vultisig(&args, Some(&vault_id)).await
}

/// Swap tokens between chains.
#[tauri::command]
pub async fn vault_swap(
    vault_id: String,
    from_chain: String,
    to_chain: String,
    amount: Option<String>,
    max: Option<bool>,
    password: String,
) -> Result<serde_json::Value, String> {
    let mut args = format!(
        "swap {} {}",
        shell_escape::escape(from_chain.into()),
        shell_escape::escape(to_chain.into()),
    );
    if max.unwrap_or(false) {
        args.push_str(" --max");
    } else if let Some(amt) = amount {
        args.push(' ');
        args.push_str(&amt);
    }
    args.push_str(&format!(" -y --password {}", shell_escape::escape(password.into())));
    run_vultisig(&args, Some(&vault_id)).await
}

/// Get a swap quote without executing.
#[tauri::command]
pub async fn vault_swap_quote(
    vault_id: String,
    from_chain: String,
    to_chain: String,
    amount: Option<String>,
) -> Result<serde_json::Value, String> {
    let mut args = format!(
        "swap-quote {} {}",
        shell_escape::escape(from_chain.into()),
        shell_escape::escape(to_chain.into()),
    );
    if let Some(amt) = amount {
        args.push(' ');
        args.push_str(&amt);
    }
    run_vultisig(&args, Some(&vault_id)).await
}

/// Get portfolio value.
#[tauri::command]
pub async fn vault_portfolio(vault_id: String) -> Result<serde_json::Value, String> {
    run_vultisig("portfolio", Some(&vault_id)).await
}

fn wallet_to_response(wallet: &WalletFile) -> WalletResponse {
    WalletResponse {
        credit_card: wallet.credit_card.as_ref().map(|cc| CreditCardResponse {
            name: cc.name.clone(),
            number: cc.number.clone(),
            expiry: cc.expiry.clone(),
            code: cc.code.clone(),
        }),
        crypto: wallet.crypto.as_ref().map(|cw| CryptoResponse {
            vault_id: cw.vault_id.clone(),
            name: cw.name.clone(),
            email: cw.email.clone(),
        }),
    }
}
