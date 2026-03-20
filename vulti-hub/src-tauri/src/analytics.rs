use crate::vulti_home::vulti_home;
use rusqlite::{Connection, params_from_iter};
use serde::Serialize;

fn state_db_path() -> std::path::PathBuf {
    vulti_home().join("state.db")
}

#[derive(Debug, Clone, Serialize, Default)]
pub struct ActivityStats {
    pub hourly_distribution: Vec<u64>,
    pub daily_distribution: Vec<u64>,
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
    #[serde(skip_serializing_if = "Option::is_none")]
    pub activity: Option<ActivityStats>,
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
    pub total_hours: f64,
    pub avg_session_duration: f64,
    pub avg_messages_per_session: f64,
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
fn build_filter(cutoff: f64, agent_id: &Option<String>) -> (String, Vec<Box<dyn rusqlite::types::ToSql>>) {
    let mut conditions = vec!["s.started_at >= ?".to_string()];
    let mut params: Vec<Box<dyn rusqlite::types::ToSql>> = vec![Box::new(cutoff)];
    if let Some(aid) = agent_id {
        conditions.push("s.agent_id = ?".to_string());
        params.push(Box::new(aid.clone()));
    }
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
                COALESCE(SUM(s.input_tokens),0), COALESCE(SUM(s.output_tokens),0),
                COALESCE(SUM(CASE WHEN s.ended_at IS NOT NULL THEN s.ended_at - s.started_at ELSE 0 END), 0)
         FROM sessions s WHERE {wc}"
    );
    let overview = conn.query_row(&sql, params_from_iter(p.iter().map(|x| x.as_ref())), |row| {
        let inp: u64 = row.get(3)?;
        let out: u64 = row.get(4)?;
        let total_seconds: f64 = row.get(5)?;
        let total_sessions: u64 = row.get(0)?;
        let total_messages: u64 = row.get(1)?;
        let avg_msgs = if total_sessions > 0 { total_messages as f64 / total_sessions as f64 } else { 0.0 };
        let avg_dur = if total_sessions > 0 { total_seconds / total_sessions as f64 } else { 0.0 };
        Ok(OverviewStats {
            total_sessions,
            total_messages,
            total_tool_calls: row.get(2)?,
            total_input_tokens: inp,
            total_output_tokens: out,
            total_tokens: inp + out,
            estimated_cost: 0.0,
            user_messages: 0,
            assistant_messages: 0,
            total_hours: total_seconds / 3600.0,
            avg_session_duration: avg_dur,
            avg_messages_per_session: avg_msgs,
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

    // Activity: daily distribution (day of week: 0=Sun..6=Sat)
    let (wc, p) = build_filter(cutoff, &agent_id);
    let sql = format!(
        "SELECT CAST(strftime('%w', s.started_at, 'unixepoch') AS INTEGER) as dow, COUNT(*)
         FROM sessions s WHERE {wc} GROUP BY dow ORDER BY dow"
    );
    let mut daily_distribution = vec![0u64; 7];
    {
        let mut stmt = conn.prepare(&sql).map_err(|e| e.to_string())?;
        let mut rows = stmt.query(params_from_iter(p.iter().map(|x| x.as_ref()))).map_err(|e| e.to_string())?;
        while let Some(row) = rows.next().map_err(|e| e.to_string())? {
            let dow: usize = row.get::<_, i64>(0).unwrap_or(0) as usize;
            let count: u64 = row.get::<_, u64>(1).unwrap_or(0);
            if dow < 7 { daily_distribution[dow] = count; }
        }
    }

    // Activity: hourly distribution
    let (wc, p) = build_filter(cutoff, &agent_id);
    let sql = format!(
        "SELECT CAST(strftime('%H', s.started_at, 'unixepoch') AS INTEGER) as hr, COUNT(*)
         FROM sessions s WHERE {wc} GROUP BY hr ORDER BY hr"
    );
    let mut hourly_distribution = vec![0u64; 24];
    {
        let mut stmt = conn.prepare(&sql).map_err(|e| e.to_string())?;
        let mut rows = stmt.query(params_from_iter(p.iter().map(|x| x.as_ref()))).map_err(|e| e.to_string())?;
        while let Some(row) = rows.next().map_err(|e| e.to_string())? {
            let hr: usize = row.get::<_, i64>(0).unwrap_or(0) as usize;
            let count: u64 = row.get::<_, u64>(1).unwrap_or(0);
            if hr < 24 { hourly_distribution[hr] = count; }
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
        activity: Some(ActivityStats { hourly_distribution, daily_distribution }),
    })
}
