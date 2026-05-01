import type { CSSProperties } from 'react';
import type { Speaker } from './types';

interface BotRowProps {
  botId: 'mei' | 'eve';
  voiceValue: string;
  speedValue: string;
  speakers: Speaker[];
  speedOptions?: string[];
  onVoiceChange: (value: string) => void;
  onSpeedChange: (value: string) => void;
  onPlay: () => void;
  playDisabled?: boolean;
  sessionError?: string;
}

const DEFAULT_SPEEDS = ['0.8', '1.0', '1.2', '1.5', '2.0'];

const containerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '6px 14px',
  background: 'var(--ember-surface)',
  borderBottom: '1px solid var(--ember-border)',
};

const nameStyle: CSSProperties = {
  color: 'var(--ember-primary)',
  fontSize: 12,
  fontWeight: 700,
  minWidth: 28,
};

const selectStyle: CSSProperties = {
  background: 'var(--ember-input-bg)',
  color: 'var(--ember-text-muted)',
  border: '1px solid var(--ember-border)',
  borderRadius: 6,
  padding: '5px 6px',
  fontSize: 11,
  outline: 'none',
  maxWidth: 140,
  minWidth: 0,
  flexShrink: 1,
};

const playStyle: CSSProperties = {
  background: 'none',
  border: '1px solid var(--ember-primary)',
  color: 'var(--ember-primary)',
  padding: '5px 12px',
  borderRadius: 6,
  cursor: 'pointer',
  fontSize: 11,
  fontWeight: 600,
  transition: 'all 0.15s',
};

const errorStyle: CSSProperties = {
  marginLeft: 'auto',
  fontSize: 11,
  color: '#ff6b6b',
  background: 'rgba(255,107,107,0.12)',
  border: '1px solid rgba(255,107,107,0.35)',
  borderRadius: 4,
  padding: '2px 6px',
  whiteSpace: 'nowrap',
};

export default function BotRow({
  botId,
  voiceValue,
  speedValue,
  speakers,
  speedOptions = DEFAULT_SPEEDS,
  onVoiceChange,
  onSpeedChange,
  onPlay,
  playDisabled,
  sessionError,
}: BotRowProps) {
  const label = botId === 'mei' ? 'Mei' : 'Eve';

  return (
    <div style={containerStyle}>
      <span style={nameStyle}>{label}</span>
      <select
        value={voiceValue}
        onChange={(e) => onVoiceChange(e.target.value)}
        style={selectStyle}
      >
        {speakers.flatMap((spk) =>
          spk.styles.map((st) => (
            <option key={`${spk.name}-${st.id}`} value={String(st.id)}>
              {spk.name} - {st.name}
            </option>
          ))
        )}
      </select>
      <select
        value={speedValue}
        onChange={(e) => onSpeedChange(e.target.value)}
        style={selectStyle}
      >
        {speedOptions.map((s) => (
          <option key={s} value={s}>{s}x</option>
        ))}
      </select>
      <button
        type="button"
        onClick={onPlay}
        disabled={playDisabled}
        style={{ ...playStyle, opacity: playDisabled ? 0.4 : 1 }}
      >
        Play
      </button>
      {sessionError && <span style={errorStyle}>{sessionError}</span>}
    </div>
  );
}
