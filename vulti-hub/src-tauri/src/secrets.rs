use crate::types::{OAuthStatus, OkResponse, ProviderResponse, SecretResponse};
use crate::vulti_home::{atomic_write_text, vulti_home};
use std::fs;

fn env_path() -> std::path::PathBuf {
    vulti_home().join(".env")
}

fn mask_value(value: &str) -> String {
    let len = value.len();
    if len <= 5 {
        "***".to_string()
    } else if len <= 12 {
        format!("{}...{}", &value[..3], &value[len - 2..])
    } else {
        format!("{}...{}", &value[..5], &value[len - 4..])
    }
}

fn categorize_key(key: &str) -> &'static str {
    let key_upper = key.to_uppercase();
    let categories: &[(&str, &[&str])] = &[
        (
            "LLM Providers",
            &[
                "OPENROUTER",
                "OPENAI",
                "GLM",
                "KIMI",
                "MINIMAX",
                "OPENCODE",
                "GROQ",
                "ANTHROPIC",
                "DEEPSEEK",
            ],
        ),
        (
            "Messaging",
            &[
                "TELEGRAM",
                "DISCORD",
                "WHATSAPP",
                "SLACK",
                "SIGNAL",
                "EMAIL",
                "MATRIX",
            ],
        ),
        (
            "Tools",
            &[
                "FIRECRAWL",
                "FAL",
                "BROWSERBASE",
                "HONCHO",
                "TINKER",
                "GITHUB",
            ],
        ),
        (
            "Voice & Audio",
            &["VOICE_TOOLS", "WHISPER", "ELEVENLABS", "TTS"],
        ),
        ("Analytics & ML", &["WANDB"]),
        ("Google", &["GOOGLE", "GEMINI"]),
    ];

    for (cat, prefixes) in categories {
        if prefixes.iter().any(|p| key_upper.starts_with(p)) {
            return cat;
        }
    }
    "Other"
}

fn parse_env_file() -> Vec<(String, String)> {
    let path = env_path();
    let content = match fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return vec![],
    };

    content
        .lines()
        .filter_map(|line| {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') || !line.contains('=') {
                return None;
            }
            let (key, value) = line.split_once('=')?;
            let key = key.trim().to_string();
            let value = value
                .trim()
                .trim_matches('\'')
                .trim_matches('"')
                .to_string();
            Some((key, value))
        })
        .collect()
}

#[tauri::command]
pub fn list_secrets() -> Result<Vec<SecretResponse>, String> {
    let entries = parse_env_file();
    let secrets: Vec<SecretResponse> = entries
        .iter()
        .map(|(key, value)| SecretResponse {
            key: key.clone(),
            masked_value: if value.is_empty() {
                String::new()
            } else {
                mask_value(value)
            },
            is_set: !value.is_empty(),
            category: categorize_key(key).to_string(),
        })
        .collect();
    Ok(secrets)
}

#[tauri::command]
pub fn add_secret(key: String, value: String) -> Result<OkResponse, String> {
    let key = key.trim().to_string();
    let value = value.trim().to_string();
    if key.is_empty() || value.is_empty() {
        return Err("Both key and value are required".to_string());
    }

    // Validate key format
    let re = regex::Regex::new(r"^[A-Z][A-Z0-9_]*$").unwrap();
    if !re.is_match(&key) {
        return Err("Key must be uppercase alphanumeric with underscores".to_string());
    }

    let path = env_path();
    let content = fs::read_to_string(&path).unwrap_or_default();

    let mut lines: Vec<String> = content.lines().map(String::from).collect();
    let mut found = false;
    for line in lines.iter_mut() {
        if line.starts_with(&format!("{}=", key)) || line.starts_with(&format!("{} =", key)) {
            *line = format!("{}={}", key, value);
            found = true;
            break;
        }
    }
    if !found {
        lines.push(format!("{}={}", key, value));
    }

    let new_content = lines.join("\n") + "\n";
    atomic_write_text(&path, &new_content)?;
    Ok(OkResponse { ok: true })
}

#[tauri::command]
pub fn delete_secret(key: String) -> Result<OkResponse, String> {
    let key = key.trim().to_string();
    if key.is_empty() {
        return Err("Key is required".to_string());
    }

    let path = env_path();
    let content = match fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return Ok(OkResponse { ok: true }),
    };

    let lines: Vec<&str> = content
        .lines()
        .filter(|line| {
            let trimmed = line.trim();
            !(trimmed.starts_with(&format!("{}=", key))
                || trimmed.starts_with(&format!("{} =", key)))
        })
        .collect();

    let new_content = lines.join("\n") + "\n";
    atomic_write_text(&path, &new_content)?;
    Ok(OkResponse { ok: true })
}

#[tauri::command]
pub fn list_providers() -> Result<Vec<ProviderResponse>, String> {
    let entries = parse_env_file();
    let configured_keys: std::collections::HashSet<String> =
        entries.into_iter().filter(|(_, v)| !v.is_empty()).map(|(k, _)| k).collect();

    let provider_defs: Vec<(&str, &str, &[&str], &[&str])> = vec![
        (
            "anthropic",
            "Anthropic",
            &["ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN"],
            &[
                "anthropic/claude-opus-4.6",
                "anthropic/claude-sonnet-4.6",
                "anthropic/claude-haiku-4.5",
            ],
        ),
        (
            "openrouter",
            "OpenRouter",
            &["OPENROUTER_API_KEY"],
            &[
                "openrouter/anthropic/claude-opus-4",
                "openrouter/anthropic/claude-sonnet-4",
                "openrouter/google/gemini-2.5-pro",
                "openrouter/openai/gpt-4o",
                "openrouter/meta-llama/llama-4-maverick",
                "openrouter/deepseek/deepseek-chat-v3",
            ],
        ),
        (
            "openai",
            "OpenAI",
            &["OPENAI_API_KEY"],
            &["openai/gpt-4o", "openai/gpt-4.1", "openai/o3"],
        ),
        (
            "deepseek",
            "DeepSeek",
            &["DEEPSEEK_API_KEY"],
            &["deepseek/deepseek-chat", "deepseek/deepseek-reasoner"],
        ),
        (
            "google",
            "Google AI",
            &["GOOGLE_API_KEY", "GEMINI_API_KEY"],
            &["google/gemini-2.5-pro", "google/gemini-2.5-flash"],
        ),
    ];

    let result: Vec<ProviderResponse> = provider_defs
        .into_iter()
        .map(|(id, name, env_keys, models)| {
            let authenticated = env_keys.iter().any(|k| configured_keys.contains(*k));
            ProviderResponse {
                id: id.to_string(),
                name: name.to_string(),
                authenticated,
                models: models.iter().map(|s| s.to_string()).collect(),
                env_keys: env_keys.iter().map(|s| s.to_string()).collect(),
            }
        })
        .collect();

    Ok(result)
}

#[tauri::command]
pub fn get_oauth_status() -> Result<Vec<OAuthStatus>, String> {
    let home = vulti_home();
    let mut tokens = Vec::new();

    // Google OAuth
    let google_token = home.join("google_token.json");
    if google_token.exists() {
        match fs::read_to_string(&google_token)
            .ok()
            .and_then(|c| serde_json::from_str::<serde_json::Value>(&c).ok())
        {
            Some(data) => {
                tokens.push(OAuthStatus {
                    service: "Google".to_string(),
                    valid: data
                        .get("token")
                        .and_then(|v| v.as_str())
                        .map(|s| !s.is_empty())
                        .unwrap_or(false),
                    scopes: data.get("scopes").and_then(|v| v.as_array()).map(|a| {
                        a.iter()
                            .filter_map(|v| v.as_str().map(String::from))
                            .collect()
                    }),
                    has_refresh: Some(
                        data.get("refresh_token")
                            .and_then(|v| v.as_str())
                            .map(|s| !s.is_empty())
                            .unwrap_or(false),
                    ),
                });
            }
            None => {
                tokens.push(OAuthStatus {
                    service: "Google".to_string(),
                    valid: false,
                    scopes: None,
                    has_refresh: None,
                });
            }
        }
    } else {
        tokens.push(OAuthStatus {
            service: "Google".to_string(),
            valid: false,
            scopes: None,
            has_refresh: None,
        });
    }

    // X/Twitter OAuth
    let x_token = home.join("x_oauth2_token.json");
    if x_token.exists() {
        match fs::read_to_string(&x_token)
            .ok()
            .and_then(|c| serde_json::from_str::<serde_json::Value>(&c).ok())
        {
            Some(data) => {
                tokens.push(OAuthStatus {
                    service: "X / Twitter".to_string(),
                    valid: data
                        .get("access_token")
                        .and_then(|v| v.as_str())
                        .map(|s| !s.is_empty())
                        .unwrap_or(false),
                    scopes: None,
                    has_refresh: Some(
                        data.get("refresh_token")
                            .and_then(|v| v.as_str())
                            .map(|s| !s.is_empty())
                            .unwrap_or(false),
                    ),
                });
            }
            None => {
                tokens.push(OAuthStatus {
                    service: "X / Twitter".to_string(),
                    valid: false,
                    scopes: None,
                    has_refresh: None,
                });
            }
        }
    } else {
        tokens.push(OAuthStatus {
            service: "X / Twitter".to_string(),
            valid: false,
            scopes: None,
            has_refresh: None,
        });
    }

    // Telegram session
    let telegram_session = home.join("telegram_user_session.session");
    tokens.push(OAuthStatus {
        service: "Telegram (User Session)".to_string(),
        valid: telegram_session.exists(),
        scopes: None,
        has_refresh: None,
    });

    Ok(tokens)
}
