const { app, BrowserWindow, ipcMain, nativeImage, Tray, Menu } = require('electron');
const path = require('path');
const fs = require('fs');
const { exec } = require('child_process');

const VOICE_CHAT_HOST = 'localhost';
const VOICE_CHAT_PORT = 8767;
const AUDIO_FIXTURE_INCOMING_DIR = path.resolve(__dirname, '../voice_chat/tests/fixtures/audio/incoming');

const APP_ICON_PATH = path.join(__dirname, 'icon-1024.png');
app.setName('Ember Chat');

// Single instance lock — prevent multiple windows
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
}

// Dock icon is set in app.whenReady() below

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

function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) fs.mkdirSync(dirPath, { recursive: true });
}

function sanitizeFixtureBaseName(raw) {
  const value = String(raw || '').trim();
  if (!/^[a-z0-9_]+(?:__[a-z0-9_]+){2}$/.test(value)) throw new Error('Invalid fixture base name');
  return value;
}

function sanitizeFixtureId(raw) {
  const value = String(raw || '').trim();
  if (!/^[a-z0-9_]+$/.test(value)) throw new Error('Invalid fixture id');
  return value;
}

ipcMain.handle('save-incoming-audio-fixture', async (_event, payload) => {
  const baseName = sanitizeFixtureBaseName(payload?.baseName);
  const previousBaseName = payload?.previousBaseName ? sanitizeFixtureBaseName(payload.previousBaseName) : null;
  ensureDir(AUDIO_FIXTURE_INCOMING_DIR);

  if (previousBaseName && previousBaseName !== baseName) {
    try { fs.unlinkSync(path.join(AUDIO_FIXTURE_INCOMING_DIR, `${previousBaseName}.wav`)); } catch {}
    try { fs.unlinkSync(path.join(AUDIO_FIXTURE_INCOMING_DIR, `${previousBaseName}.json`)); } catch {}
  }

  const sidecar = payload?.sidecar || {};
  const normalized = {
    category: String(sidecar.category || ''),
    scene: String(sidecar.scene || ''),
    variant: String(sidecar.variant || ''),
    id: sanitizeFixtureId(sidecar.id || `${sidecar.category}_${sidecar.scene}_${sidecar.variant}`),
    transcript: String(sidecar.transcript || ''),
    expected_source: String(sidecar.expected_source || ''),
    expected_intervention: String(sidecar.expected_intervention || ''),
    notes: String(sidecar.notes || ''),
  };

  const wavPath = path.join(AUDIO_FIXTURE_INCOMING_DIR, `${baseName}.wav`);
  const jsonPath = path.join(AUDIO_FIXTURE_INCOMING_DIR, `${baseName}.json`);
  fs.writeFileSync(wavPath, Buffer.from(payload.wavBuffer || []));
  fs.writeFileSync(jsonPath, JSON.stringify(normalized, null, 2) + '\n', 'utf8');
  return { ok: true, saved: { wav: wavPath, json: jsonPath } };
});

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
