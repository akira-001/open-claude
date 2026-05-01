/**
 * Meeting Recorder for Ember Chat
 *
 * 会議など長尺の録音 + Whisper 文字起こし用。
 * Always-On Listening とは独立した MediaStream / MediaRecorder を持つので並行動作する。
 *
 * 出力: webm (Opus, 64kbps mono) — 1時間で約20-30MB。Whisper は ffmpeg 経由で直接読める。
 */

const REC_MIME = 'audio/webm;codecs=opus';
const REC_BITRATE = 64000;

class MeetingRecorder {
  constructor({ onStateChange, onTick, onSaved, onError, onQueueChange } = {}) {
    this.onStateChange = onStateChange || (() => {});
    this.onTick = onTick || (() => {});
    this.onSaved = onSaved || (() => {});
    this.onError = onError || (() => {});
    this.onQueueChange = onQueueChange || (() => {});

    this.state = 'idle'; // idle | recording | saving
    this.stream = null;
    this.recorder = null;
    this.chunks = [];
    this.startedAt = 0;
    this.tickInterval = null;
    this.currentBaseName = null;
    this.pendingTranscriptions = 0;
  }

  isAvailable() {
    return typeof MediaRecorder !== 'undefined'
      && MediaRecorder.isTypeSupported(REC_MIME);
  }

  async start() {
    if (this.state !== 'idle') return false;
    if (!this.isAvailable()) {
      this.onError(new Error('MediaRecorder webm/opus 未対応'));
      return false;
    }
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          channelCount: 1,
          sampleRate: 16000,
        },
      });
    } catch (err) {
      this.onError(err);
      return false;
    }

    this.chunks = [];
    this.recorder = new MediaRecorder(this.stream, {
      mimeType: REC_MIME,
      audioBitsPerSecond: REC_BITRATE,
    });
    this.recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) this.chunks.push(e.data);
    };
    this.recorder.onstop = () => this._handleStop();
    this.recorder.onerror = (e) => this.onError(e.error || new Error('recorder error'));

    this.startedAt = Date.now();
    this.currentBaseName = `meeting-${jstStamp()}`;
    // Flush a chunk every 30s so a crash doesn't lose the whole session
    this.recorder.start(30000);
    this._setState('recording');
    this.tickInterval = setInterval(() => {
      this.onTick(this.elapsedMs());
    }, 1000);
    return true;
  }

  stop() {
    if (this.state !== 'recording' || !this.recorder) return;
    this._setState('saving');
    if (this.tickInterval) {
      clearInterval(this.tickInterval);
      this.tickInterval = null;
    }
    this.recorder.stop();
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
  }

  toggle() {
    if (this.state === 'recording') this.stop();
    else if (this.state === 'idle') this.start();
  }

  elapsedMs() {
    return this.state === 'recording' ? Date.now() - this.startedAt : 0;
  }

  async _handleStop() {
    const baseName = this.currentBaseName || `meeting-${jstStamp()}`;
    this.currentBaseName = null;

    let saved;
    try {
      const blob = new Blob(this.chunks, { type: REC_MIME });
      this.chunks = [];
      const buffer = new Uint8Array(await blob.arrayBuffer());
      const audioFilename = `${baseName}.webm`;
      saved = await window.emberBridge.saveRecordingAudio({
        filename: audioFilename,
        buffer: Array.from(buffer),
      });
      if (!saved?.ok) throw new Error('audio save failed');
      this.onSaved({ phase: 'audio_saved', path: saved.path, baseName, sizeBytes: buffer.length });
    } catch (err) {
      this.onError(err);
      this._setState('idle');
      return;
    }

    // 録音ボタンはここで即解放。文字起こしはバックグラウンドで継続。
    this._setState('idle');
    this._runTranscription(saved.path, baseName);
  }

  async _runTranscription(audioPath, baseName) {
    this.pendingTranscriptions += 1;
    this.onQueueChange(this.pendingTranscriptions);
    try {
      let result = null;
      try {
        const resp = await fetch('http://localhost:8767/api/transcribe-file', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: audioPath }),
        });
        result = await resp.json();
      } catch (err) {
        this.onError(err);
      }

      if (result?.ok) {
        const txtFilename = `${baseName}.txt`;
        const body = result.transcript || result.text || '';
        const txtSaved = await window.emberBridge.saveRecordingText({
          filename: txtFilename,
          text: body,
        });
        this.onSaved({
          phase: 'transcribed',
          audioPath,
          textPath: txtSaved?.path,
          duration: result.duration,
          segmentCount: result.segment_count,
          elapsed: result.elapsed,
        });
        // 文字起こし完了後、固有名詞候補を抽出（バックグラウンド）
        this._kickoffTermExtraction(body, baseName);
      } else {
        this.onSaved({
          phase: 'transcribe_failed',
          audioPath,
          error: result?.error || 'transcription failed',
        });
      }
    } finally {
      this.pendingTranscriptions = Math.max(0, this.pendingTranscriptions - 1);
      this.onQueueChange(this.pendingTranscriptions);
    }
  }

  async _kickoffTermExtraction(transcript, baseName) {
    try {
      const resp = await fetch('http://localhost:8767/api/transcribe/extract-terms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript }),
      });
      const result = await resp.json();
      if (result?.ok && Array.isArray(result.candidates) && result.candidates.length > 0) {
        this.onSaved({
          phase: 'term_candidates',
          baseName,
          candidates: result.candidates,
        });
      }
    } catch (err) {
      console.warn('[MeetingRecorder] term extract failed', err);
    }
  }

  _setState(next) {
    if (this.state === next) return;
    this.state = next;
    this.onStateChange(next);
  }
}

function jstStamp() {
  const fmt = new Intl.DateTimeFormat('ja-JP', {
    timeZone: 'Asia/Tokyo',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  });
  const parts = Object.fromEntries(fmt.formatToParts(new Date()).map((p) => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}_${parts.hour}-${parts.minute}-${parts.second}`;
}

function formatElapsed(ms) {
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

window.MeetingRecorder = MeetingRecorder;
window.formatRecorderElapsed = formatElapsed;
