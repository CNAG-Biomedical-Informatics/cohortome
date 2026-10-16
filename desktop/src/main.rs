use std::{io::{BufRead, BufReader}, process::{Child, Command, Stdio}, sync::Mutex};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder, menu::{Menu, MenuItem, Submenu, PredefinedMenuItem}};
use tauri_plugin_dialog::DialogExt;
use std::io::{Read, Write};

#[tauri::command]
async fn save_project_file(app: tauri::AppHandle, text: String) -> Result<bool, String> {
    if text.len() > 1024 * 1024 { return Err("Project exceeds 1 MiB".into()); }
    let value: serde_json::Value = serde_json::from_str(&text).map_err(|_| "Invalid project JSON")?;
    if value["format"] != "cohortome-project" || value["version"] != 1 { return Err("Invalid project format".into()); }
    tauri::async_runtime::spawn_blocking(move || {
        let Some(file) = app.dialog().file().add_filter("COHORTome project", &["cohortome"])
            .set_file_name("project.cohortome").blocking_save_file() else { return Ok(false); };
        let path = file.into_path().map_err(|e| e.to_string())?;
        if path.extension().and_then(|s| s.to_str()) != Some("cohortome") || path.is_symlink() {
            return Err("Choose a regular .cohortome file".into());
        }
        let mut temporary = tempfile::NamedTempFile::new_in(path.parent().ok_or("Invalid destination")?).map_err(|e| e.to_string())?;
        temporary.write_all(text.as_bytes()).and_then(|_| temporary.as_file().sync_all()).map_err(|e| e.to_string())?;
        temporary.persist(path).map_err(|e| e.to_string())?;
        Ok(true)
    }).await.map_err(|e| e.to_string())?
}

#[tauri::command]
async fn open_project_file(app: tauri::AppHandle) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let Some(file) = app.dialog().file().add_filter("COHORTome project", &["cohortome"])
            .blocking_pick_file() else { return Ok(None); };
        let path = file.into_path().map_err(|e| e.to_string())?;
        let file = std::fs::File::open(path).map_err(|e| e.to_string())?;
        if !file.metadata().map_err(|e| e.to_string())?.is_file() { return Err("Choose a regular file".into()); }
        let mut text = String::new();
        file.take(1024 * 1024 + 1).read_to_string(&mut text).map_err(|e| e.to_string())?;
        if text.len() > 1024 * 1024 { return Err("Project exceeds 1 MiB".into()); }
        Ok(Some(text))
    }).await.map_err(|e| e.to_string())?
}

struct Engine(Mutex<Option<Child>>);
impl Engine {
    fn stop(&self) {
        if let Some(mut child) = self.0.lock().unwrap().take() {
            drop(child.stdin.take());
            for _ in 0..50 {
                if child.try_wait().ok().flatten().is_some() { return; }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}
impl Drop for Engine { fn drop(&mut self) { self.stop(); } }

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![save_project_file, open_project_file])
        .setup(|app| {
            let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
            let python = std::env::var("COHORTOME_DESKTOP_PYTHON").unwrap_or_else(|_| "python3".into());
            let mut command = Command::new(python);
            command.arg(root.join("desktop/server.py")).current_dir(root)
                .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::inherit());
            let mut child = command.spawn()?;
            let stdout = child.stdout.take().unwrap();
            let engine = Engine(Mutex::new(Some(child)));
            let (tx, rx) = std::sync::mpsc::channel();
            std::thread::spawn(move || {
                let mut line = String::new();
                let result = BufReader::new(stdout).read_line(&mut line).map(|_| line);
                let _ = tx.send(result);
            });
            let line = rx.recv_timeout(std::time::Duration::from_secs(90))??;
            let ready: serde_json::Value = serde_json::from_str(&line)?;
            let url: tauri::Url = ready["url"].as_str().ok_or("Backend did not return a URL")?.parse()?;
            let origin = url.origin();
            // Only this launched backend may invoke the two native project dialogs.
            app.add_capability(serde_json::json!({
                "identifier": "project-dialogs", "windows": ["main"], "local": false,
                "remote": {"urls": [format!("{}/*", origin.ascii_serialization())]},
                "permissions": ["allow-save-project-file", "allow-open-project-file"]
            }).to_string())?;
            app.manage(engine);
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
                .initialization_script("window.__COHORTOME_DESKTOP__ = true;")
                .title("COHORTome — Desktop Preview")
                .inner_size(1440.0, 960.0).min_inner_size(800.0, 600.0)
                .on_navigation(move |target| target.origin() == origin)
                .build()?;
            let file = Submenu::with_items(app, "File", true, &[
                &MenuItem::with_id(app, "openProjectBtn", "Open Project…", true, Some("CmdOrCtrl+O"))?,
                &MenuItem::with_id(app, "saveProjectBtn", "Save Project As…", true, Some("CmdOrCtrl+Shift+S"))?,
                &MenuItem::with_id(app, "datasetsTabBtn", "Datasets", true, None::<&str>)?,
                &MenuItem::with_id(app, "userSettingsBtn", "Settings", true, Some("CmdOrCtrl+,"))?,
                &PredefinedMenuItem::quit(app, None)?,
            ])?;
            let view = Submenu::new(app, "View", true)?;
            for (id, label, shortcut) in [
                ("dashboardTabBtn", "Dashboard", "CmdOrCtrl+1"),
                ("queryTabBtn", "Query", "CmdOrCtrl+2"),
                ("analysisTabBtn", "Analysis", "CmdOrCtrl+3"),
                ("phenoTabBtn", "Pheno-Ranker", "CmdOrCtrl+4"),
            ] {
                view.append(&MenuItem::with_id(app, id, label, true, Some(shortcut))?)?;
            }
            let edit = Submenu::with_items(app, "Edit", true, &[
                &PredefinedMenuItem::copy(app, None)?, &PredefinedMenuItem::paste(app, None)?,
                &PredefinedMenuItem::select_all(app, None)?,
            ])?;
            app.set_menu(Menu::with_items(app, &[&file, &edit, &view])?)?;
            Ok(())
        })
        .on_menu_event(|app, event| {
            let id = event.id().as_ref();
            if ["openProjectBtn", "saveProjectBtn", "datasetsTabBtn", "userSettingsBtn", "dashboardTabBtn", "queryTabBtn", "analysisTabBtn", "phenoTabBtn"].contains(&id) {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.eval(&format!("document.getElementById('{}')?.click()", id));
                }
            }
        })
        .build(tauri::generate_context!()).expect("COHORTome desktop could not start");
    app.run(|app, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(engine) = app.try_state::<Engine>() { engine.stop(); }
        }
    });
}
