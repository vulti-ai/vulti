use crate::vulti_home::vulti_home;
use rusqlite::{Connection, params_from_iter};
use serde::Serialize;

fn state_db_path() -> std::path::PathBuf {
    vulti_home().join("state.db")
}

#[derive(Debug, Clone, Serialize, Default)]
pub struct AnalyticsResponse {
    pub days: u32,
    pub empty: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub overview: Option<OverviewStats>,
    #[serde(default)]
    pub models: Vec<ModelStats>,
    #[serde(default)]
    pub platforms: Vec<PlatformStats>,
    #[serde(default)]
    pub tools: Vec<ToolStats>,
}

#[derive(Debug, Clone, Serialize, Default)]
pub struct OverviewStats {
    pub total_sessions: u64,
    pub total_messages: u64,
    pub total_tool_calls: u64,
    pub total_input_tokens: u64,
    pub total_output_tokens: u64,
    pub total_tokens: u64,
    pub estimated_cost: f64,
    pub user_messages: u64,
    pub assistant_messages: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ModelStats {
    pub model: String,
    pub sessions: u64,
    pub total_tokens: u64,
    pub cost: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct PlatformStats {
    pub platform: String,
    pub sessions: u64,
    pub messages: u64,
    pub total_tokens: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ToolStats {
    pub tool_name: String,
    pub call_count: u64,
    pub sessions: u64,
}

fn open_db() -> Result<Connection, String> {
    let path = state_db_path();
    if !path.exists() {
        return Err("No session database found".to_string());
    }
    Connection::open_with_flags(
        &path,
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .map_err(|e| format!("Failed to open state.db: {e}"))
}

/// Build WHERE clause and parameter list for session-scoped queries.
/// Note: agent_id filtering is accepted but currently shows all sessions,
/// since the sessions table doesn't have an agent_id column yet.
fn build_filter(cutoff: f64, _agent_id: &Option<String>) -> (String, Vec<Box<dyn rusqlite::types::ToSql>>) {
    let conditions = vec!["s.started_at >= ?".to_string()];
    let params: Vec<Box<dyn rusqlite::types::ToSql>> = vec![Box::new(cutoff)];
    (conditions.join(" AND "), params)
}

#[tauri::command]
pub fn get_analytics(days: Option<u32>, agent_id: Option<String>) -> Result<AnalyticsResponse, String> {
    let days = days.unwrap_or(30);
    let cutoff = chrono::Utc::now().timestamp() as f64 - (days as f64 * 86400.0);
    let conn = open_db()?;
    let (where_clause, params) = build_filter(cutoff, &agent_id);

    // Session count
    let sql = format!("SELECT COUNT(*) FROM sessions s WHERE {where_clause}");
    let session_count: u64 = conn
        .query_row(&sql, params_from_iter(params.iter().map(|p| p.as_ref())), |r| r.get(0))
        .unwrap_or(0);

    if session_count == 0 {
        return Ok(AnalyticsResponse { days, empty: true, ..Default::default() });
    }

    // Overview
    let (wc, p) = build_filter(cutoff, &agent_id);
    let sql = format!(
        "SELECT COUNT(*), COALESCE(SUM(s.message_count),0), COALESCE(SUM(s.tool_call_count),0),
                COALESCE(SUM(s.input_tokens),0), COALESCE(SUM(s.output_tokens),0)
         FROM sessions s WHERE {wc}"
    );
    let overview = conn.query_row(&sql, params_from_iter(p.iter().map(|x| x.as_ref())), |row| {
        let inp: u64 = row.get(3)?;
        let out: u64 = row.get(4)?;
        Ok(OverviewStats {
            total_sessions: row.get(0)?,
            total_messages: row.get(1)?,
            total_tool_calls: row.get(2)?,
            total_input_tokens: inp,
            total_output_tokens: out,
            total_tokens: inp + out,
            estimated_cost: 0.0,
            user_messages: 0,
            assistant_messages: 0,
        })
    }).unwrap_or_default();

    // Message role counts
    let (wc, p) = build_filter(cutoff, &agent_id);
    let sql = format!(
        "SELECT COALESCE(SUM(CASE WHEN m.role='user' THEN 1 ELSE 0 END),0),
                COALESCE(SUM(CASE WHEN m.role='assistant' THEN 1 ELSE 0 END),0)
         FROM messages m JOIN sessions s ON s.id = m.session_id WHERE {wc}"
    );
    let (user_msgs, asst_msgs) = conn.query_row(&sql, params_from_iter(p.iter().map(|x| x.as_ref())), |r| {
        Ok((r.get::<_, u64>(0)?, r.get::<_, u64>(1)?))
    }).unwrap_or((0, 0));

    let overview = OverviewStats { user_messages: user_msgs, assistant_messages: asst_msgs, ..overview };

    // Models
    let (wc, p) = build_filter(cutoff, &agent_id);
    let sql = format!(
        "SELECT s.model, COUNT(*), COALESCE(SUM(s.input_tokens+s.output_tokens),0)
         FROM sessions s WHERE {wc} AND s.model IS NOT NULL GROUP BY s.model ORDER BY 2 DESC"
    );
    let mut models = Vec::new();
    {
        let mut stmt = conn.prepare(&sql).map_err(|e| e.to_string())?;
        let mut rows = stmt.query(params_from_iter(p.iter().map(|x| x.as_ref()))).map_err(|e| e.to_string())?;
        while let Some(row) = rows.next().map_err(|e| e.to_string())? {
            models.push(ModelStats {
                model: row.get::<_, String>(0).unwrap_or_default(),
                sessions: row.get::<_, u64>(1).unwrap_or(0),
                total_tokens: row.get::<_, u64>(2).unwrap_or(0),
                cost: 0.0,
            });
        }
    }

    // Platforms
    let (wc, p) = build_filter(cutoff, &agent_id);
    let sql = format!(
        "SELECT s.source, COUNT(*), COALESCE(SUM(s.message_count),0), COALESCE(SUM(s.input_tokens+s.output_tokens),0)
         FROM sessions s WHERE {wc} AND s.source IS NOT NULL GROUP BY s.source ORDER BY 2 DESC"
    );
    let mut platforms = Vec::new();
    {
        let mut stmt = conn.prepare(&sql).map_err(|e| e.to_string())?;
        let mut rows = stmt.query(params_from_iter(p.iter().map(|x| x.as_ref()))).map_err(|e| e.to_string())?;
        while let Some(row) = rows.next().map_err(|e| e.to_string())? {
            platforms.push(PlatformStats {
                platform: row.get::<_, String>(0).unwrap_or_default(),
                sessions: row.get::<_, u64>(1).unwrap_or(0),
                messages: row.get::<_, u64>(2).unwrap_or(0),
                total_tokens: row.get::<_, u64>(3).unwrap_or(0),
            });
        }
    }

    // Tools
    let (wc, p) = build_filter(cutoff, &agent_id);
    let sql = format!(
        "SELECT m.tool_name, COUNT(*), COUNT(DISTINCT m.session_id)
         FROM messages m JOIN sessions s ON s.id = m.session_id
         WHERE {wc} AND m.role='tool' AND m.tool_name IS NOT NULL
         GROUP BY m.tool_name ORDER BY 2 DESC LIMIT 20"
    );
    let mut tools = Vec::new();
    {
        let mut stmt = conn.prepare(&sql).map_err(|e| e.to_string())?;
        let mut rows = stmt.query(params_from_iter(p.iter().map(|x| x.as_ref()))).map_err(|e| e.to_string())?;
        while let Some(row) = rows.next().map_err(|e| e.to_string())? {
            tools.push(ToolStats {
                tool_name: row.get::<_, String>(0).unwrap_or_default(),
                call_count: row.get::<_, u64>(1).unwrap_or(0),
                sessions: row.get::<_, u64>(2).unwrap_or(0),
            });
        }
    }

    Ok(AnalyticsResponse {
        days,
        empty: false,
        error: None,
        overview: Some(overview),
        models,
        platforms,
        tools,
    })
}
