const { app, BrowserWindow, nativeImage, Tray, Menu } = require('electron');
const path = require('path');

// Default loads the Ember Chat page only (embedded=true hides sidebar in dashboard Layout).
// Override with EMBER_DASHBOARD_URL=http://localhost:3456/ to get the full dashboard.
const DASHBOARD_URL = process.env.EMBER_DASHBOARD_URL || 'http://localhost:3456/ember-chat?embedded=true';
const RETRY_INTERVAL_MS = 3000;
const APP_ICON_PATH = path.join(__dirname, 'icon-1024.png');

app.setName('Ember Chat');

// Single instance lock — prevent multiple windows
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
}

let mainWindow;
let tray = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 16, y: 16 },
    backgroundColor: '#141820',
    icon: APP_ICON_PATH,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });

  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription) => {
    console.warn(`[ember] did-fail-load (${errorCode}): ${errorDescription}. Retrying in ${RETRY_INTERVAL_MS}ms...`);
    setTimeout(loadDashboardWithRetry, RETRY_INTERVAL_MS);
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  loadDashboardWithRetry();
}

function loadDashboardWithRetry() {
  if (!mainWindow) return;

  mainWindow.loadURL(DASHBOARD_URL).catch((err) => {
    console.warn(`[ember] Failed to load ${DASHBOARD_URL}: ${err.message}. Retrying in ${RETRY_INTERVAL_MS}ms...`);
    setTimeout(loadDashboardWithRetry, RETRY_INTERVAL_MS);
  });
}

function createTray() {
  const iconPath = path.join(__dirname, 'icon.png');
  let img;
  try {
    img = nativeImage.createFromPath(iconPath).resize({ width: 18, height: 18 });
  } catch {
    img = nativeImage.createEmpty();
  }

  tray = new Tray(img);
  tray.setToolTip('Ember Chat');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show Window',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      },
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
