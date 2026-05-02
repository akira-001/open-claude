// dashboard/src/components/ember-chat/useAlwaysOn.ts
//
// Ports the RMS-based Voice Activity Detection (VAD) loop from the legacy
// always-on.js (Silero VAD + RMS fallback). Only the RMS path is implemented
// here — adequate to send detected speech to the voice_chat server, which
// then emits user_text / assistant_text / status WebSocket messages that the
// existing useEmberChat handler renders.

import { useCallback, useEffect, useRef, useState } from 'react';

import type { AlwaysOnState } from './ServerStatusBar';

const CONSENT_KEY = 'ember.alwaysOn.consented';
const ENABLED_KEY = 'ember.alwaysOn.enabled';

const RMS_THRESHOLD = 0.05;
const MIN_SPEECH_MS = 500;
const SILENCE_TIMEOUT_MS = 800;
const STALE_MS = 2 * 60 * 1000;
const RESTART_MS = 10 * 60 * 1000;

export interface UseAlwaysOnOptions {
  wsRef: React.MutableRefObject<WebSocket | null>;
}

export interface UseAlwaysOnReturn {
  state: AlwaysOnState;
  consentRequired: boolean;
  toggle: () => void;
  acceptConsent: () => void;
  declineConsent: () => void;
}

interface InternalRefs {
  micStream: MediaStream | null;
  audioCtx: AudioContext | null;
  checkInterval: ReturnType<typeof setInterval> | null;
  recorder: MediaRecorder | null;
  chunks: Blob[];
  speechStart: number | null;
  silenceTimer: ReturnType<typeof setTimeout> | null;
  lastAudioSendTs: number;
  watchdog: ReturnType<typeof setInterval> | null;
  // raw chunk recorder
  rawChunkInterval: ReturnType<typeof setInterval> | null;
  currentChunkRecorder: MediaRecorder | null;
  chunkStream: MediaStream | null;
  chunkStreamMode: 'dedicated_no_ec_ns' | 'shared_fallback';
}

export function useAlwaysOn({ wsRef }: UseAlwaysOnOptions): UseAlwaysOnReturn {
  // Restore enabled state from previous launch. Combined with Electron's
  // autoplay-policy relaxation in main.js, mic auto-acquisition works.
  const [enabled, setEnabled] = useState<boolean>(() => {
    if (typeof localStorage === 'undefined') return false;
    return localStorage.getItem(ENABLED_KEY) === 'true';
  });
  const [consentRequired, setConsentRequired] = useState(false);
  const [stale, setStale] = useState(false);
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(ENABLED_KEY, enabled ? 'true' : 'false');
    }
  }, [enabled]);

  const refs = useRef<InternalRefs>({
    micStream: null,
    audioCtx: null,
    checkInterval: null,
    recorder: null,
    chunks: [],
    speechStart: null,
    silenceTimer: null,
    lastAudioSendTs: 0,
    watchdog: null,
    rawChunkInterval: null,
    currentChunkRecorder: null,
    chunkStream: null,
    chunkStreamMode: 'shared_fallback',
  });

  const sendAudio = useCallback(async (buf: ArrayBuffer, speechTs: number) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn('[AlwaysOn] cannot send: ws state =', ws?.readyState);
      return;
    }
    try {
      console.log(`[AlwaysOn] sending always_on_audio: ${buf.byteLength} bytes, speech_ts=${speechTs}`);
      ws.send(JSON.stringify({
        type: 'always_on_audio',
        format: 'wav',
        speech_ts: speechTs,
      }));
      ws.send(buf);
      refs.current.lastAudioSendTs = Date.now();
      setStale(false);
    } catch (err) {
      console.warn('[AlwaysOn] send failed', err);
    }
  }, [wsRef]);

  const stopRawChunkRecorder = useCallback(() => {
    const r = refs.current;
    if (r.rawChunkInterval) { clearInterval(r.rawChunkInterval); r.rawChunkInterval = null; }
    if (r.currentChunkRecorder) {
      try { r.currentChunkRecorder.stop(); } catch {}
      r.currentChunkRecorder = null;
    }
    if (r.chunkStream && r.chunkStream !== r.micStream) {
      try { r.chunkStream.getTracks().forEach((t) => t.stop()); } catch {}
    }
    r.chunkStream = null;
  }, []);

  const stop = useCallback(() => {
    const r = refs.current;
    stopRawChunkRecorder();
    if (r.checkInterval) { clearInterval(r.checkInterval); r.checkInterval = null; }
    if (r.silenceTimer) { clearTimeout(r.silenceTimer); r.silenceTimer = null; }
    if (r.watchdog) { clearInterval(r.watchdog); r.watchdog = null; }
    if (r.recorder && r.recorder.state === 'recording') {
      try { r.recorder.stop(); } catch {}
    }
    r.recorder = null;
    r.chunks = [];
    r.speechStart = null;
    if (r.audioCtx) { try { r.audioCtx.close(); } catch {} r.audioCtx = null; }
    if (r.micStream) {
      r.micStream.getTracks().forEach((t) => t.stop());
      r.micStream = null;
    }
    setProcessing(false);
    setStale(false);
  }, [stopRawChunkRecorder]);

  const initRawChunkRecorder = useCallback(async () => {
    const r = refs.current;
    if (!r.micStream || r.rawChunkInterval) return;
    const RAW_MIME = 'audio/webm;codecs=opus';
    if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported(RAW_MIME)) {
      console.warn('[AlwaysOn] raw chunk recorder unsupported in this env');
      return;
    }
    const CHUNK_MS = 30000;

    let chunkStream: MediaStream;
    let streamMode: 'dedicated_no_ec_ns' | 'shared_fallback' = 'shared_fallback';
    try {
      chunkStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
      r.chunkStream = chunkStream;
      streamMode = 'dedicated_no_ec_ns';
      console.log('[AlwaysOn] raw chunk: dedicated stream (EC/NS/AGC OFF) acquired');
    } catch (err) {
      console.warn('[AlwaysOn] dedicated chunk stream failed, fallback to shared micStream', err);
      chunkStream = r.micStream!;
      r.chunkStream = chunkStream;
    }
    r.chunkStreamMode = streamMode;

    const startNewSession = () => {
      try {
        const rec = new MediaRecorder(chunkStream, { mimeType: RAW_MIME, audioBitsPerSecond: 32000 });
        const chunks: Blob[] = [];
        rec.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunks.push(e.data); };
        rec.onstop = () => {
          if (chunks.length === 0) return;
          const blob = new Blob(chunks, { type: RAW_MIME });
          const ws = wsRef.current;
          if (!ws || ws.readyState !== WebSocket.OPEN) return;
          blob.arrayBuffer().then((buf) => {
            try {
              ws.send(JSON.stringify({ type: 'raw_audio_chunk', ts: Date.now(), stream_mode: refs.current.chunkStreamMode }));
              ws.send(buf);
            } catch (sendErr) {
              console.warn('[AlwaysOn] raw chunk send failed', sendErr);
            }
          }).catch(() => {});
        };
        rec.onerror = (e) => console.warn('[AlwaysOn] raw chunk recorder error', e);
        rec.start();
        r.currentChunkRecorder = rec;
      } catch (err) {
        console.warn('[AlwaysOn] raw chunk recorder start failed', err);
      }
    };

    startNewSession();
    r.rawChunkInterval = setInterval(() => {
      const cur = refs.current.currentChunkRecorder;
      if (cur && cur.state === 'recording') {
        try { cur.stop(); } catch {}
      }
      startNewSession();
    }, CHUNK_MS);
    console.log('[AlwaysOn] raw chunk recorder started (30s rotate)');
  }, [wsRef]);

  const start = useCallback(async () => {
    console.log('[AlwaysOn] start() — requesting mic');
    let micStream: MediaStream;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
      const tracks = micStream.getTracks();
      console.log('[AlwaysOn] mic stream acquired, tracks=', tracks.length);
    } catch (err) {
      console.error('[AlwaysOn] Mic access denied:', err);
      setEnabled(false);
      return;
    }
    refs.current.micStream = micStream;
    refs.current.lastAudioSendTs = Date.now();

    void initRawChunkRecorder();

    // Continuous chunked recording (5s rotate). Each session generates a
    // standalone webm with EBML header so server-side ffmpeg/whisper can decode.
    // Bypasses AudioContext/AnalyserNode entirely — those return all-zero
    // buffers in some Electron 35 + macOS configurations.
    const CHUNK_MS = 5000;
    const startNewRecorderSession = () => {
      const r = refs.current;
      if (!r.micStream) return;
      try {
        const recorder = new MediaRecorder(r.micStream, { mimeType: 'audio/webm;codecs=opus' });
        const chunks: Blob[] = [];
        recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
        recorder.onstop = async () => {
          if (chunks.length === 0) return;
          const blob = new Blob(chunks, { type: 'audio/webm' });
          const buf = await blob.arrayBuffer();
          console.log(`[AlwaysOn] chunk recorded ${buf.byteLength}b`);
          await sendAudio(buf, Date.now());
        };
        recorder.start();
        r.recorder = recorder;
      } catch (err) {
        console.warn('[AlwaysOn] recorder start failed', err);
      }
    };

    startNewRecorderSession();
    refs.current.checkInterval = setInterval(() => {
      const r = refs.current;
      if (r.recorder && r.recorder.state === 'recording') {
        try { r.recorder.stop(); } catch {}
      }
      startNewRecorderSession();
    }, CHUNK_MS);

    // Watchdog: detect silent failures
    refs.current.watchdog = setInterval(() => {
      const idle = Date.now() - refs.current.lastAudioSendTs;
      if (idle > RESTART_MS) {
        console.warn('[AlwaysOn] watchdog: no audio for too long, restarting');
        stop();
        setTimeout(() => { setEnabled(true); }, 300);
      } else if (idle > STALE_MS) {
        setStale(true);
      }
    }, 30 * 1000);
  }, [sendAudio, stop, initRawChunkRecorder]);

  // Effect: enable / disable lifecycle (always triggered by user gesture
  // since cold-start enabled=false, so no autoplay-policy issues)
  useEffect(() => {
    if (!enabled) return;
    const consented = typeof localStorage !== 'undefined'
      && localStorage.getItem(CONSENT_KEY) === 'true';
    if (!consented) {
      setConsentRequired(true);
      return;
    }
    void start();
    return () => stop();
  }, [enabled, start, stop]);

  const toggle = useCallback(() => {
    setEnabled((v) => !v);
  }, []);

  const acceptConsent = useCallback(() => {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(CONSENT_KEY, 'true');
    }
    setConsentRequired(false);
    void start();
  }, [start]);

  const declineConsent = useCallback(() => {
    setConsentRequired(false);
    setEnabled(false);
  }, []);

  let state: AlwaysOnState = 'muted';
  if (enabled && !consentRequired) {
    if (processing) state = 'processing';
    else if (stale) state = 'listening-stale';
    else state = 'listening';
  }

  return { state, consentRequired, toggle, acceptConsent, declineConsent };
}
