const { app, BrowserWindow, ipcMain, nativeImage } = require('electron');
const path = require('path');
const { exec } = require('child_process');

const VOICE_CHAT_HOST = 'localhost';
const VOICE_CHAT_PORT = 8767;

const APP_ICON_PATH = path.join(__dirname, 'icon-1024.png');
app.setName('Ember Chat');

// Set Dock icon explicitly with high-res image
if (app.dock) {
  const dockIcon = nativeImage.createFromPath(APP_ICON_PATH);
  app.dock.setIcon(dockIcon);
}

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 480,
    height: 820,
    minWidth: 380,
    minHeight: 600,
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 16, y: 16 },
    backgroundColor: '#141820',
    icon: APP_ICON_PATH,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
      webSecurity: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

let _afplayProc = null;

ipcMain.handle('play-audio-native', async (_event, wavBuffer) => {
  const tmpFile = path.join(require('os').tmpdir(), `ember-audio-${Date.now()}.wav`);
  require('fs').writeFileSync(tmpFile, Buffer.from(wavBuffer));
  return new Promise((resolve) => {
    _afplayProc = exec(`afplay "${tmpFile}"`, (err) => {
      _afplayProc = null;
      try { require('fs').unlinkSync(tmpFile); } catch {}
      resolve(!err);
    });
  });
});

ipcMain.handle('stop-audio-native', async () => {
  if (_afplayProc) { _afplayProc.kill(); _afplayProc = null; }
  exec('killall afplay 2>/dev/null');
  return true;
});

ipcMain.handle('get-config', () => ({
  host: VOICE_CHAT_HOST,
  port: VOICE_CHAT_PORT,
}));

app.whenReady().then(() => {
  try {
    app.dock.setIcon(nativeImage.createFromPath(APP_ICON_PATH));
  } catch {}
  createWindow();
});

app.on('window-all-closed', () => {
  app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
