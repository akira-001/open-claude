const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('emberBridge', {
  playAudioNative: (wavBase64) => ipcRenderer.invoke('play-audio-native', wavBase64),
  stopAudioNative: () => ipcRenderer.invoke('stop-audio-native'),
  getConfig: () => ipcRenderer.invoke('get-config'),
});
