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
}

export function useAlwaysOn({ wsRef }: UseAlwaysOnOptions): UseAlwaysOnReturn {
  const [enabled, setEnabled] = useState<boolean>(() => {
    if (typeof localStorage === 'undefined') return false;
    return localStorage.getItem(ENABLED_KEY) === 'true';
  });
  const [consentRequired, setConsentRequired] = useState(false);
  const [stale, setStale] = useState(false);
  const [processing, setProcessing] = useState(false);

  // Persist enabled state across launches
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

  const stop = useCallback(() => {
    const r = refs.current;
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
  }, []);

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
  }, [sendAudio, stop]);

  // Effect: enable / disable lifecycle
  useEffect(() => {
    if (!enabled) return;
    const consented = typeof localStorage !== 'undefined'
      && localStorage.getItem(CONSENT_KEY) === 'true';
    if (!consented) {
      setConsentRequired(true);
      return;
    }

    // Chromium autoplay policy: getUserMedia called BEFORE the first user
    // gesture in a session can return a "muted" silent stream (no
    // permission prompt is shown either). After cold restart, the saved
    // enabled=true triggers this path. Delay start() until the first
    // click anywhere in the document.
    let cancelled = false;
    let started = false;
    const tryStart = () => {
      if (cancelled || started) return;
      started = true;
      void start();
    };

    if (typeof navigator !== 'undefined' && navigator.userActivation?.hasBeenActive) {
      tryStart();
    } else {
      const onGesture = () => {
        tryStart();
        document.removeEventListener('click', onGesture);
        document.removeEventListener('keydown', onGesture);
      };
      document.addEventListener('click', onGesture, { once: true });
      document.addEventListener('keydown', onGesture, { once: true });
    }

    return () => {
      cancelled = true;
      stop();
    };
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
