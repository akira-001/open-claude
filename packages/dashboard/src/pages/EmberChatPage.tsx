// dashboard/src/pages/EmberChatPage.tsx
import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { getServerStatus, controlServer } from '../api';
import { useEmberChat } from '../components/ember-chat/useEmberChat';
import ChatMessages from '../components/ember-chat/ChatMessages';
import ChatInput from '../components/ember-chat/ChatInput';
import ChatSettings from '../components/ember-chat/ChatSettings';
import DebugPanel from '../components/ember-chat/DebugPanel';

interface ServiceStatus {
  whisper: boolean;
  voicevox: boolean;
  ollama: boolean;
}

export default function EmberChatPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<ServiceStatus>({ whisper: false, voicevox: false, ollama: false });
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState<string | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);

  const chat = useEmberChat();

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

  if (loading) {
    return <div className="text-[var(--text-dim)] p-6">読み込み中...</div>;
  }

  return (
    <div className="flex flex-col -m-4 md:-m-8 md:-mt-8" style={{ height: 'calc(100vh - 0px)' }}>
      {/* Status bar */}
      <div className="flex items-center gap-4 px-4 py-2 bg-[var(--surface)] border-b border-[var(--border)] flex-shrink-0">
        <h2 className="text-sm font-semibold text-[var(--text)]">Ember Chat</h2>
        <div className="flex items-center gap-4 ml-4">
          {(['whisper', 'voicevox', 'ollama'] as const).map((svc) => (
            <span key={svc} className="flex items-center gap-1.5 text-xs">
              <span className={`inline-block w-2 h-2 rounded-full ${status[svc] ? 'bg-[var(--success)]' : 'bg-[var(--error)]'}`} />
              <span className="text-[var(--text-dim)] capitalize">{svc === 'voicevox' ? 'VOICEVOX' : svc.charAt(0).toUpperCase() + svc.slice(1)}</span>
              {!status[svc] && (
                <button
                  onClick={() => handleStart(svc)}
                  disabled={starting !== null}
                  className="px-2 py-0.5 rounded text-[10px] font-medium border border-[var(--border)] text-[var(--text-dim)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-colors disabled:opacity-40"
                >
                  {starting === svc ? '...' : 'Start'}
                </button>
              )}
            </span>
          ))}
        </div>
        {chat.wsConnected && (
          <span className="ml-auto text-[10px] text-[var(--success)]">Connected</span>
        )}
      </div>

      {/* Main content */}
      {status.whisper ? (
        <>
          <ChatMessages messages={chat.messages} />

          {/* Settings panel (collapsible) */}
          {chat.settingsExpanded && (
            <ChatSettings
              settings={chat.settings}
              speakers={chat.speakers}
              botSpeakers={chat.botSpeakers}
              models={chat.models}
              onUpdateSetting={chat.updateSetting}
              onUpdateSettings={chat.updateSettings}
              onLoadSpeakers={chat.loadSpeakers}
              onBotEngineChange={chat.handleBotEngineChange}
              onPreview={chat.previewVoice}
              onStopAudio={chat.stopAudio}
              onPlayBot={chat.playBotMessage}
            />
          )}

          <ChatInput
            onSendText={chat.sendText}
            onStartRecording={chat.startRecording}
            onStopRecording={chat.stopRecording}
            recording={chat.recording}
            processing={chat.processing}
            replyBot={chat.replyBot}
            lastBotId={chat.lastBotId}
            onToggleReply={chat.toggleReply}
            onPlayBot={chat.playBotMessage}
            ttsEnabled={chat.settings.ttsEnabled}
            onToggleTts={() => {
              const next = !chat.settings.ttsEnabled;
              chat.updateSetting('ttsEnabled', next);
              if (!next) chat.stopAudio();
            }}
            onToggleSettings={() => chat.setSettingsExpanded(!chat.settingsExpanded)}
            settingsExpanded={chat.settingsExpanded}
            onOpenRecording={() => navigate('/voice-enroll')}
          />

          <DebugPanel
            open={debugOpen}
            onToggle={() => setDebugOpen((v) => !v)}
          />
        </>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <div className="text-5xl mb-4 opacity-40">&#x1F525;</div>
            <h3 className="text-lg font-semibold text-[var(--text)] mb-2">Ember Chat</h3>
            <p className="text-sm text-[var(--text-dim)] mb-4">
              音声会話を開始するには、以下のサービスを起動してください。
            </p>
            <div className="flex flex-col gap-2 items-center">
              {['Whisper', 'VOICEVOX', 'Ollama'].filter(svc => !status[svc.toLowerCase() as keyof ServiceStatus]).map((svc) => {
                const key = svc.toLowerCase() as 'whisper' | 'voicevox' | 'ollama';
                return (
                  <button
                    key={svc}
                    onClick={() => handleStart(key)}
                    disabled={starting !== null}
                    className="px-4 py-2 rounded-lg text-sm font-medium bg-[var(--accent)]/20 text-[var(--accent)] border border-[var(--accent)]/30 hover:bg-[var(--accent)]/30 transition-colors disabled:opacity-40 min-w-[200px]"
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
