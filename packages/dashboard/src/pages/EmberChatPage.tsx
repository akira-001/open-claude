// dashboard/src/pages/EmberChatPage.tsx
//
// Restored to mirror the legacy standalone Ember Chat Electron UI
// (packages/ember-chat/renderer/index.html). Uses dark ember-* tokens
// scoped via [data-ember-chat="true"] (see Layout.tsx + index.css).

import { useEffect, useState, useCallback, type CSSProperties } from 'react';
import { useNavigate } from 'react-router-dom';
import { getServerStatus, controlServer } from '../api';
import { useEmberChat } from '../components/ember-chat/useEmberChat';
import { useAlwaysOn } from '../components/ember-chat/useAlwaysOn';
import { useMeetingRecorder } from '../components/ember-chat/useMeetingRecorder';
import ChatMessages from '../components/ember-chat/ChatMessages';
import Titlebar from '../components/ember-chat/Titlebar';
import ServerStatusBar from '../components/ember-chat/ServerStatusBar';
import PlaybackModeBar from '../components/ember-chat/PlaybackModeBar';
import ChatToolbar from '../components/ember-chat/ChatToolbar';
import BotRow from '../components/ember-chat/BotRow';
import ChatControls from '../components/ember-chat/ChatControls';
import ImproveLoopPanel from '../components/ember-chat/ImproveLoopPanel';
import ContextSummaryPanel from '../components/ember-chat/ContextSummaryPanel';

interface ServiceStatus {
  whisper: boolean;
  voicevox: boolean;
  ollama: boolean;
}

const pageStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  flex: 1,
  minHeight: 0,
  minWidth: 0,
  width: '100%',
  background: 'var(--ember-bg)',
  color: 'var(--ember-text)',
  fontFamily: "-apple-system, 'Helvetica Neue', 'Segoe UI', sans-serif",
  overflow: 'hidden',
};

const textInputRowStyle: CSSProperties = {
  display: 'flex',
  gap: 8,
  padding: '10px 14px',
  background: 'var(--ember-surface)',
  borderTop: '1px solid var(--ember-border)',
};

const textInputStyle: CSSProperties = {
  flex: 1,
  background: 'var(--ember-input-bg)',
  color: 'var(--ember-text)',
  border: '1px solid var(--ember-border)',
  padding: '10px 14px',
  borderRadius: 20,
  fontSize: 14,
  outline: 'none',
  transition: 'border-color 0.15s',
};

const sendBtnStyle: CSSProperties = {
  background: 'var(--ember-gradient)',
  color: '#fff',
  border: 'none',
  padding: '10px 18px',
  borderRadius: 20,
  fontSize: 13,
  fontWeight: 700,
  cursor: 'pointer',
  transition: 'opacity 0.15s',
};

const fallbackPanelStyle: CSSProperties = {
  flex: 1,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: 24,
};

const settingsToggleStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '4px 14px',
  background: 'var(--ember-surface)',
  borderTop: '1px solid var(--ember-border)',
  color: 'var(--ember-text-dim)',
  fontSize: 10,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  cursor: 'pointer',
  userSelect: 'none',
};

const SETTINGS_COLLAPSED_KEY = 'ember-chat:settings-collapsed';

export default function EmberChatPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<ServiceStatus>({ whisper: false, voicevox: false, ollama: false });
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [settingsCollapsed, setSettingsCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(SETTINGS_COLLAPSED_KEY) === '1';
    } catch {
      return false;
    }
  });

  const toggleSettings = useCallback(() => {
    setSettingsCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SETTINGS_COLLAPSED_KEY, next ? '1' : '0');
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  const chat = useEmberChat();
  const alwaysOn = useAlwaysOn({ wsRef: chat.wsRef });
  const meetingRec = useMeetingRecorder();

  const refresh = useCallback(async () => {
    try {
      const ss = await getServerStatus();
      setStatus({
        whisper: ss.whisper?.running ?? false,
        voicevox: ss.voicevox?.running ?? false,
        ollama: ss.ollama?.running ?? false,
      });
    } catch {
      setStatus({ whisper: false, voicevox: false, ollama: false });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 10000);
    return () => clearInterval(interval);
  }, [refresh]);

  const handleStart = async (server: 'whisper' | 'voicevox' | 'ollama') => {
    setStarting(server);
    try {
      await controlServer(server, 'start');
      await new Promise((r) => setTimeout(r, server === 'whisper' ? 5000 : 3000));
      await refresh();
    } catch {
      // ignore
    } finally {
      setStarting(null);
    }
  };

  const handleSend = useCallback(() => {
    if (!text.trim() || chat.processing) return;
    chat.sendText(text);
    setText('');
  }, [text, chat]);

  const handleToggleTalk = useCallback(() => {
    if (chat.processing) return;
    if (chat.recording) chat.stopRecording();
    else chat.startRecording();
  }, [chat]);

  const handleToggleTts = useCallback(() => {
    const next = !chat.settings.ttsEnabled;
    chat.updateSetting('ttsEnabled', next);
    if (!next) chat.stopAudio();
  }, [chat]);

  const handleToggleProactive = useCallback(() => {
    chat.updateSetting('proactiveEnabled', !chat.settings.proactiveEnabled);
  }, [chat]);

  const handleToggleReply = useCallback(() => {
    chat.toggleReply(chat.lastBotId);
  }, [chat]);

  if (loading) {
    return (
      <div style={pageStyle}>
        <div style={fallbackPanelStyle}>
          <span style={{ color: 'var(--ember-text-dim)' }}>読み込み中...</span>
        </div>
      </div>
    );
  }

  return (
    <div style={pageStyle}>
      <Titlebar
        recording={meetingRec.recording}
        busy={meetingRec.busy}
        queueCount={meetingRec.queueCount}
        onToggleRecord={() => { void meetingRec.toggle(); }}
      />

      <ServerStatusBar
        whisperOnline={status.whisper}
        voicevoxOnline={status.voicevox}
        ollamaOnline={status.ollama}
        wsConnected={chat.wsConnected}
        alwaysOnState={alwaysOn.state}
        onToggleAlwaysOn={alwaysOn.toggle}
      />

      <PlaybackModeBar />

      {status.whisper ? (
        <>
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
            <ChatMessages messages={chat.messages} />
          </div>

          <div
            role="button"
            tabIndex={0}
            onClick={toggleSettings}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggleSettings();
              }
            }}
            style={settingsToggleStyle}
            aria-expanded={!settingsCollapsed}
            aria-controls="ember-chat-settings"
            title={settingsCollapsed ? '設定を開く' : '設定を閉じる'}
          >
            <span>Settings</span>
            <span style={{ fontSize: 12, lineHeight: 1 }}>{settingsCollapsed ? '▾' : '▴'}</span>
          </div>

          {!settingsCollapsed && (
            <div id="ember-chat-settings">
              <ChatToolbar
                modelValue={chat.settings.modelSelect}
                ambientModelValue={chat.settings.ambientModel ?? chat.settings.modelSelect}
                ttsEngineValue={chat.settings.ttsEngine}
                voiceValue={chat.settings.voiceSelect}
                speedValue={chat.settings.speedSelect}
                models={chat.models}
                speakers={chat.speakers}
                onModelChange={(v) => chat.updateSetting('modelSelect', v)}
                onAmbientModelChange={(v) => chat.updateSetting('ambientModel', v)}
                onTtsEngineChange={(v) => {
                  chat.updateSetting('ttsEngine', v);
                  chat.loadSpeakers(v);
                }}
                onVoiceChange={(v) => chat.updateSetting('voiceSelect', v)}
                onSpeedChange={(v) => chat.updateSetting('speedSelect', v)}
              />

              <BotRow
                botId="mei"
                voiceValue={chat.settings.meiVoice}
                speedValue={chat.settings.meiSpeed}
                speakers={chat.botSpeakers.mei ?? chat.speakers}
                onVoiceChange={(v) => chat.updateSetting('meiVoice', v)}
                onSpeedChange={(v) => chat.updateSetting('meiSpeed', v)}
                onPlay={() => chat.playBotMessage('mei')}
              />
              <BotRow
                botId="eve"
                voiceValue={chat.settings.eveVoice}
                speedValue={chat.settings.eveSpeed}
                speakers={chat.botSpeakers.eve ?? chat.speakers}
                onVoiceChange={(v) => chat.updateSetting('eveVoice', v)}
                onSpeedChange={(v) => chat.updateSetting('eveSpeed', v)}
                onPlay={() => chat.playBotMessage('eve')}
              />
            </div>
          )}

          {!settingsCollapsed && (
            <ChatControls
              recording={chat.recording}
              processing={chat.processing}
              ttsEnabled={chat.settings.ttsEnabled}
              proactiveEnabled={chat.settings.proactiveEnabled}
              replyMode={chat.replyBot !== null}
              replyBot={chat.replyBot}
              lastBotId={chat.lastBotId}
              debugOpen={chat.settings.debugMode}
              onStopAudio={() => chat.stopAudio()}
              onToggleProactive={handleToggleProactive}
              onToggleReply={handleToggleReply}
              onPreview={chat.previewVoice}
              onToggleTalk={handleToggleTalk}
              onToggleTts={handleToggleTts}
              onToggleDebug={() => chat.updateSetting('debugMode', !chat.settings.debugMode)}
              onOpenRecording={() => navigate('/voice-enroll')}
            />
          )}

          <ImproveLoopPanel open={chat.settings.debugMode} />
          <ContextSummaryPanel open={chat.settings.debugMode} externalSummary={chat.contextSummary} mediaCtx={chat.mediaCtx} />

          <div style={textInputRowStyle}>
            <input
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.nativeEvent.isComposing && e.keyCode !== 229) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Type a message..."
              autoComplete="off"
              style={textInputStyle}
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={chat.processing || !text.trim()}
              style={{
                ...sendBtnStyle,
                opacity: chat.processing || !text.trim() ? 0.4 : 1,
                cursor: chat.processing || !text.trim() ? 'not-allowed' : 'pointer',
              }}
            >
              Send
            </button>
          </div>

          {alwaysOn.consentRequired && (
            <ConsentDialog
              onAccept={alwaysOn.acceptConsent}
              onDecline={alwaysOn.declineConsent}
            />
          )}
        </>
      ) : (
        <div style={fallbackPanelStyle}>
          <div style={{ textAlign: 'center', maxWidth: 360 }}>
            <div style={{ fontSize: 40, marginBottom: 12, opacity: 0.5 }}>&#x1F525;</div>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8, color: 'var(--ember-text)' }}>
              Ember Chat
            </h3>
            <p style={{ fontSize: 13, color: 'var(--ember-text-muted)', marginBottom: 16 }}>
              音声会話を開始するには、以下のサービスを起動してください。
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' }}>
              {(['Whisper', 'VOICEVOX', 'Ollama'] as const)
                .filter((svc) => !status[svc.toLowerCase() as keyof ServiceStatus])
                .map((svc) => {
                  const key = svc.toLowerCase() as 'whisper' | 'voicevox' | 'ollama';
                  return (
                    <button
                      key={svc}
                      type="button"
                      onClick={() => handleStart(key)}
                      disabled={starting !== null}
                      style={{
                        padding: '10px 18px',
                        borderRadius: 8,
                        fontSize: 13,
                        fontWeight: 600,
                        background: 'rgba(249, 115, 22, 0.18)',
                        color: 'var(--ember-primary)',
                        border: '1px solid rgba(249, 115, 22, 0.5)',
                        cursor: starting !== null ? 'not-allowed' : 'pointer',
                        opacity: starting !== null ? 0.4 : 1,
                        minWidth: 200,
                      }}
                    >
                      {starting === key ? `${svc} を起動中...` : `${svc} を起動`}
                    </button>
                  );
                })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface ConsentDialogProps {
  onAccept: () => void;
  onDecline: () => void;
}

function ConsentDialog({ onAccept, onDecline }: ConsentDialogProps) {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'rgba(0,0,0,0.85)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          background: 'var(--ember-surface)',
          borderRadius: 16,
          padding: 32,
          maxWidth: 360,
          textAlign: 'center',
          color: 'var(--ember-text)',
        }}
      >
        <div style={{ fontSize: 32, marginBottom: 16 }}>🎙</div>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>Always-On Listening</h2>
        <p
          style={{
            fontSize: 13,
            color: 'var(--ember-text-muted)',
            lineHeight: 1.6,
            marginBottom: 20,
          }}
        >
          Ember Chat は常時マイクを使用して音声を監視します。
          <br />
          音声はローカルでのみ処理され、外部に送信されません。
        </p>
        <button
          type="button"
          onClick={onAccept}
          style={{
            background: 'var(--ember-gradient)',
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            padding: '10px 24px',
            fontSize: 14,
            cursor: 'pointer',
            marginRight: 8,
          }}
        >
          許可する
        </button>
        <button
          type="button"
          onClick={onDecline}
          style={{
            background: 'var(--ember-border)',
            color: 'var(--ember-text-muted)',
            border: 'none',
            borderRadius: 8,
            padding: '10px 24px',
            fontSize: 14,
            cursor: 'pointer',
          }}
        >
          後で
        </button>
      </div>
    </div>
  );
}
