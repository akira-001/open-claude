#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const PACKAGE_ROOT = path.resolve(__dirname, '..');
const ICON_SOURCE = path.join(PACKAGE_ROOT, 'AppIcon.icns');
const PRODUCT_NAME = 'Ember Chat';

function run(command, args) {
  execFileSync(command, args, { stdio: 'ignore' });
}

function setPlistValue(plistPath, key, value) {
  run('plutil', ['-replace', key, '-string', value, plistPath]);
}

function patchAppBundle(appPath) {
  if (!appPath || !fs.existsSync(appPath)) {
    throw new Error(`app bundle not found: ${appPath}`);
  }
  if (!fs.existsSync(ICON_SOURCE)) {
    throw new Error(`icon source not found: ${ICON_SOURCE}`);
  }

  const resourcesDir = path.join(appPath, 'Contents', 'Resources');
  fs.mkdirSync(resourcesDir, { recursive: true });
  fs.copyFileSync(ICON_SOURCE, path.join(resourcesDir, 'icon.icns'));

  const mainPlist = path.join(appPath, 'Contents', 'Info.plist');
  setPlistValue(mainPlist, 'CFBundleIconFile', 'icon.icns');
  setPlistValue(mainPlist, 'CFBundleName', PRODUCT_NAME);
  setPlistValue(mainPlist, 'CFBundleDisplayName', PRODUCT_NAME);

  const frameworksDir = path.join(appPath, 'Contents', 'Frameworks');
  if (!fs.existsSync(frameworksDir)) return;

  for (const entry of fs.readdirSync(frameworksDir)) {
    const isPackagedHelper = entry.startsWith(`${PRODUCT_NAME} Helper`) && entry.endsWith('.app');
    const isDevHelper = entry.startsWith('Electron Helper') && entry.endsWith('.app');
    if (!isPackagedHelper && !isDevHelper) continue;

    const helperPath = path.join(frameworksDir, entry);
    const helperResourcesDir = path.join(helperPath, 'Contents', 'Resources');
    const helperPlist = path.join(helperPath, 'Contents', 'Info.plist');
    const helperName = entry
      .slice(0, -'.app'.length)
      .replace(/^Electron Helper/, `${PRODUCT_NAME} Helper`);

    fs.mkdirSync(helperResourcesDir, { recursive: true });
    fs.copyFileSync(ICON_SOURCE, path.join(helperResourcesDir, 'icon.icns'));
    setPlistValue(helperPlist, 'CFBundleIconFile', 'icon.icns');
    setPlistValue(helperPlist, 'CFBundleName', helperName);
    setPlistValue(helperPlist, 'CFBundleDisplayName', helperName);
  }
}

async function afterPack(context) {
  if (context.electronPlatformName !== 'darwin') return;
  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  patchAppBundle(appPath);
}

module.exports = afterPack;
module.exports.patchAppBundle = patchAppBundle;

if (require.main === module) {
  patchAppBundle(process.argv[2]);
}
