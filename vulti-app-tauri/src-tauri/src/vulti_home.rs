use serde::Serialize;
use std::fs;
use std::io::Write;
use std::path::PathBuf;

/// Resolve the Vulti home directory (~/.vulti/ or $VULTI_HOME).
pub fn vulti_home() -> PathBuf {
    if let Ok(h) = std::env::var("VULTI_HOME") {
        PathBuf::from(h)
    } else {
        dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".vulti")
    }
}

/// Read a JSON file and deserialize it. Returns default on missing or invalid.
pub fn read_json_file<T: serde::de::DeserializeOwned + Default>(path: &std::path::Path) -> T {
    match fs::read_to_string(path) {
        Ok(content) => serde_json::from_str(&content).unwrap_or_default(),
        Err(_) => T::default(),
    }
}

/// Read a text file. Returns empty string on missing.
pub fn read_text_file(path: &std::path::Path) -> String {
    fs::read_to_string(path).unwrap_or_default()
}

/// Atomic write: write to .tmp file, fsync, rename. Sets 0o600 permissions.
pub fn atomic_write_json<T: Serialize>(path: &std::path::Path, value: &T) -> Result<(), String> {
    let content =
        serde_json::to_string_pretty(value).map_err(|e| format!("JSON serialize error: {e}"))?;
    atomic_write_text(path, &(content + "\n"))
}

/// Atomic write for text content.
pub fn atomic_write_text(path: &std::path::Path, content: &str) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("mkdir error: {e}"))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = fs::set_permissions(parent, fs::Permissions::from_mode(0o700));
        }
    }

    let tmp_path = path.with_extension("tmp");
    let mut file = fs::File::create(&tmp_path).map_err(|e| format!("create tmp error: {e}"))?;
    file.write_all(content.as_bytes())
        .map_err(|e| format!("write error: {e}"))?;
    file.sync_all()
        .map_err(|e| format!("fsync error: {e}"))?;
    drop(file);

    fs::rename(&tmp_path, path).map_err(|e| format!("rename error: {e}"))?;

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(path, fs::Permissions::from_mode(0o600));
    }

    Ok(())
}

/// Ensure a directory exists with 0o700 permissions.
pub fn ensure_dir(path: &std::path::Path) -> Result<(), String> {
    fs::create_dir_all(path).map_err(|e| format!("mkdir error: {e}"))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(path, fs::Permissions::from_mode(0o700));
    }
    Ok(())
}
