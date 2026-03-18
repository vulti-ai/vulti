use std::process::Command;
use std::sync::Mutex;
use tauri::{Manager, menu::{Menu, MenuItem}, tray::TrayIconBuilder};
use serde::Serialize;

mod types;
mod vulti_home;
mod agents;
mod memories;
mod rules;
mod cron;
mod secrets;
mod sessions;
mod status;

// Hold the gateway child process so we can kill it on exit
struct GatewayProcess(Mutex<Option<std::process::Child>>);

#[derive(Serialize)]
pub struct GatewayStatus {
    running: bool,
    pid: Option<u32>,
}

#[derive(Serialize)]
pub struct TailscaleStatus {
    installed: bool,
    running: bool,
    ip: Option<String>,
}

#[tauri::command]
fn start_gateway(state: tauri::State<'_, GatewayProcess>) -> Result<GatewayStatus, String> {
    // Check if already running
    {
        let mut guard = state.0.lock().map_err(|e| e.to_string())?;
        if let Some(ref mut child) = *guard {
            // Check if the process is still alive
            match child.try_wait() {
                Ok(None) => {
                    // Still running
                    return Ok(GatewayStatus { running: true, pid: Some(child.id()) });
                }
                _ => {
                    // Exited, clear it
                    *guard = None;
                }
            }
        }
    }

    // Find vulti binary - check common locations
    let home = std::env::var("HOME").unwrap_or_default();
    let candidates = [
        format!("{}/.local/bin/vulti", home),
        format!("{}/.vulti/bin/vulti", home),
        "/usr/local/bin/vulti".to_string(),
    ];

    // Also try `which` via a login shell to get the user's PATH
    let shell_which = Command::new("/bin/zsh")
        .args(["-lc", "which vulti"])
        .output()
        .ok()
        .and_then(|o| {
            if o.status.success() {
                String::from_utf8(o.stdout).ok().map(|s| s.trim().to_string())
            } else {
                None
            }
        });

    let bin = shell_which
        .or_else(|| candidates.iter().find(|p| std::path::Path::new(p).exists()).cloned())
        .ok_or_else(|| "Vulti CLI not found. Install it first with: curl -fsSL https://vulti.ai/install | bash".to_string())?;

    // Spawn gateway process via login shell so it inherits PATH and venv
    // Use --replace to take over any stale gateway instance
    let child = Command::new("/bin/zsh")
        .args(["-lc", &format!("{} gateway run --replace", bin)])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .map_err(|e| format!("Failed to start gateway: {}", e))?;

    let pid = child.id();
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    *guard = Some(child);

    Ok(GatewayStatus { running: true, pid: Some(pid) })
}

#[tauri::command]
fn get_gateway_token() -> Result<String, String> {
    let home = std::env::var("HOME").unwrap_or_default();
    let path = format!("{}/.vulti/web_token", home);
    std::fs::read_to_string(&path)
        .map(|s| s.trim().to_string())
        .map_err(|e| format!("Could not read token from {}: {}", path, e))
}

#[tauri::command]
fn check_gateway() -> GatewayStatus {
    // Try to reach the gateway API - accept any HTTP response (even 401) as proof it's running
    let running = Command::new("curl")
        .args(["-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", "2", "http://localhost:8080/api/status"])
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|code| code.trim() != "000")
        .unwrap_or(false);

    GatewayStatus { running, pid: None }
}

#[tauri::command]
fn stop_gateway(state: tauri::State<'_, GatewayProcess>) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    if let Some(ref mut child) = *guard {
        let _ = child.kill();
        let _ = child.wait();
    }
    *guard = None;
    Ok(())
}

#[tauri::command]
fn tailscale_status() -> TailscaleStatus {
    // Check if tailscale CLI exists
    let installed = Command::new("which")
        .arg("tailscale")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
        || std::path::Path::new("/Applications/Tailscale.app").exists();

    if !installed {
        return TailscaleStatus { installed: false, running: false, ip: None };
    }

    // Try to get the IP (implies it's running and connected)
    let ip = Command::new("tailscale")
        .arg("ip")
        .arg("-4")
        .output()
        .ok()
        .and_then(|o| {
            if o.status.success() {
                String::from_utf8(o.stdout).ok().map(|s| s.trim().to_string())
            } else {
                None
            }
        });

    let running = ip.is_some();
    TailscaleStatus { installed, running, ip }
}

#[tauri::command]
fn install_tailscale() -> Result<String, String> {
    // Try brew install first
    let output = Command::new("brew")
        .args(["install", "--cask", "tailscale"])
        .output()
        .map_err(|e| format!("Failed to run brew: {}", e))?;

    if output.status.success() {
        // Open Tailscale app after install
        let _ = Command::new("open")
            .arg("-a")
            .arg("Tailscale")
            .spawn();
        Ok("Tailscale installed successfully".to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        if stderr.contains("already installed") {
            // Already installed, just open it
            let _ = Command::new("open")
                .arg("-a")
                .arg("Tailscale")
                .spawn();
            Ok("Tailscale is already installed".to_string())
        } else {
            Err(format!("Installation failed: {}", stderr))
        }
    }
}

#[tauri::command]
fn open_tailscale() -> Result<(), String> {
    Command::new("open")
        .arg("-a")
        .arg("Tailscale")
        .spawn()
        .map_err(|e| format!("Failed to open Tailscale: {}", e))?;
    Ok(())
}

#[tauri::command]
fn get_continuwuity_path(app_handle: tauri::AppHandle) -> Result<String, String> {
    // Resolve the bundled sidecar binary path.
    // Tauri places sidecars next to the app binary with the original name.
    let resource_dir = app_handle.path().resource_dir()
        .map_err(|e| format!("Cannot resolve resource dir: {}", e))?;

    // Check for the sidecar binary (Tauri strips the target triple at runtime)
    let sidecar_path = resource_dir.join("continuwuity");
    if sidecar_path.exists() {
        let path_str = sidecar_path.to_string_lossy().to_string();
        // Write to a well-known location so the Python gateway can find it
        let home = std::env::var("HOME").unwrap_or_default();
        let marker_dir = format!("{}/.vulti/continuwuity", home);
        let _ = std::fs::create_dir_all(&marker_dir);
        let _ = std::fs::write(format!("{}/sidecar_path", marker_dir), &path_str);
        return Ok(path_str);
    }

    Err("Bundled continuwuity binary not found".to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(GatewayProcess(Mutex::new(None)))
        .setup(|app| {
            // Write the bundled continuwuity sidecar path so the Python gateway can find it
            if let Ok(resource_dir) = app.path().resource_dir() {
                let sidecar = resource_dir.join("continuwuity");
                if sidecar.exists() {
                    let home = std::env::var("HOME").unwrap_or_default();
                    let marker_dir = format!("{}/.vulti/continuwuity", home);
                    let _ = std::fs::create_dir_all(&marker_dir);
                    let _ = std::fs::write(
                        format!("{}/sidecar_path", marker_dir),
                        sidecar.to_string_lossy().as_ref(),
                    );
                }
            }

            let quit = MenuItem::with_id(app, "quit", "Quit Vulti", true, None::<&str>)?;
            let show = MenuItem::with_id(app, "show", "Show Window", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;

            TrayIconBuilder::new()
                .menu(&menu)
                .tooltip("Vulti Gateway")
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        app.exit(0);
                    }
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            // Existing gateway management
            start_gateway, check_gateway, stop_gateway, get_gateway_token,
            tailscale_status, install_tailscale, open_tailscale, get_continuwuity_path,
            // Agents
            agents::list_agents, agents::get_agent, agents::create_agent, agents::update_agent,
            // Memories & Soul
            memories::get_memories, memories::update_memory, memories::get_soul, memories::update_soul,
            // Rules
            rules::list_rules, rules::create_rule, rules::update_rule, rules::delete_rule,
            // Cron
            cron::list_cron, cron::create_cron, cron::update_cron, cron::delete_cron,
            // Secrets & Providers
            secrets::list_secrets, secrets::add_secret, secrets::delete_secret,
            secrets::list_providers, secrets::get_oauth_status,
            // Sessions
            sessions::list_sessions, sessions::create_session, sessions::delete_session,
            sessions::get_history,
            // Status
            status::get_system_status, status::get_channel_directory, status::get_integrations,
        ])
        .build(tauri::generate_context!())
        .expect("error while building Vulti Gateway")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                // Kill the gateway process on app exit
                if let Some(state) = app.try_state::<GatewayProcess>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(ref mut child) = *guard {
                            let _ = child.kill();
                            let _ = child.wait();
                        }
                    }
                }
            }
        });
}
