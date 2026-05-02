// dashboard/src/components/ember-chat/useEmberChat.ts
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChatMessage, ContextSummary, EmberSettings, Speaker, OllamaModel, MediaContext } from './types';
import { DEFAULT_SETTINGS } from './types';
import { buildStatusDiagnostic, parseDiagnosticLine } from './diagnostics';

const API_BASE = '/whisper/api';
const WS_URL = `ws://${typeof window !== 'undefined' ? window.location.host : 'localhost:3456'}/ws`;

export function useEmberChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [settings, setSettings] = useState<EmberSettings>(DEFAULT_SETTINGS);
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [botSpeakers, setBotSpeakers] = useState<Record<string, Speaker[]>>({});
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [replyBot, setReplyBot] = useState<string | null>(null);
  const [lastBotId, setLastBotId] = useState<string | null>(null);
  const [contextSummary, setContextSummary] = useState<ContextSummary | null>(null);
  const [mediaCtx, setMediaCtx] = useState<MediaContext | null>(null);
  const settingsExpanded = settings.settingsExpanded ?? false;

  const wsRef = useRef<WebSocket | null>(null);
  const settingsRef = useRef(settings);
  const lastSaveTimeRef = useRef(0);
  const audioQueueRef = useRef<ArrayBuffer[]>([]);
  const isPlayingRef = useRef(false);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const currentAudioUrlRef = useRef<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const playedIdsRef = useRef(new Set<string>());
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shouldReconnectRef = useRef(true);

  // Keep settingsRef in sync
  useEffect(() => { settingsRef.current = settings; }, [settings]);

  // --- Audio playback via HTMLAudioElement (avoids Web Audio autoplay quirks) ---
  const cleanupCurrentAudio = useCallback(() => {
    if (currentAudioRef.current) {
      try {
        currentAudioRef.current.pause();
        currentAudioRef.current.src = '';
      } catch {}
      currentAudioRef.current = null;
    }
    if (currentAudioUrlRef.current) {
      try { URL.revokeObjectURL(currentAudioUrlRef.current); } catch {}
      currentAudioUrlRef.current = null;
    }
  }, []);

  const processQueue = useCallback(() => {
    if (isPlayingRef.current || audioQueueRef.current.length === 0) return;
    isPlayingRef.current = true;
    const buf = audioQueueRef.current.shift()!;
    const blob = new Blob([buf], { type: 'audio/wav' });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudioRef.current = audio;
    currentAudioUrlRef.current = url;

    const onDone = () => {
      cleanupCurrentAudio();
      isPlayingRef.current = false;
      processQueue();
    };

    audio.onended = onDone;
    audio.onerror = (e) => {
      console.error('[ember-chat] audio play error:', e);
      onDone();
    };

    audio.play().catch((err) => {
      console.error('[ember-chat] audio.play() rejected:', err);
      onDone();
    });
  }, [cleanupCurrentAudio]);

  const playAudio = useCallback((buf: ArrayBuffer) => {
    audioQueueRef.current.push(buf);
    processQueue();
  }, [processQueue]);

  // --- WebSocket ---
  const wsSend = useCallback((obj: unknown) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  }, []);

  const stopAudio = useCallback((broadcast = true) => {
    audioQueueRef.current.length = 0;
    cleanupCurrentAudio();
    isPlayingRef.current = false;
    if (broadcast) wsSend({ type: 'stop_audio' });
  }, [cleanupCurrentAudio, wsSend]);

  const addMessage = useCallback((text: string, type: ChatMessage['type'], botId?: string, diagnostic?: ChatMessage['diagnostic']) => {
    setMessages(prev => [...prev, {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      type, text, botId,
      timestamp: Date.now(),
      diagnostic,
    }]);
  }, []);

  const parseSpeedValue = useCallback((speed: string) => {
    if (speed === 'auto') return 1.0;
    const v = parseFloat(speed);
    return Number.isFinite(v) ? v : 1.0;
  }, []);

  const updateSetting = useCallback(<K extends keyof EmberSettings>(key: K, value: EmberSettings[K]) => {
    setSettings(prev => {
      const next = { ...prev, [key]: value } as EmberSettings & { listeningDebug?: boolean };
      // Server-side flag for STT debug stream is `listeningDebug` (legacy name).
      // Mirror debugMode → listeningDebug so the WS stream is enabled on save.
      if (key === 'debugMode') {
        next.listeningDebug = value as boolean;
      }
      // Debounced save to server
      lastSaveTimeRef.current = Date.now();
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'update_settings', settings: next }));
      }
      // Send specific WS commands for voice/speed/model
      if (key === 'voiceSelect') {
        const vid = String(value);
        wsSend({ type: 'set_speaker', speaker_id: /^\d+$/.test(vid) ? parseInt(vid) : vid });
      } else if (key === 'speedSelect') {
        const sv = String(value);
        wsSend({ type: 'set_speed', speed: parseSpeedValue(sv) });
      } else if (key === 'modelSelect') {
        wsSend({ type: 'set_model', model: value });
      } else if (key === 'emojiEnabled') {
        fetch(`/api/proactive/state?botId=mei`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ emojiEnabled: value }),
        }).catch(() => {});
        fetch(`/api/proactive/state?botId=eve`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ emojiEnabled: value }),
        }).catch(() => {});
      }
      return next;
    });
  }, [parseSpeedValue, wsSend]);

  const setSettingsExpanded = useCallback((v: boolean) => updateSetting('settingsExpanded', v), [updateSetting]);

  const updateSettings = useCallback((partial: Partial<EmberSettings>) => {
    setSettings(prev => {
      const next = { ...prev, ...partial };
      lastSaveTimeRef.current = Date.now();
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'update_settings', settings: next }));
      }
      return next;
    });
  }, []);

  // --- Load speakers for engine ---
  const loadSpeakers = useCallback(async (engine?: string) => {
    const eng = engine || settingsRef.current.ttsEngine || 'voicevox';
    try {
      const resp = await fetch(`${API_BASE}/speakers?engine=${eng}`);
      const data: Speaker[] = await resp.json();
      setSpeakers(data);
      // Reload bot speakers: if bot has independent engine, keep its speakers;
      // if bot follows global, update to new global speakers
      const s = settingsRef.current;
      for (const botId of ['mei', 'eve']) {
        const botEng = s[`${botId}Engine` as keyof EmberSettings] as string;
        if (!botEng || botEng === eng) {
          // Bot follows global — use same speakers
          setBotSpeakers(prev => ({ ...prev, [botId]: data }));
        }
        // else: bot has independent engine, leave its botSpeakers as-is
      }
      return data;
    } catch {
      return [];
    }
  }, []);

  // --- Bot engine change (per-bot speaker loading) ---
  const handleBotEngineChange = useCallback(async (botId: string, engine: string) => {
    const engineKey = `${botId}Engine` as keyof EmberSettings;
    const voiceKey = `${botId}Voice` as keyof EmberSettings;
    updateSetting(engineKey, engine);
    try {
      const resp = await fetch(`${API_BASE}/speakers?engine=${engine}`);
      const data: Speaker[] = await resp.json();
      setBotSpeakers(prev => ({ ...prev, [botId]: data }));
      if (data.length > 0) {
        const firstId = String(data[0].styles[0]?.id ?? '');
        updateSetting(voiceKey, firstId);
      }
    } catch {}
  }, [updateSetting]);

  // --- Load models ---
  const loadModels = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/models`);
      const data: OllamaModel[] = await resp.json();
      setModels(data);
    } catch {}
  }, []);

  // --- Proactive message handler ---
  const pendingProactiveAudioRef = useRef(false);

  const handleProactiveMessage = useCallback(async (botId: string, text: string, _speaker: string, _speed: string) => {
    addMessage(text, 'proactive', botId);
    setLastBotId(botId);
    // 音声はサーバー側で生成済み — 直後に WS バイナリとして届く
    pendingProactiveAudioRef.current = true;
  }, [addMessage]);

  // --- Connect WebSocket ---
  useEffect(() => {
    let ws: WebSocket;
    shouldReconnectRef.current = true;

    function connect() {
      ws = new WebSocket(WS_URL);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => setWsConnected(true);

      ws.onmessage = async (e) => {
        if (e.data instanceof ArrayBuffer) {
          const isProactive = pendingProactiveAudioRef.current;
          pendingProactiveAudioRef.current = false;
          if (settingsRef.current.ttsEnabled && document.visibilityState === 'visible') {
            playAudio(e.data);
          }
          if (!isProactive) setProcessing(false);
          return;
        }

        const msg = JSON.parse(e.data);

        if (msg.type === 'stop_audio') {
          stopAudio(false);
        } else if (msg.type === 'proactive_message') {
          const msgId = msg.ts || `${msg.botId}-${msg.text}`;
          if (playedIdsRef.current.has(msgId)) return;
          playedIdsRef.current.add(msgId);
          if (playedIdsRef.current.size > 100) {
            const arr = [...playedIdsRef.current];
            playedIdsRef.current = new Set(arr.slice(-50));
          }
          handleProactiveMessage(msg.botId, msg.text, msg.speaker, msg.speed);
        } else if (msg.type === 'sync_settings') {
          // Skip if we just saved locally
          if (Date.now() - lastSaveTimeRef.current < 500) return;
          setSettings(prev => ({ ...prev, ...msg.settings }));
          // Send WS commands to sync server-side session state
          const vid = msg.settings.voiceSelect;
          if (vid) wsSend({ type: 'set_speaker', speaker_id: /^\d+$/.test(vid) ? parseInt(vid) : vid });
          if (msg.settings.speedSelect) wsSend({ type: 'set_speed', speed: parseSpeedValue(msg.settings.speedSelect) });
          if (msg.settings.modelSelect) wsSend({ type: 'set_model', model: msg.settings.modelSelect });
          // Reload speakers if engine changed
          if (msg.settings.ttsEngine) loadSpeakers(msg.settings.ttsEngine);
        } else if (msg.type === 'status') {
          addMessage(msg.text, 'status', undefined, buildStatusDiagnostic(msg.text) ?? undefined);
        } else if (msg.type === 'diagnostic') {
          const text = typeof msg.text === 'string' ? msg.text : (typeof msg.summary === 'string' ? msg.summary : JSON.stringify(msg));
          addMessage(text, 'status', undefined, parseDiagnosticLine(text) || {
            kind: 'unknown',
            label: 'diagnostic',
            summary: text,
            raw: text,
            confidence: typeof msg.confidence === 'number' ? msg.confidence : undefined,
          });
        } else if (msg.type === 'user_text') {
          addMessage(msg.text, 'user');
        } else if (msg.type === 'assistant_text') {
          addMessage(msg.text, 'assistant');
          if (msg.tts_fallback && settingsRef.current.ttsEnabled) {
            // Browser TTS fallback
            const u = new SpeechSynthesisUtterance(msg.text);
            u.lang = 'ja-JP';
            speechSynthesis.speak(u);
          }
          if (msg.tts_fallback) setProcessing(false);
        } else if (msg.type === 'ambient_response') {
          addMessage(msg.text, 'assistant');
          if (msg.tts_fallback && settingsRef.current.ttsEnabled) {
            const u = new SpeechSynthesisUtterance(msg.text);
            u.lang = 'ja-JP';
            speechSynthesis.speak(u);
          }
        } else if (msg.type === 'listening_debug') {
          // Debug button (settings.debugMode) のときだけ表示
          if (settingsRef.current.debugMode) {
            addMessage(msg.text, 'debug');
          }
        } else if (msg.type === 'context_summary') {
          if (msg.summary) setContextSummary(msg.summary as ContextSummary);
          if (msg.media_ctx) setMediaCtx(msg.media_ctx as MediaContext);
        } else if (msg.type === 'reply_ended') {
          if (msg.bot_id && msg.reply_ts) {
            updateSetting('lastSeen', { ...settingsRef.current.lastSeen, [msg.bot_id]: msg.reply_ts });
          }
          setReplyBot(null);
          setProcessing(false);
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        if (wsRef.current === ws) {
          wsRef.current = null;
        }
        if (!shouldReconnectRef.current) return;
        reconnectTimerRef.current = setTimeout(connect, 2000);
      };
    }

    connect();
    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        const currentWs = wsRef.current;
        wsRef.current = null;
        currentWs.close();
      }
    };
  }, [addMessage, handleProactiveMessage, loadSpeakers, parseSpeedValue, playAudio, stopAudio, updateSetting, wsSend]);

  // --- Init: load settings, speakers, models ---
  useEffect(() => {
    (async () => {
      try {
        const resp = await fetch(`${API_BASE}/settings`);
        const saved = await resp.json();
        // Normalize legacy 'auto' speed to '1.0'
        for (const k of ['speedSelect', 'meiSpeed', 'eveSpeed'] as const) {
          if (saved[k] === 'auto') saved[k] = '1.0';
        }
        const merged = { ...DEFAULT_SETTINGS, ...saved };
        setSettings(prev => ({ ...prev, ...saved }));
        await loadSpeakers(merged.ttsEngine);
        // Load per-bot speakers if different engines
        for (const botId of ['mei', 'eve']) {
          const eng = merged[`${botId}Engine` as keyof EmberSettings] as string;
          if (eng && eng !== merged.ttsEngine) {
            const r = await fetch(`${API_BASE}/speakers?engine=${eng}`);
            const data: Speaker[] = await r.json();
            setBotSpeakers(prev => ({ ...prev, [botId]: data }));
          }
        }
      } catch {
        await loadSpeakers();
      }
      await loadModels();
    })();
  }, [loadSpeakers, loadModels]);


  // --- Thought trace polling (Debug mode only, #3 retro 2026-04-25) ---
  // When debugMode is on, poll /api/thought-trace every 30s and inject any
  // new entries as 'thought' diagnostic messages. lastSeen prevents replays.
  const lastThoughtTsRef = useRef<string | null>(null);
  useEffect(() => {
    if (!settings.debugMode) return;
    let cancelled = false;
    const fetchThoughts = async () => {
      try {
        const since = lastThoughtTsRef.current;
        const url = since
          ? `/api/thought-trace?days=1&since=${encodeURIComponent(since)}`
          : `/api/thought-trace?days=1`;
        const resp = await fetch(url);
        if (!resp.ok) return;
        const data = await resp.json();
        const entries: any[] = data.entries || [];
        if (cancelled) return;
        // Newest-first → reverse to chronological for in-order insertion
        const ordered = [...entries].reverse();
        for (const e of ordered) {
          // Skip on first load: just record the latest ts so we don't backfill
          // a week of thoughts into the chat. Only stream new ones going forward.
          if (since == null) continue;
          if (!e.timestamp) continue;
          if (lastThoughtTsRef.current && e.timestamp <= lastThoughtTsRef.current) continue;
          const summary = e.inner_thought
            ? e.inner_thought
            : e.type === 'skip'
              ? `見送り: ${e.reason || ''}`
              : e.type === 'send'
                ? '発話'
                : e.type;
          addMessage('', 'status', undefined, {
            kind: 'thought',
            label: 'inner thought',
            summary,
            timeLabel: e.timeDisplay,
            botId: e.bot,
            action: e.type === 'send' ? 'reply' : e.type === 'skip' ? 'skip' : 'unknown',
            reason: e.reason,
            thought: {
              innerThought: e.inner_thought,
              plan: e.plan,
              generateScore: e.generate_score,
              evaluateScore: e.evaluate_score,
              topic: e.message ? e.message.split('\n')[0].substring(0, 100) : undefined,
              category: e.category,
              modeEstimate: e.modeEstimate,
            },
            raw: JSON.stringify(e),
          });
        }
        if (entries.length > 0) {
          lastThoughtTsRef.current = entries[0].timestamp; // entries is newest-first
        } else if (since == null) {
          // Initialize watermark so future polls only return newer entries
          lastThoughtTsRef.current = new Date().toISOString();
        }
      } catch {
        // Silent fail — polling will retry
      }
    };
    fetchThoughts();
    const id = setInterval(fetchThoughts, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [settings.debugMode, addMessage]);

  // --- Send text ---
  const sendText = useCallback((text: string) => {
    if (!text.trim() || processing) return;
    if (replyBot) {
      const s = settingsRef.current;
      const speaker = replyBot === 'mei' ? s.meiVoice : s.eveVoice;
      const speed = replyBot === 'mei' ? s.meiSpeed : s.eveSpeed;
      wsSend({ type: 'slack_reply', bot_id: replyBot, speaker_id: /^\d+$/.test(speaker) ? parseInt(speaker) : speaker, speed: parseSpeedValue(speed) });
    }
    wsSend({ type: 'text_message', text: text.trim() });
    setProcessing(true);
  }, [parseSpeedValue, processing, replyBot, wsSend]);

  // --- Recording ---
  const startRecording = useCallback(async () => {
    try {
      if (!micStreamRef.current || !micStreamRef.current.active) {
        micStreamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      }
      const chunks: Blob[] = [];
      const recorder = new MediaRecorder(micStreamRef.current, { mimeType: 'audio/webm;codecs=opus' });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        const buf = await blob.arrayBuffer();
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) {
          if (replyBot) {
            const s = settingsRef.current;
            const speaker = replyBot === 'mei' ? s.meiVoice : s.eveVoice;
            const speed = replyBot === 'mei' ? s.meiSpeed : s.eveSpeed;
            wsSend({ type: 'slack_reply', bot_id: replyBot, speaker_id: /^\d+$/.test(speaker) ? parseInt(speaker) : speaker, speed: parseSpeedValue(speed) });
          }
          setProcessing(true);
          ws.send(buf);
        }
      };

      recorder.start();
      setRecording(true);
    } catch (err) {
      console.error('Mic error:', err);
    }
  }, [parseSpeedValue, replyBot, wsSend]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setRecording(false);
    }
  }, []);

  // --- Play bot message ---
  const playBotMessage = useCallback(async (botId: string) => {
    try {
      const textResp = await fetch(`${API_BASE}/bot-text/${botId}`);
      if (!textResp.ok) {
        addMessage(`[${botId}] メッセージが見つかりません`, 'status');
        return;
      }
      const { text, sentAt } = await textResp.json();
      addMessage(text, 'assistant', botId);
      setLastBotId(botId);
      updateSettings({ lastSeen: { ...settingsRef.current.lastSeen, [botId]: sentAt } });

      const s = settingsRef.current;
      const engine = botId === 'mei' ? (s.meiEngine || s.ttsEngine) : (s.eveEngine || s.ttsEngine);
      const speaker = botId === 'mei' ? s.meiVoice : s.eveVoice;
      const speed = botId === 'mei' ? s.meiSpeed : s.eveSpeed;
      const audioResp = await fetch(`${API_BASE}/bot-audio/${botId}?speaker=${speaker}&speed=${speed}&engine=${engine}`);
      if (!audioResp.ok) {
        const err = await audioResp.json().catch(() => ({ error: '音声生成に失敗しました' }));
        addMessage(`[${botId}] ${err.error}`, 'status');
        return;
      }
      const buf = await audioResp.arrayBuffer();
      playAudio(buf);
    } catch (err) {
      console.error(err);
    }
  }, [addMessage, playAudio, updateSettings]);

  // --- Preview voice ---
  const previewVoice = useCallback(async () => {
    try {
      const { voiceSelect: speaker, speedSelect: speed, ttsEngine } = settingsRef.current;
      const resp = await fetch(`${API_BASE}/preview?speaker=${speaker}&speed=${speed}&engine=${ttsEngine}`);
      const buf = await resp.arrayBuffer();
      playAudio(buf);
    } catch (err) {
      console.error(err);
    }
  }, [playAudio]);

  // --- Toggle reply ---
  const toggleReply = useCallback((botId: string | null) => {
    if (botId && botId === replyBot) {
      // Toggle off
      wsSend({ type: 'cancel_reply' });
      setReplyBot(null);
    } else if (botId) {
      const s = settingsRef.current;
      const speaker = botId === 'mei' ? s.meiVoice : s.eveVoice;
      const speed = botId === 'mei' ? s.meiSpeed : s.eveSpeed;
      wsSend({ type: 'slack_reply', bot_id: botId, speaker_id: /^\d+$/.test(speaker) ? parseInt(speaker) : speaker, speed: parseSpeedValue(speed) });
      setReplyBot(botId);
    }
  }, [parseSpeedValue, replyBot, wsSend]);

  return {
    // State
    messages, settings, speakers, botSpeakers, models,
    recording, processing, wsConnected,
    replyBot, lastBotId, settingsExpanded,
    contextSummary, mediaCtx,
    // Actions
    sendText, startRecording, stopRecording,
    updateSetting, updateSettings, loadSpeakers, handleBotEngineChange,
    stopAudio, playBotMessage, previewVoice,
    toggleReply, setSettingsExpanded,
    setReplyBot, setLastBotId,
    // Refs (for hook composition)
    wsRef,
  };
}
