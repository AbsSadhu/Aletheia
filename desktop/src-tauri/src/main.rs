#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! ALETHEIA Desktop — Tauri Application Entry Point
//!
//! This module handles:
//! 1. Spawning the Python FastAPI backend sidecar (`uvicorn aletheia.core.main:app`)
//! 2. Spawning the Rust compute sidecar (`aletheia-engine`)
//! 3. System tray icon with start/stop/open controls
//! 4. Graceful shutdown of all child processes when the window closes

use std::sync::{Arc, Mutex};
use std::process::Child;

use serde::Serialize;
use tauri::{
    Manager,
    menu::{MenuBuilder, MenuItem},
    tray::{MouseButton, TrayIconBuilder, TrayIconEvent},
    Emitter,
};

// ---------------------------------------------------------------------------
// Shared state to track child processes
// ---------------------------------------------------------------------------

struct SidecarState {
    engine: Option<Child>,
    api: Option<Child>,
}

impl SidecarState {
    fn new() -> Self {
        Self { engine: None, api: None }
    }

    fn kill_all(&mut self) {
        if let Some(mut child) = self.engine.take() {
            let _ = child.kill();
        }
        if let Some(mut child) = self.api.take() {
            let _ = child.kill();
        }
    }
}

type SharedState = Arc<Mutex<SidecarState>>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn find_workspace_root(app_dir: &std::path::Path) -> std::path::PathBuf {
    // Walk up until we find pyproject.toml — that's the workspace root
    let mut current = app_dir.to_path_buf();
    for _ in 0..10 {
        if current.join("pyproject.toml").exists() {
            return current;
        }
        if let Some(parent) = current.parent() {
            current = parent.to_path_buf();
        } else {
            break;
        }
    }
    // Fallback: assume 3 levels above the Tauri resources dir
    app_dir.join("../../..").canonicalize().unwrap_or_else(|_| app_dir.to_path_buf())
}

fn spawn_engine(workspace: &std::path::Path) -> Option<Child> {
    let exe = workspace.join("aletheia_engine/target/release/aletheia-engine.exe");
    if !exe.exists() {
        eprintln!("[ALETHEIA] Engine binary not found at {:?} — skipping sidecar", exe);
        return None;
    }
    match std::process::Command::new(&exe)
        .current_dir(workspace)
        .spawn()
    {
        Ok(child) => {
            println!("[ALETHEIA] aletheia-engine started (PID {})", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("[ALETHEIA] Failed to start aletheia-engine: {e}");
            None
        }
    }
}

fn spawn_api(workspace: &std::path::Path) -> Option<Child> {
    let python = workspace.join(".venv/Scripts/python.exe");
    if !python.exists() {
        eprintln!("[ALETHEIA] Python not found at {:?} — skipping API sidecar", python);
        return None;
    }
    match std::process::Command::new(&python)
        .args([
            "-m", "uvicorn", "aletheia.core.main:app",
            "--host", "127.0.0.1",
            "--port", "8899",
        ])
        .current_dir(workspace)
        .env("ALETHEIA_SKIP_PREFLIGHT", "false")
        .spawn()
    {
        Ok(child) => {
            println!("[ALETHEIA] FastAPI backend started (PID {})", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("[ALETHEIA] Failed to start FastAPI backend: {e}");
            None
        }
    }
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

#[derive(Serialize, Clone)]
struct DesktopSettings {
    backend_url: String,
    offline_mode: bool,
    ollama_endpoint: String,
    export_permissions: Vec<String>,
    engine_running: bool,
    api_running: bool,
}

#[tauri::command]
fn get_desktop_settings(state: tauri::State<'_, SharedState>) -> DesktopSettings {
    let lock = state.lock().unwrap();
    DesktopSettings {
        backend_url: "http://127.0.0.1:8899".to_string(),
        offline_mode: true,
        ollama_endpoint: "http://127.0.0.1:11434".to_string(),
        export_permissions: vec!["reports".to_string(), "csv".to_string(), "json".to_string()],
        engine_running: lock.engine.is_some(),
        api_running: lock.api.is_some(),
    }
}

#[tauri::command]
fn restart_sidecars(app: tauri::AppHandle, state: tauri::State<'_, SharedState>) -> String {
    let mut lock = state.lock().unwrap();
    lock.kill_all();

    let res_dir = app.path().resource_dir().unwrap_or_default();
    let workspace = find_workspace_root(&res_dir);

    lock.engine = spawn_engine(&workspace);
    lock.api = spawn_api(&workspace);

    format!(
        "engine={} api={}",
        lock.engine.is_some(),
        lock.api.is_some()
    )
}

#[tauri::command]
fn stop_sidecars(state: tauri::State<'_, SharedState>) -> String {
    let mut lock = state.lock().unwrap();
    lock.kill_all();
    "stopped".to_string()
}

// ---------------------------------------------------------------------------
// Health-gated window reveal
// ---------------------------------------------------------------------------

/// Polls a sidecar's health endpoint until it responds OK or `deadline` elapses.
fn wait_until_healthy(client: &reqwest::blocking::Client, url: &str, deadline: std::time::Instant) -> bool {
    while std::time::Instant::now() < deadline {
        if let Ok(resp) = client.get(url).send() {
            if resp.status().is_success() {
                return true;
            }
        }
        std::thread::sleep(std::time::Duration::from_millis(250));
    }
    false
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

fn main() {
    let shared_state: SharedState = Arc::new(Mutex::new(SidecarState::new()));

    // Windows Job Object: assigns this process (and, by inheritance, every
    // child it spawns afterwards — the two sidecars) to a job with
    // kill-on-close semantics. If this process dies for ANY reason,
    // including a hard Task Manager kill that skips our own cleanup code,
    // Windows tears down the whole process tree instead of leaving orphaned
    // python.exe / aletheia-engine.exe processes running.
    #[cfg(windows)]
    let _job_guard = {
        match win32job::Job::create() {
            Ok(job) => match job.query_extended_limit_info() {
                Ok(mut info) => {
                    info.limit_kill_on_job_close();
                    if let Err(e) = job.set_extended_limit_info(&info) {
                        eprintln!("[ALETHEIA] Failed to configure Job Object: {e}");
                    }
                    if let Err(e) = job.assign_current_process() {
                        eprintln!("[ALETHEIA] Failed to assign process to Job Object: {e}");
                    }
                    Some(job)
                }
                Err(e) => {
                    eprintln!("[ALETHEIA] Failed to query Job Object limits: {e}");
                    None
                }
            },
            Err(e) => {
                eprintln!("[ALETHEIA] Failed to create Job Object — sidecars may survive a hard kill: {e}");
                None
            }
        }
    };

    // Cloned before `.setup()` moves `shared_state` — `.on_window_event()` is
    // a separate builder call further down the chain and needs its own handle.
    let state_for_window_close = Arc::clone(&shared_state);

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(shared_state.clone())
        .invoke_handler(tauri::generate_handler![
            get_desktop_settings,
            restart_sidecars,
            stop_sidecars,
        ])
        .setup(move |app| {
            // ---- Spawn sidecars on startup ----
            let res_dir = app.path().resource_dir().unwrap_or_default();
            let workspace = find_workspace_root(&res_dir);

            {
                let mut lock = shared_state.lock().unwrap();
                lock.engine = spawn_engine(&workspace);

                // Give the engine 500ms to bind its port before starting the API
                std::thread::sleep(std::time::Duration::from_millis(500));

                lock.api = spawn_api(&workspace);
            }

            // ---- Hold the window hidden until both sidecars answer their
            // health checks (or 30s elapses), so the user never sees a blank
            // "connection refused" UI on a slow-starting Python backend. ----
            {
                let app_handle = app.handle().clone();
                std::thread::spawn(move || {
                    let client = reqwest::blocking::Client::builder()
                        .timeout(std::time::Duration::from_secs(2))
                        .build()
                        .expect("failed to build health-check HTTP client");
                    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(30);

                    let engine_ok = wait_until_healthy(&client, "http://127.0.0.1:18899/health", deadline);
                    let api_ok = wait_until_healthy(&client, "http://127.0.0.1:8899/api/v1/health", deadline);

                    if !engine_ok {
                        eprintln!("[ALETHEIA] aletheia-engine did not become healthy within 30s");
                    }
                    if !api_ok {
                        eprintln!("[ALETHEIA] FastAPI backend did not become healthy within 30s");
                    }

                    if let Some(win) = app_handle.get_webview_window("main") {
                        let _ = win.show();
                    }
                });
            }

            // ---- System Tray ----
            let open_item = MenuItem::with_id(app, "open", "Open ALETHEIA", true, None::<&str>)?;
            let restart_item = MenuItem::with_id(app, "restart", "Restart Services", true, None::<&str>)?;
            let stop_item = MenuItem::with_id(app, "stop", "Stop Services", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;

            let menu = MenuBuilder::new(app)
                .item(&open_item)
                .separator()
                .item(&restart_item)
                .item(&stop_item)
                .separator()
                .item(&quit_item)
                .build()?;

            let _tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("ALETHEIA — Financial Intelligence")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event({
                    let app_handle = app.handle().clone();
                    let state_ref = Arc::clone(&shared_state);
                    move |_tray, event| match event.id().as_ref() {
                        "open" => {
                            if let Some(win) = app_handle.get_webview_window("main") {
                                let _ = win.show();
                                let _ = win.set_focus();
                            }
                        }
                        "restart" => {
                            let mut lock = state_ref.lock().unwrap();
                            lock.kill_all();
                            let res_dir = app_handle.path().resource_dir().unwrap_or_default();
                            let ws = find_workspace_root(&res_dir);
                            lock.engine = spawn_engine(&ws);
                            std::thread::sleep(std::time::Duration::from_millis(500));
                            lock.api = spawn_api(&ws);
                            let _ = app_handle.emit("services-restarted", ());
                        }
                        "stop" => {
                            let mut lock = state_ref.lock().unwrap();
                            lock.kill_all();
                            let _ = app_handle.emit("services-stopped", ());
                        }
                        "quit" => {
                            let mut lock = state_ref.lock().unwrap();
                            lock.kill_all();
                            app_handle.exit(0);
                        }
                        _ => {}
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if matches!(event, TrayIconEvent::Click { button: MouseButton::Left, .. }) {
                        if let Some(win) = tray.app_handle().get_webview_window("main") {
                            let _ = win.show();
                            let _ = win.set_focus();
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event({
            let state_for_close = state_for_window_close;
            move |_window, event| {
                if let tauri::WindowEvent::Destroyed = event {
                    // Kill sidecars when window is destroyed (quit)
                    let mut lock = state_for_close.lock().unwrap();
                    lock.kill_all();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running ALETHEIA desktop");
}
