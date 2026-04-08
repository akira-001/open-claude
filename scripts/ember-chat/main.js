const { app, BrowserWindow, ipcMain, nativeImage, Tray, Menu } = require('electron');
const path = require('path');
const fs = require('fs');
const { exec } = require('child_process');

const VOICE_CHAT_HOST = 'localhost';
const VOICE_CHAT_PORT = 8767;

const APP_ICON_PATH = path.join(__dirname, 'icon-1024.png');
app.setName('Ember Chat');

// Single instance lock — prevent multiple windows
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
}

// Set Dock icon explicitly with high-res image
if (app.dock) {
  const dockIcon = nativeImage.createFromPath(APP_ICON_PATH);
  app.dock.setIcon(dockIcon);
}

let mainWindow;
let tray = null;
let alwaysOnListening = false;
const CONSENT_FILE = path.join(app.getPath('userData'), 'always-on-consent.json');

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

  // Forward renderer console.log to main process stdout for debugging
  mainWindow.webContents.on('console-message', (_event, level, message) => {
    if (message.includes('AlwaysOn')) {
      console.log(`[renderer] ${message}`);
    }
  });

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

// --- Always-On consent ---
ipcMain.handle('check-consent', () => {
  try {
    const data = JSON.parse(fs.readFileSync(CONSENT_FILE, 'utf8'));
    return !!data.consented;
  } catch { return false; }
});

ipcMain.handle('save-consent', () => {
  fs.writeFileSync(CONSENT_FILE, JSON.stringify({ consented: true, at: new Date().toISOString() }));
  return true;
});

// --- Always-On state from renderer ---
ipcMain.on('always-on-set', (_event, listening) => {
  alwaysOnListening = listening;
  updateTrayIcon();
});

function updateTrayIcon() {
  if (!tray) return;
  const iconName = alwaysOnListening ? 'listening.png' : 'muted.png';
  const iconPath = path.join(__dirname, 'tray-icons', iconName);
  try {
    const img = nativeImage.createFromPath(iconPath);
    tray.setImage(img.resize({ width: 18, height: 18 }));
  } catch (err) {
    console.error('[Tray] Failed to update icon:', err);
  }
}

function createTray() {
  const iconPath = path.join(__dirname, 'tray-icons', 'muted.png');
  const img = nativeImage.createFromPath(iconPath);
  tray = new Tray(img.resize({ width: 18, height: 18 }));
  tray.setToolTip('Ember Chat');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Toggle Always-On',
      click: () => {
        alwaysOnListening = !alwaysOnListening;
        updateTrayIcon();
        if (mainWindow) mainWindow.webContents.send('always-on-toggle', alwaysOnListening);
      },
    },
    { type: 'separator' },
    {
      label: 'Show Window',
      click: () => { if (mainWindow) { mainWindow.show(); mainWindow.focus(); } },
    },
    { type: 'separator' },
    { label: 'Quit', click: () => app.quit() },
  ]);
  tray.setContextMenu(contextMenu);
}

app.on('second-instance', () => {
  // Focus existing window when second instance is launched
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

app.whenReady().then(() => {
  try {
    app.dock.setIcon(nativeImage.createFromPath(APP_ICON_PATH));
  } catch {}
  createWindow();
  createTray();
});

app.on('window-all-closed', () => {
  app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
