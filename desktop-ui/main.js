const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

let mainWindow;
let pythonProcess = null;

// Get project root (parent of desktop-ui folder)
const PROJECT_ROOT = path.dirname(__dirname);

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    },
    titleBarStyle: 'hiddenInset',
    show: false
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
    if (pythonProcess) {
      pythonProcess.kill();
    }
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// IPC handlers
ipcMain.handle('generate-video', async (event, data) => {
  return new Promise((resolve, reject) => {
    const args = [
      path.join(PROJECT_ROOT, 'pipeline.py'),
      '--topic', data.topic,
      '--duration', data.duration.toString(),
      '--style', data.style,
      '--theme', data.theme
    ];

    if (data.music) args.push('--music');
    else args.push('--no-music');
    
    if (data.images) args.push('--images');
    else args.push('--no-images');
    
    if (data.upload) args.push('--upload');

    const env = { ...process.env };
    env.PYTHONPATH = path.join(require('os').homedir(), '.local/lib/python3.12/site-packages');

    pythonProcess = spawn('python3', args, {
      cwd: PROJECT_ROOT,
      env: env
    });

    let output = '';
    let errorOutput = '';

    pythonProcess.stdout.on('data', (data) => {
      const text = data.toString();
      output += text;
      mainWindow.webContents.send('output', text);
    });

    pythonProcess.stderr.on('data', (data) => {
      const text = data.toString();
      errorOutput += text;
      mainWindow.webContents.send('output', text);
    });

    pythonProcess.on('close', (code) => {
      pythonProcess = null;
      if (code === 0) {
        resolve({ success: true, output });
      } else {
        reject({ success: false, error: errorOutput || output });
      }
    });

    pythonProcess.on('error', (err) => {
      pythonProcess = null;
      reject({ success: false, error: err.message });
    });
  });
});

ipcMain.handle('stop-generation', () => {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
    return true;
  }
  return false;
});

ipcMain.handle('get-videos', async () => {
  const outputDir = path.join(PROJECT_ROOT, 'output');
  try {
    const files = fs.readdirSync(outputDir);
    const videos = files
      .filter(f => f.endsWith('.mp4'))
      .map(f => {
        const stat = fs.statSync(path.join(outputDir, f));
        return {
          name: f,
          path: path.join(outputDir, f),
          size: stat.size,
          date: stat.mtime
        };
      })
      .sort((a, b) => b.date - a.date);
    return videos;
  } catch (e) {
    return [];
  }
});

ipcMain.handle('open-video', async (event, videoPath) => {
  require('electron').shell.openPath(videoPath);
});

ipcMain.handle('select-output-dir', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  return result.filePaths[0];
});
