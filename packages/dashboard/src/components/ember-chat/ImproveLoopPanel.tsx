import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';

const API_BASE = '/whisper/api';

const SPAN_OPTIONS = [
  { value: 30, label: '30分' },
  { value: 60, label: '1時間' },
  { value: 120, label: '2時間' },
];

const REACTIVITY_OPTIONS = [
  { value: 1, label: '1 静か' },
  { value: 2, label: '2' },
  { value: 3, label: '3' },
  { value: 4, label: '4 標準' },
  { value: 5, label: '5 おしゃべり' },
];

function nextTimeLabel(spanMin: number): string {
  const t = new Date(Date.now() + spanMin * 60_000);
  return `${t.getHours()}:${String(t.getMinutes()).padStart(2, '0')}`;
}

export interface ImproveLoopPanelProps {
  open: boolean;
}

const containerStyle: CSSProperties = {
  padding: '4px 8px',
  background: '#1a1a1a',
  borderTop: '1px solid #333',
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  flexWrap: 'wrap',
};

const labelStyle: CSSProperties = {
  color: 'var(--ember-text-dim)',
  fontSize: 11,
};

const sideBtnStyle: CSSProperties = {
  background: 'none',
  border: '1px solid var(--ember-border)',
  color: 'var(--ember-text-muted)',
  padding: '2px 8px',
  borderRadius: 6,
  cursor: 'pointer',
  fontSize: 11,
  fontWeight: 500,
  transition: 'all 0.15s',
};

const onStyle: CSSProperties = {
  borderColor: 'var(--ember-primary)',
  color: 'var(--ember-primary)',
};

const successOnStyle: CSSProperties = {
  borderColor: 'var(--ember-success)',
  color: 'var(--ember-success)',
};

const selectStyle: CSSProperties = {
  background: '#222',
  color: '#ccc',
  border: '1px solid #444',
  borderRadius: 4,
  fontSize: 11,
  padding: '2px 4px',
};

const statusStyle: CSSProperties = {
  color: '#666',
  fontSize: 11,
};

const sepStyle: CSSProperties = {
  color: '#444',
  fontSize: 11,
};

export default function ImproveLoopPanel({ open }: ImproveLoopPanelProps) {
  const [loopEnabled, setLoopEnabled] = useState(false);
  const [spanMin, setSpanMin] = useState(60);
  const [autoApprove, setAutoApprove] = useState(false);
  const [loopStatus, setLoopStatus] = useState('');
  const [reactivity, setReactivity] = useState(4);

  const loopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loopEnabledRef = useRef(loopEnabled);
  const spanMinRef = useRef(spanMin);

  useEffect(() => { loopEnabledRef.current = loopEnabled; }, [loopEnabled]);
  useEffect(() => { spanMinRef.current = spanMin; }, [spanMin]);

  useEffect(() => {
    if (!open) return;
    (async () => {
      try {
        const [stateRes, aaRes, settingsRes] = await Promise.all([
          fetch(`${API_BASE}/improve_loop/state`),
          fetch(`${API_BASE}/improve_loop/auto_approve`),
          fetch(`${API_BASE}/settings`),
        ]);
        const stateData = await stateRes.json();
        const aaData = await aaRes.json();
        const settingsData = await settingsRes.json();

        setLoopEnabled(stateData.enabled ?? false);
        setAutoApprove(aaData.enabled ?? false);
        const r = settingsData.ambient_reactivity ?? settingsData.ambientReactivity ?? 4;
        setReactivity(r);
        const spanFromSettings = settingsData.improveLoopSpanMin ?? 60;
        setSpanMin(spanFromSettings);
      } catch {
        // ignore
      }
    })();
  }, [open]);

  const scheduleLoop = useCallback((currentSpanMin: number) => {
    if (loopTimerRef.current) clearTimeout(loopTimerRef.current);
    loopTimerRef.current = setTimeout(async () => {
      if (!loopEnabledRef.current) return;
      setLoopStatus('分析中...');
      try {
        await fetch(`${API_BASE}/improve_loop/run`, { method: 'POST' });
        setLoopStatus(`実行済 | 次回: ${nextTimeLabel(spanMinRef.current)}`);
      } catch {
        setLoopStatus('エラー');
      }
      scheduleLoop(spanMinRef.current);
    }, currentSpanMin * 60 * 1000);
  }, []);

  useEffect(() => () => {
    if (loopTimerRef.current) clearTimeout(loopTimerRef.current);
  }, []);

  const handleToggleLoop = useCallback(async () => {
    const next = !loopEnabled;
    setLoopEnabled(next);
    loopEnabledRef.current = next;
    if (next) {
      scheduleLoop(spanMin);
      setLoopStatus(`次回: ${nextTimeLabel(spanMin)}`);
    } else {
      if (loopTimerRef.current) clearTimeout(loopTimerRef.current);
      setLoopStatus('');
    }
    try {
      await fetch(`${API_BASE}/improve_loop/state`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next }),
      });
    } catch {}
  }, [loopEnabled, spanMin, scheduleLoop]);

  const handleSpanChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = parseInt(e.target.value, 10);
    setSpanMin(next);
    spanMinRef.current = next;
    if (loopEnabled) {
      if (loopTimerRef.current) clearTimeout(loopTimerRef.current);
      scheduleLoop(next);
      setLoopStatus(`次回: ${nextTimeLabel(next)}`);
    }
  }, [loopEnabled, scheduleLoop]);

  const handleToggleAutoApprove = useCallback(async () => {
    const next = !autoApprove;
    setAutoApprove(next);
    if (next) setLoopStatus('自動承認モード');
    else if (!loopEnabled) setLoopStatus('');
    try {
      await fetch(`${API_BASE}/improve_loop/auto_approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next }),
      });
    } catch {}
  }, [autoApprove, loopEnabled]);

  const handleReactivityChange = useCallback(async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = parseInt(e.target.value, 10);
    setReactivity(next);
    try {
      await fetch(`${API_BASE}/ambient/reactivity`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level: next }),
      });
    } catch {}
  }, []);

  if (!open) return null;

  return (
    <div style={containerStyle}>
      <span style={labelStyle}>改善ループ</span>
      <button
        type="button"
        onClick={handleToggleLoop}
        style={loopEnabled ? { ...sideBtnStyle, ...onStyle } : sideBtnStyle}
      >
        {loopEnabled ? 'Loop ON' : 'Loop OFF'}
      </button>
      <select value={spanMin} onChange={handleSpanChange} style={selectStyle}>
        {SPAN_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <button
        type="button"
        onClick={handleToggleAutoApprove}
        title="自動承認: Slackの👍なしで自動適用"
        style={autoApprove ? { ...sideBtnStyle, ...successOnStyle } : sideBtnStyle}
      >
        {autoApprove ? '自動承認 ON' : '自動承認 OFF'}
      </button>
      {loopStatus && <span style={statusStyle}>{loopStatus}</span>}
      <span style={sepStyle}>|</span>
      <span style={labelStyle} title="1=最小, 5=おしゃべりモード(media_likelyでもco_view)">
        Reactivity
      </span>
      <select value={reactivity} onChange={handleReactivityChange} style={selectStyle}>
        {REACTIVITY_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <span style={statusStyle}>{reactivityNote(reactivity)}</span>
    </div>
  );
}

function reactivityNote(level: number): string {
  if (level >= 5) return '→ media_likely でも co_view 発動';
  if (level <= 1) return '→ ほぼ反応しない';
  return '→ user発話のみ反応';
}
