use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// =============================================================================
// Agent Registry (registry.json)
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AgentRegistry {
    #[serde(default = "default_version")]
    pub version: u32,
    pub default_agent: Option<String>,
    #[serde(default)]
    pub agents: HashMap<String, AgentEntry>,
    #[serde(default)]
    pub relationships: Vec<RelationshipEntry>,
    #[serde(default)]
    pub owner: Option<OwnerEntry>,
}

fn default_version() -> u32 {
    1
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AgentEntry {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub role: String,
    #[serde(default = "default_active")]
    pub status: String,
    #[serde(default)]
    pub created_at: String,
    pub created_from: Option<String>,
    pub avatar: Option<String>,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub allowed_connections: Vec<String>,
}

// =============================================================================
// Connections (connections.yaml)
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ConnectionsFile {
    #[serde(default = "default_version")]
    pub version: u32,
    #[serde(default)]
    pub connections: HashMap<String, ConnectionEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ConnectionEntry {
    pub name: String,
    #[serde(rename = "type")]
    pub conn_type: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub credentials: HashMap<String, String>,
    #[serde(default)]
    pub mcp: HashMap<String, serde_json::Value>,
    #[serde(default)]
    pub provides_toolsets: Vec<String>,
    #[serde(default)]
    pub tools: HashMap<String, serde_json::Value>,
    #[serde(default = "default_enabled")]
    pub enabled: bool,
}

fn default_enabled() -> bool {
    true
}

#[derive(Debug, Clone, Serialize)]
pub struct ConnectionResponse {
    pub name: String,
    #[serde(rename = "type")]
    pub conn_type: String,
    pub description: String,
    pub tags: Vec<String>,
    pub credentials: HashMap<String, String>,
    pub mcp: HashMap<String, serde_json::Value>,
    pub provides_toolsets: Vec<String>,
    pub enabled: bool,
}

fn default_active() -> String {
    "active".to_string()
}

// =============================================================================
// Relationships & Owner
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RelationshipEntry {
    pub id: String,
    pub from_agent_id: String,
    pub to_agent_id: String,
    pub rel_type: String,
    pub matrix_room_id: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct OwnerEntry {
    #[serde(default = "default_owner_name")]
    pub name: String,
    pub avatar: Option<String>,
    #[serde(default)]
    pub about: Option<String>,
}

fn default_owner_name() -> String {
    "Human".to_string()
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RelationshipResponse {
    pub id: String,
    pub from_agent_id: String,
    pub to_agent_id: String,
    #[serde(rename = "type")]
    pub rel_type: String,
    pub matrix_room_id: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct OwnerResponse {
    pub name: String,
    pub avatar: Option<String>,
    pub about: Option<String>,
}

/// Response format for the frontend (matches what web.py returns).
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentResponse {
    pub id: String,
    pub name: String,
    pub role: String,
    pub url: String,
    pub status: String,
    pub platforms: Vec<String>,
    pub avatar: Option<String>,
    pub description: String,
    pub created_at: String,
    pub created_from: Option<String>,
    pub allowed_connections: Vec<String>,
    pub is_default: bool,
}

// =============================================================================
// Cron Jobs (jobs.json)
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CronFile {
    #[serde(default)]
    pub jobs: Vec<serde_json::Value>,
    pub updated_at: Option<String>,
}

/// Simplified cron response for frontend.
#[derive(Debug, Clone, Serialize)]
pub struct CronResponse {
    pub id: String,
    pub name: String,
    pub prompt: String,
    pub schedule: String,
    pub status: String,
    pub last_run: Option<String>,
    pub last_output: Option<String>,
}

// =============================================================================
// Rules (rules.json)
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RulesFile {
    #[serde(default)]
    pub rules: Vec<serde_json::Value>,
    pub updated_at: Option<String>,
}

/// Rule response for frontend.
#[derive(Debug, Clone, Serialize)]
pub struct RuleResponse {
    pub id: String,
    pub name: String,
    pub condition: String,
    pub action: String,
    pub enabled: bool,
    pub priority: i64,
    pub trigger_count: i64,
    pub max_triggers: Option<i64>,
    pub cooldown_minutes: Option<i64>,
    pub last_triggered_at: Option<String>,
    pub tags: Vec<String>,
}

// =============================================================================
// Sessions
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SessionMeta {
    pub id: String,
    #[serde(default)]
    pub name: String,
    pub agent_id: Option<String>,
    #[serde(default)]
    pub created_at: String,
    #[serde(default)]
    pub updated_at: String,
    #[serde(default)]
    pub preview: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[allow(dead_code)]
pub struct HistoryMessage {
    pub id: String,
    pub role: String,
    pub content: String,
    pub timestamp: String,
}

// =============================================================================
// Secrets & Providers
// =============================================================================

#[derive(Debug, Clone, Serialize)]
pub struct SecretResponse {
    pub key: String,
    pub masked_value: String,
    pub is_set: bool,
    pub category: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ProviderResponse {
    pub id: String,
    pub name: String,
    pub authenticated: bool,
    pub models: Vec<String>,
    pub env_keys: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct OAuthStatus {
    pub service: String,
    pub valid: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scopes: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub has_refresh: Option<bool>,
}

// =============================================================================
// Memories
// =============================================================================

#[derive(Debug, Clone, Serialize)]
pub struct MemoriesResponse {
    pub memory: String,
    pub user: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct SoulResponse {
    pub content: String,
}

// =============================================================================
// Wallet
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CreditCardEntry {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub number: String,
    #[serde(default)]
    pub expiry: String,
    #[serde(default)]
    pub code: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CryptoWalletEntry {
    #[serde(default)]
    pub vault_id: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub email: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct WalletFile {
    #[serde(default)]
    pub credit_card: Option<CreditCardEntry>,
    #[serde(default)]
    pub crypto: Option<CryptoWalletEntry>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct WalletResponse {
    pub credit_card: Option<CreditCardResponse>,
    pub crypto: Option<CryptoResponse>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CreditCardResponse {
    pub name: String,
    pub number: String,
    pub expiry: String,
    pub code: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CryptoResponse {
    pub vault_id: String,
    pub name: String,
    pub email: String,
}

// =============================================================================
// Status
// =============================================================================

#[derive(Debug, Clone, Serialize)]
pub struct OkResponse {
    pub ok: bool,
}

#[derive(Debug, Clone, Serialize)]
#[allow(dead_code)]
pub struct IntegrationResponse {
    pub id: String,
    pub name: String,
    pub category: String,
    pub status: String,
    #[serde(default)]
    pub details: serde_json::Value,
    pub updated_at: Option<String>,
}
