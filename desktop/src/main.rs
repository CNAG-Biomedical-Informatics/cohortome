use std::{io::{BufRead, BufReader}, process::{Child, Command, Stdio}, sync::Mutex};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder, menu::{Menu, MenuItem, Submenu, PredefinedMenuItem}};
use tauri_plugin_dialog::DialogExt;
use std::io::{Read, Write};

fn browser_link_allowed(target: &tauri::Url, backend: &tauri::Url) -> bool {
    matches!(target.scheme(), "https" | "http")
        && target.host_str().is_some()
        && target.username().is_empty() && target.password().is_none()
        && target.origin() != backend.origin()
}

fn open_browser(app: &tauri::AppHandle, url: &str) {
    // Pass the URL as an argument, never through a command shell.
    #[cfg(target_os = "linux")]
    let result = Command::new("xdg-open").arg(url).spawn();
    #[cfg(target_os = "macos")]
    let result = Command::new("open").arg(url).spawn();
    #[cfg(target_os = "windows")]
    let result = Command::new("rundll32").args(["url.dll,FileProtocolHandler", url]).spawn();
    match result {
        Ok(mut child) => {
            let app = app.clone();
            std::thread::spawn(move || {
                if !child.wait().map(|status| status.success()).unwrap_or(false) {
                    app.dialog().message("Could not open your default browser. Check your system browser settings.").show(|_| {});
                }
            });
        }
        Err(_) => { app.dialog().message("Could not open your default browser. Check your system browser settings.").show(|_| {}); }
    }
}

#[tauri::command]
async fn pick_dataset_folder(app: tauri::AppHandle) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let Some(folder) = app.dialog().file().blocking_pick_folder() else { return Ok(None); };
        let path = folder.into_path().map_err(|e| e.to_string())?;
        Ok(Some(path.to_string_lossy().into_owned()))
    }).await.map_err(|e| e.to_string())?
}

#[tauri::command]
async fn save_export_file(app: tauri::AppHandle, request: tauri::ipc::Request<'_>) -> Result<bool, String> {
    let filename = request.headers().get("x-cohortome-filename")
        .and_then(|value| value.to_str().ok()).ok_or("Missing export filename")?.to_owned();
    if filename.len() > 120 || filename.starts_with('.')
        || !filename.bytes().all(|ch| ch.is_ascii_alphanumeric() || b"-_.".contains(&ch)) {
        return Err("Invalid export filename".into());
    }
    let extension = std::path::Path::new(&filename).extension()
        .and_then(|value| value.to_str()).ok_or("Missing file extension")?.to_owned();
    if !["zip", "tsv", "csv", "json"].contains(&extension.as_str()) {
        return Err("Unsupported export format".into());
    }
    let bytes = match request.body() {
        tauri::ipc::InvokeBody::Raw(bytes) if bytes.len() <= 32 * 1024 * 1024 => bytes.clone(),
        _ => return Err("Expected a binary export up to 32 MiB".into()),
    };
    tauri::async_runtime::spawn_blocking(move || {
        let Some(file) = app.dialog().file().add_filter("Export file", &[extension.as_str()])
            .set_file_name(&filename).blocking_save_file() else { return Ok(false); };
        let mut path = file.into_path().map_err(|e| e.to_string())?;
        if path.extension().is_none() { path.set_extension(&extension); }
        if path.extension().and_then(|value| value.to_str()) != Some(extension.as_str()) || path.is_symlink() {
            return Err(format!("Choose a regular .{} file", extension));
        }
        let mut temporary = tempfile::NamedTempFile::new_in(path.parent().ok_or("Invalid destination")?).map_err(|e| e.to_string())?;
        temporary.write_all(&bytes).and_then(|_| temporary.as_file().sync_all()).map_err(|e| e.to_string())?;
        temporary.persist(path).map_err(|e| e.to_string())?;
        Ok(true)
    }).await.map_err(|e| e.to_string())?
}

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
        .invoke_handler(tauri::generate_handler![save_project_file, open_project_file, save_export_file, pick_dataset_folder])
        .setup(|app| {
            let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
            let executable = std::env::current_exe()?;
            let backend_name = if cfg!(windows) { "cohortome-backend.exe" } else { "cohortome-backend" };
            let portable = executable.parent().unwrap().join("engine").join(backend_name);
            let packaged = if portable.is_file() { Some(portable) } else {
                app.path().resource_dir().ok()
                    .map(|path| path.join("engine").join(backend_name))
                    .filter(|path| path.is_file())
            };
            let mut command = if let Some(backend) = packaged {
                let mut command = Command::new(backend);
                command.arg("--runtime-dir").arg(app.path().app_local_data_dir()?);
                command
            } else if cfg!(debug_assertions) {
                let python = std::env::var("COHORTOME_DESKTOP_PYTHON").unwrap_or_else(|_| "python3".into());
                let mut command = Command::new(python);
                command.arg(root.join("desktop/server.py")).current_dir(root);
                command
            } else {
                return Err("Packaged COHORTome backend is missing. Reinstall the application.".into());
            };
            command.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::inherit());
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
            // Only this launched backend may invoke native file dialogs.
            app.add_capability(serde_json::json!({
                "identifier": "project-dialogs", "windows": ["main"], "local": false,
                "remote": {"urls": [format!("{}/*", origin.ascii_serialization())]},
                "permissions": ["allow-save-project-file", "allow-open-project-file", "allow-save-export-file", "allow-pick-dataset-folder"]
            }).to_string())?;
            app.manage(engine);
            let smoke = std::env::var("COHORTOME_DESKTOP_SMOKE_TEST").as_deref() == Ok("1");
            let link_app = app.handle().clone();
            let backend_url = url.clone();
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
                .initialization_script("window.__COHORTOME_DESKTOP__ = true; document.addEventListener('contextmenu', event => event.preventDefault());")
                .devtools(false)
                .title("COHORTome — Desktop Preview")
                .inner_size(1440.0, 960.0).min_inner_size(800.0, 600.0)
                .on_navigation(move |target| target.origin() == origin)
                .on_new_window(move |target, _| {
                    if browser_link_allowed(&target, &backend_url) {
                        open_browser(&link_app, target.as_str());
                    }
                    tauri::webview::NewWindowResponse::Deny
                })
                .on_page_load(move |window, payload| {
                    if smoke && payload.url().path() == "/"
                        && matches!(payload.event(), tauri::webview::PageLoadEvent::Finished) {
                        let handle = window.app_handle().clone();
                        std::thread::spawn(move || {
                            std::thread::sleep(std::time::Duration::from_secs(2));
                            println!("PASS: packaged native window loaded");
                            handle.exit(0);
                        });
                    }
                })
                .build()?;
            let file = Submenu::with_items(app, "File", true, &[
                &MenuItem::with_id(app, "newQueryChatBtn", "New Query Chat", true, None::<&str>)?,
                &MenuItem::with_id(app, "newAnalysisChatBtn", "New Analysis Chat", true, None::<&str>)?,
                &MenuItem::with_id(app, "newPhenoChatBtn", "New Pheno-Ranker Chat", true, None::<&str>)?,
                &PredefinedMenuItem::separator(app)?,
                &MenuItem::with_id(app, "openProjectBtn", "Open Project…", true, Some("CmdOrCtrl+O"))?,
                &MenuItem::with_id(app, "saveProjectBtn", "Save Project As…", true, Some("CmdOrCtrl+Shift+S"))?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::quit(app, None)?,
            ])?;
            let view = Submenu::new(app, "View", true)?;
            view.append(&MenuItem::with_id(app, "reload", "Reload", true, Some("CmdOrCtrl+R"))?)?;
            view.append(&PredefinedMenuItem::separator(app)?)?;
            for (id, label, shortcut) in [
                ("dashboardTabBtn", "Dashboard", "CmdOrCtrl+1"),
                ("queryTabBtn", "Query", "CmdOrCtrl+2"),
                ("analysisTabBtn", "Analysis", "CmdOrCtrl+3"),
                ("phenoTabBtn", "Pheno-Ranker", "CmdOrCtrl+4"),
            ] {
                view.append(&MenuItem::with_id(app, id, label, true, Some(shortcut))?)?;
            }
            let dashboard = Submenu::new(app, "Dashboard Sections", true)?;
            for (id, label) in [
                ("dashboardClinicalBtn", "Clinical"), ("dashboardPatientsBtn", "Patients"),
                ("dashboardTimelineBtn", "Timeline"), ("dashboardAssaysBtn", "Assays"),
                ("dashboardImagingBtn", "Imaging"), ("dashboardMultimodalBtn", "Multimodal"),
            ] {
                dashboard.append(&MenuItem::with_id(app, id, label, true, None::<&str>)?)?;
            }
            view.append(&dashboard)?;
            view.append(&PredefinedMenuItem::separator(app)?)?;
            for (id, label) in [
                ("datasetsTabBtn", "Datasets"), ("cohortsTabBtn", "Cohorts"),
                ("analysisChatsDrawerBtn", "Chats"), ("jobsDrawerBtn", "Jobs"),
                ("runHistoryDrawerBtn", "Run History"),
            ] {
                view.append(&MenuItem::with_id(app, id, label, true, None::<&str>)?)?;
            }
            let edit = Submenu::with_items(app, "Edit", true, &[
                &PredefinedMenuItem::undo(app, None)?, &PredefinedMenuItem::redo(app, None)?,
                &PredefinedMenuItem::separator(app)?, &PredefinedMenuItem::cut(app, None)?,
                &PredefinedMenuItem::copy(app, None)?, &PredefinedMenuItem::paste(app, None)?,
                &PredefinedMenuItem::select_all(app, None)?,
            ])?;
            let tools = Submenu::with_items(app, "Tools", true, &[
                &MenuItem::with_id(app, "userSettingsBtn", "Settings…", true, Some("CmdOrCtrl+,"))?,
                &MenuItem::with_id(app, "modelsTabBtn", "Model Configuration", true, None::<&str>)?,
            ])?;
            let help = Submenu::with_items(app, "Help", true, &[
                &MenuItem::with_id(app, "documentation", "Documentation (Online)", true, None::<&str>)?,
                &MenuItem::with_id(app, "journeys", "User Journeys (Online)", true, None::<&str>)?,
                &PredefinedMenuItem::separator(app)?,
                &MenuItem::with_id(app, "about", "About COHORTome", true, None::<&str>)?,
            ])?;
            app.set_menu(Menu::with_items(app, &[&file, &edit, &view, &tools, &help])?)?;
            Ok(())
        })
        .on_menu_event(|app, event| {
            let id = event.id().as_ref();
            if let Some(script) = menu_script(id) {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.eval(&script);
                }
            } else if let Some(url) = help_url(id) {
                open_browser(app, url);
            }
        })
        .build(tauri::generate_context!()).expect("COHORTome desktop could not start");
    app.run(|app, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(engine) = app.try_state::<Engine>() { engine.stop(); }
        }
    });
}

fn help_url(id: &str) -> Option<&'static str> {
    match id {
        "documentation" => Some("https://mrueda.github.io/cohortome/"),
        "journeys" => Some("https://mrueda.github.io/cohortome/docs/user-guide/user-journeys"),
        _ => None,
    }
}

fn menu_script(id: &str) -> Option<String> {
    if id == "reload" {
        return Some("window.location.reload()".into());
    }
    if id == "about" {
        return Some("(() => { if(document.getElementById('userSettingsPanel')?.classList.contains('is-hidden')) document.getElementById('userSettingsBtn')?.click(); document.querySelector('[data-settings-section=about]')?.click(); const about=document.getElementById('settingsAbout'); if(about){about.open=true; about.scrollIntoView({block:'nearest'});} })()".into());
    }
    if ["dashboardClinicalBtn", "dashboardPatientsBtn", "dashboardTimelineBtn", "dashboardAssaysBtn", "dashboardImagingBtn", "dashboardMultimodalBtn"].contains(&id) {
        return Some(format!("if(!document.getElementById('dashboardTab')?.classList.contains('active')) document.getElementById('dashboardTabBtn')?.click(); document.getElementById('{}')?.click()", id));
    }
    if ["newQueryChatBtn", "newAnalysisChatBtn", "newPhenoChatBtn", "openProjectBtn", "saveProjectBtn",
        "datasetsTabBtn", "cohortsTabBtn", "userSettingsBtn", "modelsTabBtn", "dashboardTabBtn",
        "queryTabBtn", "analysisTabBtn", "phenoTabBtn", "analysisChatsDrawerBtn", "jobsDrawerBtn", "runHistoryDrawerBtn"].contains(&id) {
        return Some(format!("document.getElementById('{}')?.click()", id));
    }
    None
}

#[cfg(test)]
mod menu_tests {
    use super::*;
    #[test]
    fn external_browser_links_exclude_backend_and_non_web_schemes() {
        let backend: tauri::Url = "http://127.0.0.1:8001/".parse().unwrap();
        assert!(browser_link_allowed(&"https://www.ensembl.org/Homo_sapiens/Gene/Summary?g=ENSG00000141510".parse().unwrap(), &backend));
        for target in ["http://127.0.0.1:8001/private", "file:///tmp/example", "javascript:alert(1)",
            "mailto:example@example.org", "https://user:password@example.org/"] {
            assert!(!browser_link_allowed(&target.parse().unwrap(), &backend));
        }
    }
    #[test]
    fn menu_routes_only_known_actions() {
        assert_eq!(menu_script("reload").as_deref(), Some("window.location.reload()"));
        assert!(menu_script("newPhenoChatBtn").unwrap().contains(".click()"));
        assert!(menu_script("cohortsTabBtn").is_some());
        assert!(menu_script("dashboardImagingBtn").unwrap().contains("dashboardTabBtn"));
        assert!(menu_script("about").unwrap().contains("about.open=true"));
        assert!(menu_script("arbitrary-input").is_none());
        assert!(help_url("arbitrary-input").is_none());
    }
}
