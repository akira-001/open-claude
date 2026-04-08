/**
 * Always-On Listening Module for Ember Chat
 *
 * States: idle -> listening -> detected -> processing -> listening (loop)
 *         idle -> muted (user toggle)
 *
 * Uses @ricky0123/vad-web (Silero VAD ONNX) if available,
 * falls back to RMS-based voice activity detection.
 */

class AlwaysOnListener {
  constructor({ wsSend, wsRef, onStateChange, onWakeDetected, playAudio, addMessage }) {
    this.wsSend = wsSend;
    this.wsRef = wsRef;
    this.onStateChange = onStateChange;
    this.onWakeDetected = onWakeDetected;
    this.playAudio = playAudio;
    this.addMessage = addMessage;

    this.state = 'idle';
    this.micStream = null;
    this.vad = null;
    this.enabled = false;
    this._processingTimeout = null;
    this._rmsCleanup = null;
  }

  async start() {
    if (this.state !== 'idle' && this.state !== 'muted') return;

    try {
      this.micStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true }
      });
    } catch (err) {
      console.error('[AlwaysOn] Mic access denied:', err);
      return;
    }

    try {
      await this._initSileroVAD();
    } catch (err) {
      console.warn('[AlwaysOn] Silero VAD failed, using RMS fallback:', err);
      this._initRMSVAD();
    }

    this.enabled = true;
    this._setState('listening');
  }

  async _initSileroVAD() {
    const { MicVAD } = await import('@ricky0123/vad-web');
    this.vad = await MicVAD.new({
      stream: this.micStream,
      onSpeechStart: () => {
        if (this.state !== 'listening') return;
        this._setState('detected');
      },
      onSpeechEnd: (audio) => {
        if (this.state !== 'detected') return;
        this._handleSpeechSegment(audio);
      },
      positiveSpeechThreshold: 0.8,
      negativeSpeechThreshold: 0.3,
      minSpeechFrames: 5,
      preSpeechPadFrames: 10,
      redemptionFrames: 8,
    });
    this.vad.start();
  }

  _initRMSVAD() {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioCtx.createMediaStreamSource(this.micStream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);

    const dataArray = new Float32Array(analyser.fftSize);
    let speechStart = null;
    let recorder = null;
    let chunks = [];
    const THRESHOLD = 0.015;
    const MIN_SPEECH_MS = 500;
    const SILENCE_TIMEOUT_MS = 800;
    let silenceTimer = null;

    const check = () => {
      if (!this.enabled) return;
      analyser.getFloatTimeDomainData(dataArray);
      let rms = 0;
      for (let i = 0; i < dataArray.length; i++) rms += dataArray[i] * dataArray[i];
      rms = Math.sqrt(rms / dataArray.length);

      if (rms > THRESHOLD) {
        if (!speechStart && this.state === 'listening') {
          speechStart = Date.now();
          this._setState('detected');
          chunks = [];
          recorder = new MediaRecorder(this.micStream, { mimeType: 'audio/webm;codecs=opus' });
          recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
          recorder.onstop = async () => {
            const blob = new Blob(chunks, { type: 'audio/webm' });
            const buf = await blob.arrayBuffer();
            this._handleSpeechSegmentWebm(buf);
          };
          recorder.start();
        }
        if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
      } else if (speechStart) {
        if (!silenceTimer) {
          silenceTimer = setTimeout(() => {
            if (Date.now() - speechStart >= MIN_SPEECH_MS && recorder && recorder.state === 'recording') {
              recorder.stop();
            } else if (recorder && recorder.state === 'recording') {
              recorder.stop();
              this._setState('listening');
            }
            speechStart = null;
            silenceTimer = null;
          }, SILENCE_TIMEOUT_MS);
        }
      }
      requestAnimationFrame(check);
    };
    requestAnimationFrame(check);

    this._rmsCleanup = () => {
      this.enabled = false;
      audioCtx.close();
    };
  }

  async _handleSpeechSegment(audioFloat32) {
    this._setState('processing');
    const wavBuffer = this._float32ToWav(audioFloat32, 16000);
    this._sendAlwaysOnAudio(wavBuffer);
  }

  async _handleSpeechSegmentWebm(webmBuffer) {
    this._setState('processing');
    this._sendAlwaysOnAudio(webmBuffer);
  }

  _sendAlwaysOnAudio(audioBuffer) {
    const ws = this.wsRef();
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      this._setState('listening');
      return;
    }
    ws.send(JSON.stringify({ type: 'always_on_audio', format: 'wav' }));
    ws.send(audioBuffer);

    if (this._processingTimeout) clearTimeout(this._processingTimeout);
    this._processingTimeout = setTimeout(() => {
      if (this.state === 'processing') this._setState('listening');
    }, 10000);
  }

  handleServerMessage(msg) {
    if (msg.type === 'wake_detected') {
      if (this._processingTimeout) { clearTimeout(this._processingTimeout); this._processingTimeout = null; }
      this.onWakeDetected(msg);
      setTimeout(() => {
        if (this.state === 'processing') this._setState('listening');
      }, 3000);
    } else if (msg.type === 'always_on_result' && !msg.wake) {
      if (this._processingTimeout) { clearTimeout(this._processingTimeout); this._processingTimeout = null; }
      this._setState('listening');
    }
  }

  returnToListening() {
    if (this.state === 'processing') this._setState('listening');
  }

  stop() {
    if (this.vad) this.vad.pause();
    if (this._rmsCleanup) this._rmsCleanup();
    this.enabled = false;
    this._setState('muted');
  }

  toggle() {
    if (this.enabled) {
      this.stop();
    } else {
      this.start();
    }
    return this.enabled;
  }

  _setState(newState) {
    const prev = this.state;
    this.state = newState;
    if (prev !== newState) {
      console.log(`[AlwaysOn] ${prev} -> ${newState}`);
      this.onStateChange(newState);
    }
  }

  _float32ToWav(float32Array, sampleRate) {
    const numSamples = float32Array.length;
    const buffer = new ArrayBuffer(44 + numSamples * 2);
    const view = new DataView(buffer);
    const writeStr = (off, s) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };
    writeStr(0, 'RIFF');
    view.setUint32(4, 36 + numSamples * 2, true);
    writeStr(8, 'WAVE');
    writeStr(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, 'data');
    view.setUint32(40, numSamples * 2, true);
    for (let i = 0; i < numSamples; i++) {
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return buffer;
  }

  destroy() {
    if (this.vad) { this.vad.destroy(); this.vad = null; }
    if (this._rmsCleanup) this._rmsCleanup();
    if (this.micStream) { this.micStream.getTracks().forEach(t => t.stop()); this.micStream = null; }
    this.enabled = false;
    this._setState('idle');
  }
}

window.AlwaysOnListener = AlwaysOnListener;
