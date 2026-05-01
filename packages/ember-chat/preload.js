const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('emberBridge', {
  playAudioNative: (wavBase64) => ipcRenderer.invoke('play-audio-native', wavBase64),
  stopAudioNative: () => ipcRenderer.invoke('stop-audio-native'),
  getConfig: () => ipcRenderer.invoke('get-config'),
  saveIncomingAudioFixture: (payload) => ipcRenderer.invoke('save-incoming-audio-fixture', payload),
  setAlwaysOn: (listening) => ipcRenderer.send('always-on-set', listening),
  onAlwaysOnToggle: (callback) => ipcRenderer.on('always-on-toggle', (_e, val) => callback(val)),
  checkConsent: () => ipcRenderer.invoke('check-consent'),
  saveConsent: () => ipcRenderer.invoke('save-consent'),
  saveRecordingAudio: (payload) => ipcRenderer.invoke('save-recording-audio', payload),
  saveRecordingText: (payload) => ipcRenderer.invoke('save-recording-text', payload),
  openRecordingsFolder: () => ipcRenderer.invoke('open-recordings-folder'),
});
