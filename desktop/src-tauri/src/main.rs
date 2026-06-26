#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use tauri::Manager;

#[derive(Serialize, Clone)]
struct DesktopSettings {
    backend_url: String,
    offline_mode: bool,
    ollama_endpoint: String,
    export_permissions: Vec<String>,
}

#[tauri::command]
fn get_desktop_settings() -> DesktopSettings {
    DesktopSettings {
        backend_url: "http://127.0.0.1:8899".to_string(),
        offline_mode: true,
        ollama_endpoint: "http://127.0.0.1:11434".to_string(),
        export_permissions: vec!["reports".to_string(), "csv".to_string(), "json".to_string()],
    }
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![get_desktop_settings])
        .setup(|app| {
            let _window = app.get_webview_window("main");
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running ALETHEIA desktop")
}

