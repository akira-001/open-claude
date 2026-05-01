/**
 * Always-On Listening Module for Ember Chat
 *
 * States: idle -> listening (continuous) -> processing (wake detected) -> listening
 *         idle -> muted (user toggle)
 * Audio is sent to server while staying in 'listening' state (non-blocking).
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
    this._rmsCleanup = null;
    this._speechStartTs = null;
    this._lastAudioSendTs = 0;
    this._watchdogInterval = null;
    this._isStale = false;
  }

  // Watchdog: detect silent failures where VAD stops emitting audio despite 'listening' state
  _startWatchdog() {
    this._stopWatchdog();
    this._lastAudioSendTs = Date.now();
    this._isStale = false;
    const STALE_MS = 2 * 60 * 1000;
    const RESTART_MS = 10 * 60 * 1000;
    this._watchdogInterval = setInterval(() => {
      if (!this.enabled || this.state !== 'listening') return;
      const idle = Date.now() - this._lastAudioSendTs;
      if (idle > RESTART_MS) {
        console.warn(`[AlwaysOn] watchdog: no audio for ${Math.floor(idle/60000)}min, auto-restarting`);
        this.restart();
      } else if (idle > STALE_MS) {
        this._setStale(true);
      }
    }, 30 * 1000);
  }

  _stopWatchdog() {
    if (this._watchdogInterval) {
      clearInterval(this._watchdogInterval);
      this._watchdogInterval = null;
    }
  }

  _setStale(stale) {
    if (this._isStale === stale) return;
    this._isStale = stale;
    if (this.state === 'listening') {
      this.onStateChange(stale ? 'listening_stale' : 'listening');
    }
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

    // Phase 2: 連続録音チャンク（VAD なし）— large-v3 chunk transcribe の素材
    this._initRawChunkRecorder().catch((err) => {
      console.warn('[AlwaysOn] raw chunk init failed', err);
    });

    this.enabled = true;
    this._setState('listening');
    this._startWatchdog();
  }

  async _initRawChunkRecorder() {
    if (!this.micStream || this._rawChunkInterval) return;
    const RAW_MIME = 'audio/webm;codecs=opus';
    if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported(RAW_MIME)) {
      console.warn('[AlwaysOn] raw chunk recorder unsupported in this env');
      return;
    }
    const CHUNK_MS = 30000;

    // EC/NS/AGC を無効にした別 stream を取得（room audio = iPad 等の遠方音を保つ）。
    // always-on の VAD/STT は引き続き既存 micStream（EC/NS ON）を使う。
    let chunkStream = null;
    let streamMode = 'shared_fallback';
    try {
      chunkStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
      this._chunkStream = chunkStream;
      streamMode = 'dedicated_no_ec_ns';
      console.log('[AlwaysOn] raw chunk: dedicated stream (EC/NS/AGC OFF) acquired');
    } catch (err) {
      console.warn('[AlwaysOn] dedicated chunk stream failed, fallback to shared micStream', err);
      chunkStream = this.micStream;
    }
    this._chunkStreamMode = streamMode;

    // 各セッションごとに新 MediaRecorder を立ててヘッダ付き完結 webm を生成。
    // start(timeslice) は 2 つ目以降のチャンクに EBML ヘッダがなく ffmpeg がデコード失敗するため使えない。
    const startNewSession = () => {
      try {
        const rec = new MediaRecorder(chunkStream, {
          mimeType: RAW_MIME,
          audioBitsPerSecond: 32000,
        });
        const chunks = [];
        rec.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data); };
        rec.onstop = () => {
          if (chunks.length === 0) return;
          const blob = new Blob(chunks, { type: RAW_MIME });
          const ws = this.wsRef();
          if (!ws || ws.readyState !== WebSocket.OPEN) return;
          blob.arrayBuffer().then((buf) => {
            try {
              ws.send(JSON.stringify({ type: 'raw_audio_chunk', ts: Date.now(), stream_mode: this._chunkStreamMode }));
              ws.send(buf);
            } catch (err) {
              console.warn('[AlwaysOn] raw chunk send failed', err);
            }
          });
        };
        rec.onerror = (e) => console.warn('[AlwaysOn] raw chunk recorder error', e);
        rec.start();
        this._currentChunkRecorder = rec;
      } catch (err) {
        console.warn('[AlwaysOn] raw chunk recorder start failed', err);
      }
    };

    startNewSession();
    this._rawChunkInterval = setInterval(() => {
      const rec = this._currentChunkRecorder;
      if (rec && rec.state === 'recording') {
        try { rec.stop(); } catch {}
      }
      startNewSession();
    }, CHUNK_MS);
    console.log('[AlwaysOn] raw chunk recorder started (30s rotate)');
  }

  _stopRawChunkRecorder() {
    if (this._rawChunkInterval) {
      clearInterval(this._rawChunkInterval);
      this._rawChunkInterval = null;
    }
    if (this._currentChunkRecorder) {
      try { this._currentChunkRecorder.stop(); } catch {}
      this._currentChunkRecorder = null;
    }
    if (this._chunkStream && this._chunkStream !== this.micStream) {
      try { this._chunkStream.getTracks().forEach(t => t.stop()); } catch {}
    }
    this._chunkStream = null;
  }

  async _initSileroVAD() {
    const { MicVAD } = await import('@ricky0123/vad-web');
    this.vad = await MicVAD.new({
      stream: this.micStream,
      onSpeechStart: () => {
        if (this.state !== 'listening') return;
        this._speechStartTs = Date.now();
        console.log('[AlwaysOn] speech detected');
      },
      onSpeechEnd: (audio) => {
        if (this.state !== 'listening') return;
        this._handleSpeechSegment(audio);
      },
      positiveSpeechThreshold: 0.8,
      negativeSpeechThreshold: 0.35,
      minSpeechFrames: 8,
      preSpeechPadFrames: 10,
      redemptionFrames: 12,
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
    const THRESHOLD = 0.05;
    const MIN_SPEECH_MS = 500;
    const SILENCE_TIMEOUT_MS = 800;
    let silenceTimer = null;

    // Use setInterval instead of requestAnimationFrame — rAF stops when window is hidden/background
    const checkInterval = setInterval(() => {
      if (!this.enabled) return;
      analyser.getFloatTimeDomainData(dataArray);
      let rms = 0;
      for (let i = 0; i < dataArray.length; i++) rms += dataArray[i] * dataArray[i];
      rms = Math.sqrt(rms / dataArray.length);

      // Barge-in: if audio is playing and user speaks loudly, send stop signal
      if (rms > 0.04 && window._isPlayingAudio) {
        const ws = this.wsRef();
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'barge_in' }));
          console.log('[AlwaysOn] barge-in detected (RMS:', rms.toFixed(3), ')');
          window._isPlayingAudio = false; // prevent repeated sends
        }
      }

      if (rms > THRESHOLD) {
        if (!speechStart && this.state === 'listening') {
          speechStart = Date.now();
          this._speechStartTs = speechStart;
          chunks = [];
          recorder = new MediaRecorder(this.micStream, { mimeType: 'audio/webm;codecs=opus' });
          recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
          recorder.onstop = async () => {
            const blob = new Blob(chunks, { type: 'audio/webm' });
            const buf = await blob.arrayBuffer();
            this._handleSpeechSegmentWebm(buf);
          };
          recorder.start();
          console.log('[AlwaysOn] RMS speech start');
        }
        if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
      } else if (speechStart) {
        if (!silenceTimer) {
          silenceTimer = setTimeout(() => {
            if (Date.now() - speechStart >= MIN_SPEECH_MS && recorder && recorder.state === 'recording') {
              console.log('[AlwaysOn] RMS speech end, sending');
              recorder.stop();
            } else if (recorder && recorder.state === 'recording') {
              recorder.stop();
            }
            speechStart = null;
            silenceTimer = null;
          }, SILENCE_TIMEOUT_MS);
        }
      }
    }, 50); // 50ms = 20Hz check rate

    this._rmsCleanup = () => {
      this.enabled = false;
      clearInterval(checkInterval);
      audioCtx.close();
    };
  }

  async _handleSpeechSegment(audioFloat32) {
    const wavBuffer = this._float32ToWav(audioFloat32, 16000);
    this._sendAlwaysOnAudio(wavBuffer);
  }

  async _handleSpeechSegmentWebm(webmBuffer) {
    this._sendAlwaysOnAudio(webmBuffer);
  }

  _sendAlwaysOnAudio(audioBuffer) {
    const ws = this.wsRef();
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({
      type: 'always_on_audio',
      format: 'wav',
      speech_ts: this._speechStartTs || Date.now(),
    }));
    ws.send(audioBuffer);
    this._lastAudioSendTs = Date.now();
    if (this._isStale) this._setStale(false);
    this._speechStartTs = null;
    // Stay in 'listening' — server processes async, we keep capturing
  }

  handleServerMessage(msg) {
    if (msg.type === 'wake_detected') {
      this._setState('processing');
      this.onWakeDetected(msg);
      // Resume listening after echo window (audio playback + margin)
      setTimeout(() => this.returnToListening(), 4000);
    } else if (msg.type === 'always_on_result') {
      // No wake word — already listening, nothing to do
    }
  }

  returnToListening() {
    if (this.state === 'processing') this._setState('listening');
  }

  stop() {
    this._stopWatchdog();
    if (this.vad) this.vad.pause();
    if (this._rmsCleanup) this._rmsCleanup();
    this._stopRawChunkRecorder();
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

  async restart() {
    const wasEnabled = this.enabled;
    console.log(`[AlwaysOn] restart requested (wasEnabled=${wasEnabled})`);
    this.destroy();
    if (wasEnabled) {
      // Let WebAudio/MediaStream resources fully release before re-initializing —
      // skipping this causes Silero VAD to silently fail on rapid destroy→new cycles.
      await new Promise(r => setTimeout(r, 300));
      await this.start();
    }
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
    this._stopWatchdog();
    if (this.vad) { this.vad.destroy(); this.vad = null; }
    if (this._rmsCleanup) this._rmsCleanup();
    this._stopRawChunkRecorder();
    if (this.micStream) { this.micStream.getTracks().forEach(t => t.stop()); this.micStream = null; }
    this.enabled = false;
    this._isStale = false;
    this._setState('idle');
  }
}

window.AlwaysOnListener = AlwaysOnListener;
