import type { CSSProperties } from 'react';
import type { Speaker, OllamaModel } from './types';

interface ChatToolbarProps {
  modelValue: string;
  ambientModelValue: string;
  ttsEngineValue: string;
  voiceValue: string;
  speedValue: string;
  models: OllamaModel[];
  speakers: Speaker[];
  speedOptions?: string[];
  onModelChange: (value: string) => void;
  onAmbientModelChange: (value: string) => void;
  onTtsEngineChange: (value: string) => void;
  onVoiceChange: (value: string) => void;
  onSpeedChange: (value: string) => void;
}

const DEFAULT_SPEEDS = ['0.8', '1.0', '1.2', '1.5', '2.0'];

const containerStyle: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 8,
  padding: '8px 14px',
  background: 'var(--ember-surface)',
  borderTop: '1px solid var(--ember-border)',
  alignItems: 'center',
};

const labelStyle: CSSProperties = {
  color: 'var(--ember-text-dim)',
  fontSize: 10,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
};

const selectStyle: CSSProperties = {
  background: 'var(--ember-input-bg)',
  color: 'var(--ember-text-muted)',
  border: '1px solid var(--ember-border)',
  borderRadius: 6,
  padding: '6px 8px',
  fontSize: 12,
  outline: 'none',
  maxWidth: 140,
  minWidth: 0,
  flexShrink: 1,
};

export default function ChatToolbar({
  modelValue,
  ambientModelValue,
  ttsEngineValue,
  voiceValue,
  speedValue,
  models,
  speakers,
  speedOptions = DEFAULT_SPEEDS,
  onModelChange,
  onAmbientModelChange,
  onTtsEngineChange,
  onVoiceChange,
  onSpeedChange,
}: ChatToolbarProps) {
  return (
    <div style={containerStyle}>
      <span style={labelStyle}>Model</span>
      <select
        value={modelValue}
        onChange={(e) => onModelChange(e.target.value)}
        style={selectStyle}
      >
        {models.map((m) => (
          <option key={m.name} value={m.name}>
            {m.name} {m.size ? `(${m.size})` : ''}
          </option>
        ))}
      </select>

      <span style={labelStyle}>Ambient</span>
      <select
        value={ambientModelValue}
        onChange={(e) => onAmbientModelChange(e.target.value)}
        style={selectStyle}
      >
        {models.map((m) => (
          <option key={m.name} value={m.name}>
            {m.name} {m.size ? `(${m.size})` : ''}
          </option>
        ))}
      </select>

      <span style={labelStyle}>TTS</span>
      <select
        value={ttsEngineValue}
        onChange={(e) => onTtsEngineChange(e.target.value)}
        style={selectStyle}
      >
        <option value="voicevox">VOICEVOX</option>
        <option value="irodori">Irodori</option>
      </select>

      <span style={labelStyle}>Voice</span>
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

      <span style={labelStyle}>Speed</span>
      <select
        value={speedValue}
        onChange={(e) => onSpeedChange(e.target.value)}
        style={selectStyle}
      >
        {speedOptions.map((s) => (
          <option key={s} value={s}>{s}x</option>
        ))}
      </select>
    </div>
  );
}
