#!/usr/bin/env node
// Set up Ember Chat.app bundle in electron prebuilt dist.
//
// pnpm/npm runs this from the package root (process.cwd() === ember-chat dir),
// so we anchor paths off __dirname (this file lives in scripts/) for safety.
//
// Idempotent: safe to run on every install.

const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');
const { patchAppBundle } = require('./patch-mac-bundle');

const PACKAGE_ROOT = path.resolve(__dirname, '..');

let electronDir;
try {
  electronDir = path.dirname(require.resolve('electron/package.json', { paths: [PACKAGE_ROOT] }));
} catch (e) {
  console.warn('[postinstall] electron not resolvable, skipping:', e.message);
  process.exit(0);
}

const distDir = path.join(electronDir, 'dist');
const sourceApp = path.join(distDir, 'Electron.app');
const targetApp = path.join(distDir, 'Ember Chat.app');

// Recreate Ember Chat.app from Electron.app if missing or broken.
const targetMacOSDir = path.join(targetApp, 'Contents', 'MacOS');
if (!fs.existsSync(targetMacOSDir)) {
  if (!fs.existsSync(path.join(sourceApp, 'Contents', 'MacOS'))) {
    console.warn('[postinstall] Electron.app prebuilt missing, run electron install.js first');
    process.exit(0);
  }
  try {
    if (fs.existsSync(targetApp)) execSync(`rm -rf "${targetApp}"`);
    execSync(`cp -R "${sourceApp}" "${targetApp}"`);
    console.log('[postinstall] copied Electron.app → Ember Chat.app');
  } catch (e) {
    console.warn('[postinstall] failed to copy app bundle:', e.message);
    process.exit(0);
  }
}

// Symlink Resources/app → package root (absolute path so symlink survives Dock launches).
const appLink = path.join(targetApp, 'Contents', 'Resources', 'app');
try { fs.unlinkSync(appLink); } catch {}
try {
  fs.symlinkSync(PACKAGE_ROOT, appLink);
  console.log(`[postinstall] symlink: ${appLink} → ${PACKAGE_ROOT}`);
} catch (e) {
  console.warn('[postinstall] symlink failed:', e.message);
}

// Set CFBundleIdentifier so macOS treats this as a distinct app from Electron itself.
try {
  execSync(`defaults write "${path.join(targetApp, 'Contents', 'Info.plist')}" CFBundleIdentifier -string com.ember.chat`);
} catch (e) {
  console.warn('[postinstall] CFBundleIdentifier set failed:', e.message);
}

try {
  patchAppBundle(targetApp);
  console.log('[postinstall] patched Ember Chat.app names and icons');
} catch (e) {
  console.warn('[postinstall] app bundle patch failed:', e.message);
}
