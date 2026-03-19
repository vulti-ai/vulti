use notify::{Config, Event, EventKind, RecommendedWatcher, RecursiveMode, Watcher};
use serde::Serialize;
use std::path::PathBuf;
use std::sync::mpsc;
use std::sync::Mutex;
use tauri::Emitter;

use crate::vulti_home::vulti_home;

#[derive(Clone, Serialize)]
pub struct FileChanged {
    /// "soul", "memory", or "user"
    pub kind: String,
    /// Agent ID if agent-specific, empty for global
    pub agent_id: String,
}

pub struct WatcherState(pub Mutex<Option<RecommendedWatcher>>);

/// Start watching ~/.vulti for SOUL.md and memory file changes.
/// Emits "file-changed" events to the Tauri frontend.
pub fn start_watcher(app: tauri::AppHandle) {
    let home = vulti_home();

    let (tx, rx) = mpsc::channel::<Result<Event, notify::Error>>();

    let mut watcher = match RecommendedWatcher::new(tx, Config::default()) {
        Ok(w) => w,
        Err(e) => {
            eprintln!("[watcher] failed to create: {e}");
            return;
        }
    };

    // Watch the entire vulti home recursively
    if let Err(e) = watcher.watch(&home, RecursiveMode::Recursive) {
        eprintln!("[watcher] failed to watch {}: {e}", home.display());
        return;
    }

    // Store watcher so it doesn't get dropped
    if let Some(state) = app.try_state::<WatcherState>() {
        if let Ok(mut guard) = state.0.lock() {
            *guard = Some(watcher);
        }
    }

    let home_clone = home.clone();
    std::thread::spawn(move || {
        for res in rx {
            let event = match res {
                Ok(e) => e,
                Err(_) => continue,
            };

            // Only care about creates/modifies (not removes, renames, etc.)
            match event.kind {
                EventKind::Create(_) | EventKind::Modify(_) => {}
                _ => continue,
            }

            for path in &event.paths {
                if let Some(changed) = classify_path(path, &home_clone) {
                    let _ = app.emit("file-changed", changed);
                }
            }
        }
    });
}

/// Determine if a changed path is a soul/memory file we care about.
fn classify_path(path: &PathBuf, home: &PathBuf) -> Option<FileChanged> {
    let filename = path.file_name()?.to_str()?;

    let kind = match filename {
        "SOUL.md" => "soul",
        "MEMORY.md" => "memory",
        "USER.md" => "user",
        _ => return None,
    };

    // Ignore .tmp files from atomic writes
    if path.extension().map(|e| e == "tmp").unwrap_or(false) {
        return None;
    }

    // Extract agent_id from path: ~/.vulti/agents/{agent_id}/...
    let rel = path.strip_prefix(home).ok()?;
    let components: Vec<&str> = rel.components()
        .filter_map(|c| c.as_os_str().to_str())
        .collect();

    let agent_id = if components.len() >= 2 && components[0] == "agents" {
        components[1].to_string()
    } else {
        String::new()
    };

    Some(FileChanged {
        kind: kind.to_string(),
        agent_id,
    })
}
