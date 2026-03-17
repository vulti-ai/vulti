use std::process::Command;
use tauri::{Manager, menu::{Menu, MenuItem}, tray::TrayIconBuilder};
use serde::Serialize;

#[derive(Serialize)]
pub struct TailscaleStatus {
    installed: bool,
    running: bool,
    ip: Option<String>,
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
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
        .invoke_handler(tauri::generate_handler![tailscale_status, install_tailscale, open_tailscale])
        .run(tauri::generate_context!())
        .expect("error while running Vulti Gateway");
}
