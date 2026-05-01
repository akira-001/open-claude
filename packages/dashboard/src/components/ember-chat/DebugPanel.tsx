// dashboard/src/components/ember-chat/DebugPanel.tsx
import { useCallback, useEffect, useRef, useState } from 'react';

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

function reactivityNote(level: number): string {
  if (level >= 5) return '→ media_likely でも co_view 発動';
  if (level <= 1) return '→ ほぼ反応しない';
  return '→ user発話のみ反応';
}

function nextTimeLabel(spanMin: number): string {
  const t = new Date(Date.now() + spanMin * 60_000);
  return `${t.getHours()}:${String(t.getMinutes()).padStart(2, '0')}`;
}

export interface DebugPanelProps {
  open: boolean;
  onToggle: () => void;
}

export default function DebugPanel({ open, onToggle }: DebugPanelProps) {
  // --- Improve loop state ---
  const [loopEnabled, setLoopEnabled] = useState(false);
  const [spanMin, setSpanMin] = useState(60);
  const [autoApprove, setAutoApprove] = useState(false);
  const [loopStatus, setLoopStatus] = useState('');

  // --- Reactivity state ---
  const [reactivity, setReactivity] = useState(4);

  // --- Refs for loop timer ---
  const loopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loopEnabledRef = useRef(loopEnabled);
  const spanMinRef = useRef(spanMin);

  useEffect(() => { loopEnabledRef.current = loopEnabled; }, [loopEnabled]);
  useEffect(() => { spanMinRef.current = spanMin; }, [spanMin]);

  // --- Init: load state from server when panel opens ---
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
        // ignore — server may not be running
      }
    })();
  }, [open]);

  // --- Schedule loop ---
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

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (loopTimerRef.current) clearTimeout(loopTimerRef.current);
    };
  }, []);

  // --- Handlers ---
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
    } catch {
      // ignore
    }
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
    if (next) {
      setLoopStatus('自動承認モード');
    } else if (!loopEnabled) {
      setLoopStatus('');
    }
    try {
      await fetch(`${API_BASE}/improve_loop/auto_approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next }),
      });
    } catch {
      // ignore
    }
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
    } catch {
      // ignore
    }
  }, []);

  return (
    <div className="flex-shrink-0 border-t border-[var(--border)]">
      {/* Debug toggle button row */}
      <div className="flex items-center gap-2 px-4 py-1.5">
        <button
          onClick={onToggle}
          className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${
            open
              ? 'border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10'
              : 'border-[var(--border)] text-[var(--text-dim)] hover:text-[var(--accent)] hover:border-[var(--accent)]'
          }`}
        >
          {open ? 'Debug ON' : 'Debug'}
        </button>
      </div>

      {/* Improve Loop panel (only when open) */}
      {open && (
        <div className="flex flex-wrap items-center gap-2 px-4 pb-2">
          {/* Loop toggle */}
          <button
            onClick={handleToggleLoop}
            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${
              loopEnabled
                ? 'border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10'
                : 'border-[var(--border)] text-[var(--text-dim)] hover:text-[var(--accent)] hover:border-[var(--accent)]'
            }`}
          >
            {loopEnabled ? 'Loop ON' : 'Loop OFF'}
          </button>

          {/* Span select */}
          <select
            value={spanMin}
            onChange={handleSpanChange}
            className="px-1.5 py-0.5 rounded text-[11px] border border-[var(--border)] bg-[var(--surface)] text-[var(--text-dim)] focus:outline-none focus:border-[var(--accent)]"
          >
            {SPAN_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          {/* Auto approve toggle */}
          <button
            onClick={handleToggleAutoApprove}
            className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${
              autoApprove
                ? 'border-[var(--success)] text-[var(--success)] bg-[var(--success)]/10'
                : 'border-[var(--border)] text-[var(--text-dim)] hover:text-[var(--success)] hover:border-[var(--success)]'
            }`}
          >
            {autoApprove ? '自動承認 ON' : '自動承認 OFF'}
          </button>

          {/* Loop status */}
          {loopStatus && (
            <span className="text-[11px] text-[var(--text-dim)]">{loopStatus}</span>
          )}

          {/* Separator */}
          <span className="text-[var(--border)] text-[11px] select-none">|</span>

          {/* Reactivity label + select */}
          <span
            className="text-[11px] text-[var(--text-dim)]"
            title="1=最小, 5=おしゃべりモード"
          >
            Reactivity
          </span>
          <select
            value={reactivity}
            onChange={handleReactivityChange}
            className="px-1.5 py-0.5 rounded text-[11px] border border-[var(--border)] bg-[var(--surface)] text-[var(--text-dim)] focus:outline-none focus:border-[var(--accent)]"
          >
            {REACTIVITY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          {/* Reactivity note */}
          <span className="text-[10px] text-[var(--text-dim)] opacity-70">
            {reactivityNote(reactivity)}
          </span>
        </div>
      )}
    </div>
  );
}
