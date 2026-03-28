#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::path::PathBuf;
use tauri::{Manager, State, api::process::Command as TauriCommand};
use serde::{Serialize, Deserialize};

#[derive(Serialize)]
struct VideoInfo {
    name: String,
    path: String,
    size: u64,
    date: String,
}

#[derive(Deserialize)]
struct GenerateRequest {
    topic: String,
    duration: u32,
    style: String,
    theme: String,
    music: bool,
    images: bool,
    upload: bool,
}

struct AppState {
    process: Arc<Mutex<Option<std::process::Child>>>,
    project_root: PathBuf,
}

#[tauri::command]
async fn generate_video(
    request: GenerateRequest,
    state: State<'_, AppState>,
    window: tauri::Window,
) -> Result<String, String> {
    let project_root = state.project_root.clone();
    
    let mut args = vec![
        "pipeline.py".to_string(),
        "--topic".to_string(),
        request.topic,
        "--duration".to_string(),
        request.duration.to_string(),
        "--style".to_string(),
        request.style,
        "--theme".to_string(),
        request.theme,
    ];
    
    if request.music {
        args.push("--music".to_string());
    } else {
        args.push("--no-music".to_string());
    }
    
    if request.images {
        args.push("--images".to_string());
    } else {
        args.push("--no-images".to_string());
    }
    
    if request.upload {
        args.push("--upload".to_string());
    }
    
    // Get home directory for PYTHONPATH
    let home = std::env::var("HOME").unwrap_or_default();
    let pythonpath = format!("{}/.local/lib/python3.12/site-packages", home);
    
    let mut cmd = Command::new("python3")
        .args(&args)
        .current_dir(&project_root)
        .env("PYTHONPATH", pythonpath)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start process: {}", e))?;
    
    let stdout = cmd.stdout.take().unwrap();
    let stderr = cmd.stderr.take().unwrap();
    
    // Store process handle
    *state.process.lock().unwrap() = Some(cmd);
    
    // Read stdout
    let window_clone = window.clone();
    std::thread::spawn(move || {
        use std::io::{BufRead, BufReader};
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            if let Ok(line) = line {
                let _ = window_clone.emit("output", line);
            }
        }
    });
    
    // Read stderr
    let window_clone = window.clone();
    std::thread::spawn(move || {
        use std::io::{BufRead, BufReader};
        let reader = BufReader::new(stderr);
        for line in reader.lines() {
            if let Ok(line) = line {
                let _ = window_clone.emit("output", format!("ERROR: {}", line));
            }
        }
    });
    
    // Wait for completion
    let mut process = state.process.lock().unwrap();
    if let Some(mut p) = process.take() {
        let status = p.wait().map_err(|e| e.to_string())?;
        if status.success() {
            Ok("Video generated successfully".to_string())
        } else {
            Err("Generation failed".to_string())
        }
    } else {
        Err("Process not found".to_string())
    }
}

#[tauri::command]
fn stop_generation(state: State<'_, AppState>) -> Result<(), String> {
    let mut process = state.process.lock().unwrap();
    if let Some(mut p) = process.take() {
        let _ = p.kill();
    }
    Ok(())
}

#[tauri::command]
fn get_videos(state: State<'_, AppState>) -> Result<Vec<VideoInfo>, String> {
    let output_dir = state.project_root.join("output");
    let mut videos = Vec::new();
    
    if let Ok(entries) = std::fs::read_dir(&output_dir) {
        for entry in entries {
            if let Ok(entry) = entry {
                let path = entry.path();
                if path.extension().map(|e| e == "mp4").unwrap_or(false) {
                    if let Ok(metadata) = entry.metadata() {
                        if let Ok(modified) = metadata.modified() {
                            let name = path.file_name()
                                .and_then(|n| n.to_str())
                                .unwrap_or("unknown")
                                .to_string();
                            
                            let datetime: chrono::DateTime<chrono::Local> = modified.into();
                            videos.push(VideoInfo {
                                name: name.clone(),
                                path: path.to_string_lossy().to_string(),
                                size: metadata.len(),
                                date: datetime.format("%Y-%m-%d %H:%M").to_string(),
                            });
                        }
                    }
                }
            }
        }
    }
    
    videos.sort_by(|a, b| b.date.cmp(&a.date));
    Ok(videos)
}

#[tauri::command]
fn open_video(path: String) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    {
        std::process::Command::new("xdg-open")
            .arg(&path)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(&path)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("cmd")
            .args(&["/c", "start", "", &path])
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn main() {
    // Get project root (parent of tauri-app directory)
    let project_root = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|p| p.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."));
    
    // Go up one level from tauri-app
    let project_root = project_root.parent()
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| PathBuf::from("."));
    
    tauri::Builder::default()
        .manage(AppState {
            process: Arc::new(Mutex::new(None)),
            project_root,
        })
        .invoke_handler(tauri::generate_handler![
            generate_video,
            stop_generation,
            get_videos,
            open_video
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
