import type { CSSProperties } from 'react';

interface TitlebarProps {
  recording: boolean;
  busy: boolean;
  queueCount?: number;
  onToggleRecord: () => void;
}

const containerStyle: CSSProperties = {
  height: 38,
  background: 'var(--ember-surface)',
  borderBottom: '1px solid var(--ember-border)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  flexShrink: 0,
  position: 'relative',
  WebkitAppRegion: 'drag',
} as CSSProperties;

const logoStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 2,
  fontSize: 13,
  fontWeight: 700,
  letterSpacing: '0.04em',
  color: 'var(--ember-primary)',
};

const queueBadgeStyle: CSSProperties = {
  position: 'absolute',
  right: 78,
  top: '50%',
  transform: 'translateY(-50%)',
  background: 'rgba(249, 115, 22, 0.18)',
  border: '1px solid rgba(249, 115, 22, 0.5)',
  color: '#fed7aa',
  fontSize: 10,
  fontWeight: 600,
  padding: '2px 7px',
  borderRadius: 10,
  letterSpacing: '0.02em',
  pointerEvents: 'none',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
};

function recordControlStyle(recording: boolean, busy: boolean): CSSProperties {
  const base = {
    position: 'absolute',
    right: 12,
    top: '50%',
    transform: 'translateY(-50%)',
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    border: '1px solid var(--ember-border)',
    color: 'var(--ember-text-muted)',
    background: 'transparent',
    borderRadius: 14,
    padding: '3px 9px 3px 7px',
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: '0.05em',
    cursor: 'pointer',
    transition: 'background 0.15s, color 0.15s, border-color 0.15s',
    WebkitAppRegion: 'no-drag',
  } as CSSProperties;
  if (recording) {
    return {
      ...base,
      background: 'rgba(239, 68, 68, 0.12)',
      borderColor: 'rgba(239, 68, 68, 0.55)',
      color: '#fecaca',
    };
  }
  if (busy) {
    return {
      ...base,
      background: 'rgba(249, 115, 22, 0.10)',
      borderColor: 'rgba(249, 115, 22, 0.45)',
      color: '#fed7aa',
    };
  }
  return base;
}

function recDotStyle(recording: boolean, busy: boolean): CSSProperties {
  return {
    width: 8,
    height: 8,
    borderRadius: '50%',
    background: busy ? 'var(--ember-primary)' : 'var(--ember-danger)',
    opacity: recording || busy ? 1 : 0.55,
    flexShrink: 0,
    animation: recording
      ? 'ember-rec-pulse 1.1s ease-in-out infinite'
      : busy
        ? 'ember-rec-pulse 0.8s ease-in-out infinite'
        : 'none',
  };
}

const FLAME_SVG = (
  <svg
    width={24}
    height={20}
    viewBox="56 20 144 212"
    xmlns="http://www.w3.org/2000/svg"
    style={{ flexShrink: 0 }}
  >
    <defs>
      <linearGradient id="ember-lo" x1="0.5" y1="1" x2="0.5" y2="0">
        <stop offset="0%" stopColor="#dc2626" />
        <stop offset="40%" stopColor="#ea580c" />
        <stop offset="70%" stopColor="#f97316" />
        <stop offset="100%" stopColor="#fb923c" />
      </linearGradient>
      <linearGradient id="ember-lm" x1="0.5" y1="1" x2="0.5" y2="0">
        <stop offset="0%" stopColor="#ea580c" />
        <stop offset="50%" stopColor="#f97316" />
        <stop offset="100%" stopColor="#fdba74" />
      </linearGradient>
      <linearGradient id="ember-li" x1="0.5" y1="1" x2="0.5" y2="0">
        <stop offset="0%" stopColor="#f97316" />
        <stop offset="40%" stopColor="#fbbf24" />
        <stop offset="100%" stopColor="#fde68a" />
      </linearGradient>
      <linearGradient id="ember-lc" x1="0.5" y1="1" x2="0.5" y2="0">
        <stop offset="0%" stopColor="#fbbf24" />
        <stop offset="100%" stopColor="#fef3c7" />
      </linearGradient>
    </defs>
    <path d="M128 28C128 28 188 80 192 140C194 165 182 192 164 208C158 213 148 220 128 224C108 220 98 213 92 208C74 192 62 165 64 140C68 80 128 28 128 28Z" fill="url(#ember-lo)" />
    <path d="M128 60C128 60 172 104 174 148C175 168 166 190 152 204C144 210 136 216 128 218C120 216 112 210 104 204C90 190 81 168 82 148C84 104 128 60 128 60Z" fill="url(#ember-lm)" />
    <path d="M128 96C128 96 158 128 160 158C161 172 154 190 144 200C140 204 134 208 128 210C122 208 116 204 112 200C102 190 95 172 96 158C98 128 128 96 128 96Z" fill="url(#ember-li)" />
    <path d="M128 140C128 140 146 158 146 174C146 184 140 196 134 202C132 204 130 206 128 206C126 206 124 204 122 202C116 196 110 184 110 174C110 158 128 140 128 140Z" fill="url(#ember-lc)" />
  </svg>
);

const KEYFRAMES = `
@keyframes ember-rec-pulse {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.55); }
  50% { transform: scale(1.18); box-shadow: 0 0 0 6px rgba(239, 68, 68, 0); }
}
`;

export default function Titlebar({ recording, busy, queueCount, onToggleRecord }: TitlebarProps) {
  return (
    <div style={containerStyle}>
      <style>{KEYFRAMES}</style>
      <div style={logoStyle}>
        {FLAME_SVG}
        EMBER CHAT
      </div>
      {queueCount && queueCount > 0 ? (
        <span style={queueBadgeStyle} title="文字起こし待ちのファイル数">
          <span
            style={{
              display: 'inline-block',
              width: 5,
              height: 5,
              borderRadius: '50%',
              background: 'var(--ember-primary)',
              animation: 'ember-rec-pulse 1.2s ease-in-out infinite',
            }}
          />
          {queueCount}
        </span>
      ) : null}
      <button
        type="button"
        onClick={onToggleRecord}
        title="会議録音 (webm/Opus)"
        aria-label="会議録音"
        style={recordControlStyle(recording, busy)}
      >
        <span style={recDotStyle(recording, busy)} />
        <span>{recording ? 'REC' : busy ? 'BUSY' : 'REC'}</span>
      </button>
    </div>
  );
}
