use crate::types::{ConnectionEntry, ConnectionResponse, ConnectionsFile, OkResponse};
use crate::vulti_home::{atomic_write_text, vulti_home};
use std::collections::{HashMap, HashSet};
use std::fs;

fn connections_path() -> std::path::PathBuf {
    vulti_home().join("connections.yaml")
}

fn load_connections() -> ConnectionsFile {
    let path = connections_path();
    if !path.exists() {
        return ConnectionsFile::default();
    }
    match fs::read_to_string(&path) {
        Ok(content) => serde_yaml::from_str(&content).unwrap_or_default(),
        Err(_) => ConnectionsFile::default(),
    }
}

fn save_connections(file: &ConnectionsFile) -> Result<(), String> {
    let content =
        serde_yaml::to_string(file).map_err(|e| format!("YAML serialize error: {e}"))?;
    atomic_write_text(&connections_path(), &content)
}

fn entry_to_response(name: &str, entry: &ConnectionEntry) -> ConnectionResponse {
    // Mask credential values for the frontend
    let masked: HashMap<String, String> = entry
        .credentials
        .iter()
        .map(|(k, v)| {
            let masked = if v.len() <= 5 {
                "****".to_string()
            } else if v.len() <= 12 {
                format!("{}...{}", &v[..3], &v[v.len() - 2..])
            } else {
                format!("{}...{}", &v[..5], &v[v.len() - 4..])
            };
            (k.clone(), masked)
        })
        .collect();

    ConnectionResponse {
        name: name.to_string(),
        conn_type: entry.conn_type.clone(),
        description: entry.description.clone(),
        tags: entry.tags.clone(),
        credentials: masked,
        mcp: entry.mcp.clone(),
        provides_toolsets: entry.provides_toolsets.clone(),
        enabled: entry.enabled,
    }
}

/// Known .env keys → connection metadata.
const ENV_KEY_CONNECTIONS: &[(&str, &str, &str, &[&str], &[&str])] = &[
    ("OPENROUTER_API_KEY", "openrouter", "OpenRouter — 200+ models via one API", &["llm", "provider"], &[]),
    ("ANTHROPIC_API_KEY", "anthropic", "Anthropic — Claude models", &["llm", "provider"], &[]),
    ("OPENAI_API_KEY", "openai", "OpenAI — GPT-4o, o1, o3", &["llm", "provider"], &[]),
    ("DEEPSEEK_API_KEY", "deepseek", "DeepSeek — R1, V3", &["llm", "provider"], &[]),
    ("GOOGLE_API_KEY", "google-ai", "Google AI — Gemini 2.5", &["llm", "provider"], &[]),
    ("FIRECRAWL_API_KEY", "firecrawl", "Firecrawl web search & extraction", &["web", "scraping"], &["web"]),
    ("FAL_KEY", "fal", "fal.ai image generation", &["image", "generation"], &["image"]),
    ("ELEVENLABS_API_KEY", "elevenlabs", "ElevenLabs text-to-speech", &["audio", "tts"], &["tts"]),
    ("BROWSERBASE_API_KEY", "browserbase", "BrowserBase cloud browser", &["browser"], &["browser"]),
    ("GITHUB_TOKEN", "github", "GitHub repository access", &["code", "vcs"], &[]),
    ("WANDB_API_KEY", "wandb", "Weights & Biases ML tracking", &["analytics", "ml"], &[]),
    ("HONCHO_API_KEY", "honcho", "Honcho AI user modeling", &["memory", "context"], &[]),
    ("VOICE_TOOLS_OPENAI_KEY", "openai-voice", "OpenAI TTS/STT", &["audio", "tts", "stt"], &["tts"]),
    ("TELEGRAM_BOT_TOKEN", "telegram", "Telegram bot", &["messaging"], &[]),
    ("DISCORD_TOKEN", "discord", "Discord bot", &["messaging"], &[]),
    ("SLACK_BOT_TOKEN", "slack", "Slack bot", &["messaging"], &[]),
    ("GLM_API_KEY", "glm", "Z.AI / GLM models", &["llm", "provider"], &[]),
    ("KIMI_API_KEY", "kimi", "Moonshot / Kimi models", &["llm", "provider"], &[]),
    ("MINIMAX_API_KEY", "minimax", "MiniMax models", &["llm", "provider"], &[]),
    ("GROQ_API_KEY", "groq", "Groq — fast inference", &["llm", "provider"], &[]),
    ("GOOGLE_API_KEY", "google", "Google — Calendar, Drive, Gmail, etc.", &["google", "productivity"], &[]),
    ("GEMINI_API_KEY", "gemini", "Google Gemini models", &["llm", "provider"], &[]),
    ("WHATSAPP_ENABLED", "whatsapp", "WhatsApp messaging", &["messaging"], &[]),
    ("SIGNAL_ACCOUNT", "signal", "Signal messaging", &["messaging"], &[]),
    ("EMAIL_ADDRESS", "email", "Email (SMTP/IMAP)", &["messaging", "email"], &[]),
    ("MATRIX_HOMESERVER", "matrix", "Matrix chat homeserver", &["messaging"], &[]),
    ("ICLOUD_USERNAME", "icloud", "Apple iCloud", &["apple", "productivity"], &[]),
    ("APPLE_ID", "icloud", "Apple iCloud", &["apple", "productivity"], &[]),
    ("TINKER_API_KEY", "tinker", "Tinker RL training", &["ml", "training"], &[]),
    ("OPENCODE_ZEN_API_KEY", "opencode-zen", "OpenCode Zen — curated models", &["llm", "provider"], &[]),
    ("OPENCODE_GO_API_KEY", "opencode-go", "OpenCode Go — open models", &["llm", "provider"], &[]),
    ("MINIMAX_CN_API_KEY", "minimax-cn", "MiniMax China", &["llm", "provider"], &[]),
    ("DEEPSEEK_API_KEY", "deepseek", "DeepSeek — R1, V3", &["llm", "provider"], &[]),
    ("BROWSERBASE_PROJECT_ID", "browserbase", "BrowserBase cloud browser", &["browser"], &["browser"]),
    ("BLAND_API_KEY", "bland", "Bland.ai telephony / voice calls", &["voice", "telephony"], &[]),
    ("MATRIX_SERVER_NAME", "matrix", "Matrix chat homeserver", &["messaging"], &[]),
    ("MATRIX_ALLOW_ALL_USERS", "matrix", "Matrix chat homeserver", &["messaging"], &[]),
];

fn parse_env_file() -> HashMap<String, String> {
    let path = vulti_home().join(".env");
    let content = match fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return HashMap::new(),
    };
    content
        .lines()
        .filter_map(|line| {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') || !line.contains('=') {
                return None;
            }
            let (key, value) = line.split_once('=')?;
            let value = value.trim().trim_matches('\'').trim_matches('"').to_string();
            if value.is_empty() { return None; }
            Some((key.trim().to_string(), value))
        })
        .collect()
}

fn load_mcp_servers() -> HashMap<String, serde_json::Value> {
    let config_path = vulti_home().join("config.yaml");
    if !config_path.exists() {
        // Try default agent config
        let agent_config = vulti_home().join("agents").join("default").join("config.yaml");
        if !agent_config.exists() {
            return HashMap::new();
        }
        return load_mcp_from_path(&agent_config);
    }
    load_mcp_from_path(&config_path)
}

fn load_mcp_from_path(path: &std::path::Path) -> HashMap<String, serde_json::Value> {
    match fs::read_to_string(path) {
        Ok(content) => {
            match serde_yaml::from_str::<serde_json::Value>(&content) {
                Ok(val) => {
                    val.get("mcp_servers")
                        .and_then(|v| v.as_object())
                        .map(|obj| obj.iter().map(|(k, v)| (k.clone(), v.clone())).collect())
                        .unwrap_or_default()
                }
                Err(_) => HashMap::new(),
            }
        }
        Err(_) => HashMap::new(),
    }
}

fn mask_value(value: &str) -> String {
    let len = value.len();
    if len <= 5 {
        "****".to_string()
    } else if len <= 12 {
        format!("{}...{}", &value[..3], &value[len - 2..])
    } else {
        format!("{}...{}", &value[..5], &value[len - 4..])
    }
}

#[tauri::command]
pub fn list_connections() -> Result<Vec<ConnectionResponse>, String> {
    let file = load_connections();
    let mut result: Vec<ConnectionResponse> = file
        .connections
        .iter()
        .map(|(name, entry)| entry_to_response(name, entry))
        .collect();

    // Track which connection names we already have
    let existing_names: HashSet<String> = result.iter().map(|r| r.name.clone()).collect();

    // Merge in .env secrets as legacy connections
    let env_vars = parse_env_file();
    for (env_key, conn_name, desc, tags, toolsets) in ENV_KEY_CONNECTIONS {
        if existing_names.contains(*conn_name) {
            continue;
        }
        if let Some(value) = env_vars.get(*env_key) {
            // Check if we already have this connection name in result (multi-key merge)
            if let Some(existing) = result.iter_mut().find(|r| r.name == *conn_name) {
                existing.credentials.insert(env_key.to_string(), mask_value(value));
            } else {
                let mut creds = HashMap::new();
                creds.insert(env_key.to_string(), mask_value(value));
                result.push(ConnectionResponse {
                    name: conn_name.to_string(),
                    conn_type: "api_key".to_string(),
                    description: desc.to_string(),
                    tags: tags.iter().map(|s| s.to_string()).collect(),
                    credentials: creds,
                    mcp: HashMap::new(),
                    provides_toolsets: toolsets.iter().map(|s| s.to_string()).collect(),
                    enabled: true,
                });
            }
        }
    }

    // Detect file-based tokens/integrations
    let home = vulti_home();
    let file_connections: &[(&str, &str, &str, &[&str])] = &[
        ("x_oauth2_token.json", "twitter", "X / Twitter (OAuth)", &["messaging", "social"]),
        ("google_token.json", "google", "Google — Calendar, Drive, Gmail, etc.", &["google", "productivity"]),
        ("gmail_archiver_state.json", "gmail", "Gmail email integration", &["email", "google"]),
        ("icloud_session.json", "icloud", "Apple iCloud", &["apple", "productivity"]),
        ("telegram_user_session.session", "telegram-user", "Telegram user session", &["messaging"]),
    ];
    for (filename, conn_name, desc, tags) in file_connections {
        if existing_names.contains(*conn_name) || result.iter().any(|r| r.name == *conn_name) {
            continue;
        }
        if home.join(filename).exists() {
            result.push(ConnectionResponse {
                name: conn_name.to_string(),
                conn_type: "oauth".to_string(),
                description: desc.to_string(),
                tags: tags.iter().map(|s| s.to_string()).collect(),
                credentials: HashMap::from([("token_file".to_string(), filename.to_string())]),
                mcp: HashMap::new(),
                provides_toolsets: vec![],
                enabled: true,
            });
        }
    }

    // Merge in MCP servers from config.yaml
    let mcp_servers = load_mcp_servers();
    for (name, cfg) in &mcp_servers {
        if existing_names.contains(name) {
            continue;
        }
        // Already shown as env-based connection?
        if result.iter().any(|r| r.name == *name) {
            continue;
        }
        let transport = if cfg.get("url").is_some() { "http" } else { "stdio" };
        let command = cfg.get("command").and_then(|v| v.as_str()).unwrap_or("");
        let mcp_map: HashMap<String, serde_json::Value> = cfg
            .as_object()
            .map(|o| o.iter()
                .filter(|(k, _)| *k != "env")  // Don't expose env credentials
                .map(|(k, v)| (k.clone(), v.clone()))
                .collect())
            .unwrap_or_default();

        // Mask any env credentials
        let mut creds = HashMap::new();
        if let Some(env_obj) = cfg.get("env").and_then(|v| v.as_object()) {
            for (k, v) in env_obj {
                if let Some(s) = v.as_str() {
                    if !s.is_empty() {
                        creds.insert(k.clone(), mask_value(s));
                    }
                }
            }
        }

        result.push(ConnectionResponse {
            name: name.clone(),
            conn_type: "mcp".to_string(),
            description: format!("MCP server ({transport}){}", if !command.is_empty() { format!(" — {command}") } else { String::new() }),
            tags: vec!["mcp".to_string()],
            credentials: creds,
            mcp: mcp_map,
            provides_toolsets: vec![],
            enabled: cfg.get("enabled").and_then(|v| v.as_bool()).unwrap_or(true),
        });
    }

    result.sort_by(|a, b| a.name.cmp(&b.name));
    Ok(result)
}

#[tauri::command]
pub fn add_connection(
    name: String,
    conn_type: String,
    description: String,
    tags: Vec<String>,
    credentials: HashMap<String, String>,
    mcp: Option<HashMap<String, serde_json::Value>>,
    provides_toolsets: Option<Vec<String>>,
) -> Result<ConnectionResponse, String> {
    let name = name.trim().to_string();
    if name.is_empty() {
        return Err("Connection name is required".to_string());
    }

    let mut file = load_connections();
    if file.connections.contains_key(&name) {
        return Err(format!("Connection '{}' already exists", name));
    }

    let entry = ConnectionEntry {
        name: name.clone(),
        conn_type,
        description,
        tags,
        credentials,
        mcp: mcp.unwrap_or_default(),
        provides_toolsets: provides_toolsets.unwrap_or_default(),
        tools: HashMap::new(),
        enabled: true,
    };

    file.connections.insert(name.clone(), entry.clone());
    save_connections(&file)?;

    Ok(entry_to_response(&name, &entry))
}

#[tauri::command]
pub fn update_connection(
    name: String,
    updates: serde_json::Value,
) -> Result<ConnectionResponse, String> {
    let mut file = load_connections();
    let entry = file
        .connections
        .get_mut(&name)
        .ok_or_else(|| format!("Connection '{}' not found", name))?;

    if let Some(v) = updates.get("description").and_then(|v| v.as_str()) {
        entry.description = v.to_string();
    }
    if let Some(v) = updates.get("tags").and_then(|v| v.as_array()) {
        entry.tags = v
            .iter()
            .filter_map(|s| s.as_str().map(String::from))
            .collect();
    }
    if let Some(v) = updates.get("enabled").and_then(|v| v.as_bool()) {
        entry.enabled = v;
    }
    if let Some(v) = updates.get("credentials").and_then(|v| v.as_object()) {
        for (k, val) in v {
            if let Some(s) = val.as_str() {
                entry.credentials.insert(k.clone(), s.to_string());
            }
        }
    }

    let entry_clone = entry.clone();
    save_connections(&file)?;

    Ok(entry_to_response(&name, &entry_clone))
}

#[tauri::command]
pub fn delete_connection(name: String) -> Result<OkResponse, String> {
    let mut file = load_connections();
    if file.connections.remove(&name).is_none() {
        return Err(format!("Connection '{}' not found", name));
    }
    save_connections(&file)?;
    Ok(OkResponse { ok: true })
}
