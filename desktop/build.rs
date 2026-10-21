fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&["save_project_file", "open_project_file", "save_export_file", "pick_dataset_folder"])
    )).expect("Desktop build configuration failed");
}
