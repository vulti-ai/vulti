use crate::types::{CronFile, CronResponse};
use crate::vulti_home::{atomic_write_json, ensure_dir, read_json_file, vulti_home};
use std::fs;

fn cron_path(agent_id: Option<&str>) -> std::path::PathBuf {
    match agent_id {
        Some(id) => vulti_home().join("agents").join(id).join("cron").join("jobs.json"),
        None => vulti_home().join("cron").join("jobs.json"),
    }
}

fn load_cron_file(agent_id: Option<&str>) -> CronFile {
    let path = cron_path(agent_id);
    if path.exists() {
        read_json_file(&path)
    } else if agent_id.is_none() {
        // Only fall back to global dir when no specific agent requested
        read_json_file(&vulti_home().join("cron").join("jobs.json"))
    } else {
        CronFile::default()
    }
}

fn save_cron_file(file: &CronFile, agent_id: Option<&str>) -> Result<(), String> {
    let path = cron_path(agent_id);
    if let Some(parent) = path.parent() {
        ensure_dir(parent)?;
    }
    atomic_write_json(&path, file)
}

fn job_to_response(v: &serde_json::Value) -> CronResponse {
    let schedule_display = v
        .get("schedule_display")
        .and_then(|v| v.as_str())
        .or_else(|| {
            v.get("schedule")
                .and_then(|s| s.get("display"))
                .and_then(|d| d.as_str())
        })
        .unwrap_or("")
        .to_string();

    let status = if !v.get("enabled").and_then(|v| v.as_bool()).unwrap_or(true) {
        "paused"
    } else {
        match v.get("state").and_then(|v| v.as_str()) {
            Some("paused") => "paused",
            Some("completed") => "completed",
            _ => "active",
        }
    };

    let job_id = v
        .get("id")
        .and_then(|v| v.as_str())
        .unwrap_or("");

    // Read latest output from disk if available
    let last_output = if !job_id.is_empty() {
        let output_dir = vulti_home().join("cron").join("output").join(job_id);
        if output_dir.exists() {
            fs::read_dir(&output_dir)
                .ok()
                .and_then(|entries| {
                    entries
                        .flatten()
                        .filter(|e| e.path().extension().map(|ext| ext == "md").unwrap_or(false))
                        .max_by_key(|e| e.file_name())
                        .and_then(|e| fs::read_to_string(e.path()).ok())
                        .map(|s| {
                            // Truncate to first 500 chars for preview
                            if s.len() > 500 {
                                format!("{}...", &s[..500])
                            } else {
                                s
                            }
                        })
                })
        } else {
            None
        }
    } else {
        None
    };

    CronResponse {
        id: job_id.to_string(),
        name: v
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        prompt: v
            .get("prompt")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        schedule: schedule_display,
        status: status.to_string(),
        last_run: v
            .get("last_run_at")
            .and_then(|v| v.as_str())
            .map(String::from),
        last_output,
    }
}

#[tauri::command]
pub fn list_cron(agent_id: Option<String>) -> Result<Vec<CronResponse>, String> {
    let file = load_cron_file(agent_id.as_deref());
    let jobs: Vec<CronResponse> = file
        .jobs
        .iter()
        .map(|j| job_to_response(j))
        .collect();
    Ok(jobs)
}

#[tauri::command]
pub fn create_cron(data: serde_json::Value, agent_id: Option<String>) -> Result<serde_json::Value, String> {
    let mut file = load_cron_file(agent_id.as_deref());
    let job_id = uuid::Uuid::new_v4().to_string().replace("-", "")[..12].to_string();
    let now = chrono::Utc::now().to_rfc3339();

    let name = data
        .get("name")
        .and_then(|v| v.as_str())
        .unwrap_or("cron job")
        .to_string();
    let prompt = data
        .get("prompt")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let schedule_str = data
        .get("schedule")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    let effective_agent = agent_id.unwrap_or_else(|| "default".to_string());

    // Store the schedule as a simple object — Python scheduler will parse it
    let schedule = serde_json::json!({
        "kind": "interval",
        "display": &schedule_str,
    });

    let job = serde_json::json!({
        "id": job_id,
        "name": name,
        "prompt": prompt,
        "skills": [],
        "skill": null,
        "model": null,
        "provider": null,
        "base_url": null,
        "schedule": schedule,
        "schedule_display": &schedule_str,
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
        "agent": effective_agent,
        "persist_session": data.get("persist_session").and_then(|v| v.as_bool()).unwrap_or(false),
        "max_session_turns": data.get("max_session_turns").and_then(|v| v.as_u64()).unwrap_or(40),
    });

    file.jobs.push(job.clone());
    file.updated_at = Some(chrono::Utc::now().to_rfc3339());
    let effective_agent_ref = Some(effective_agent.as_str());
    save_cron_file(&file, effective_agent_ref)?;

    Ok(job)
}

/// Find which agent owns a cron job by scanning all agent dirs.
fn find_agent_for_job(job_id: &str) -> Option<String> {
    let agents_dir = vulti_home().join("agents");
    if let Ok(entries) = fs::read_dir(&agents_dir) {
        for entry in entries.flatten() {
            if !entry.path().is_dir() { continue; }
            let agent_id = entry.file_name().to_string_lossy().to_string();
            if agent_id == "registry.json" { continue; }
            let jobs_path = entry.path().join("cron").join("jobs.json");
            if jobs_path.exists() {
                let file: CronFile = read_json_file(&jobs_path);
                if file.jobs.iter().any(|j| j.get("id").and_then(|v| v.as_str()) == Some(job_id)) {
                    return Some(agent_id);
                }
            }
        }
    }
    None
}

#[tauri::command]
pub fn update_cron(job_id: String, updates: serde_json::Value) -> Result<CronResponse, String> {
    let owner = find_agent_for_job(&job_id);
    let mut file = load_cron_file(owner.as_deref());

    for job in file.jobs.iter_mut() {
        if job.get("id").and_then(|v| v.as_str()) == Some(&job_id) {
            if let (Some(job_obj), Some(updates_obj)) = (job.as_object_mut(), updates.as_object()) {
                // Handle status -> enabled/state mapping
                if let Some(status) = updates_obj.get("status").and_then(|v| v.as_str()) {
                    match status {
                        "paused" => {
                            job_obj.insert(
                                "enabled".to_string(),
                                serde_json::Value::Bool(false),
                            );
                            job_obj.insert(
                                "state".to_string(),
                                serde_json::Value::String("paused".to_string()),
                            );
                        }
                        "active" => {
                            job_obj
                                .insert("enabled".to_string(), serde_json::Value::Bool(true));
                            job_obj.insert(
                                "state".to_string(),
                                serde_json::Value::String("scheduled".to_string()),
                            );
                        }
                        _ => {}
                    }
                }
                for (k, v) in updates_obj {
                    if k != "status" {
                        job_obj.insert(k.clone(), v.clone());
                    }
                }
            }
            let response = job_to_response(job);
            file.updated_at = Some(chrono::Utc::now().to_rfc3339());
            save_cron_file(&file, owner.as_deref())?;
            return Ok(response);
        }
    }
    Err(format!("Cron job '{}' not found", job_id))
}

#[tauri::command]
pub fn delete_cron(job_id: String) -> Result<serde_json::Value, String> {
    let owner = find_agent_for_job(&job_id);
    let mut file = load_cron_file(owner.as_deref());
    let original_len = file.jobs.len();
    file.jobs
        .retain(|j| j.get("id").and_then(|v| v.as_str()) != Some(&job_id));

    if file.jobs.len() < original_len {
        file.updated_at = Some(chrono::Utc::now().to_rfc3339());
        save_cron_file(&file, owner.as_deref())?;
        Ok(serde_json::json!({"ok": true}))
    } else {
        Err(format!("Cron job '{}' not found", job_id))
    }
}
