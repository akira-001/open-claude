import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import type { ContextSummary, MediaContext } from './types';

const API_BASE = '/whisper/api';
const COLLAPSED_KEY = 'ember-chat:context-summary-collapsed';

interface ContextSummaryPanelProps {
  open: boolean;
  externalSummary?: ContextSummary | null;
  mediaCtx?: MediaContext | null;
}

type FieldKey = 'activity' | 'topic' | 'is_meeting' | 'keywords' | 'named_entities' | 'mood' | 'location' | 'time_context';

const containerStyle: CSSProperties = {
  position: 'relative',
  padding: '6px 42px 6px 10px',
  background: '#16181f',
  borderTop: '1px solid #2a2f3a',
  color: '#cfd6e4',
  fontSize: 11,
};

const headerRowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  flexWrap: 'wrap',
  marginBottom: 4,
};

const labelStyle: CSSProperties = { color: '#888' };

const buttonStyle: CSSProperties = {
  borderRadius: 4,
  padding: '3px 10px',
  cursor: 'pointer',
  fontSize: 11,
  border: '1px solid',
};

const yesStyle: CSSProperties = {
  ...buttonStyle,
  background: '#1f5d3a',
  color: '#dff5e3',
  borderColor: '#2c8a55',
};

const noStyle: CSSProperties = {
  ...buttonStyle,
  background: '#5d1f1f',
  color: '#f5dada',
  borderColor: '#8a2c2c',
};

const inputStyle: CSSProperties = {
  background: '#222',
  color: '#ccc',
  border: '1px solid #444',
  borderRadius: 3,
  padding: '2px 4px',
  fontSize: 11,
};

const chipStyle: CSSProperties = {
  ...buttonStyle,
  background: '#2a2f3a',
  color: '#888',
  borderColor: '#3a4050',
  padding: '1px 7px',
  fontSize: 10,
};

const chipActiveStyle: CSSProperties = {
  ...buttonStyle,
  background: '#4a2e10',
  color: '#ffc97d',
  borderColor: '#8a5a2c',
  padding: '1px 7px',
  fontSize: 10,
};

const STALE_THRESHOLD_SEC = 180;

function ConfidenceChart({ data }: { data: { ts: number; confidence: number }[] }) {
  if (!data || data.length === 0) {
    return <div style={{ fontSize: 10, color: '#555' }}>confidence 履歴なし</div>;
  }
  const W = 200;
  const H = 40;
  const n = data.length;
  const points = data.map((d, i) => {
    const x = n === 1 ? W / 2 : (i / (n - 1)) * W;
    const y = H - d.confidence * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <svg width={W} height={H} style={{ display: 'block', background: '#0d1117', borderRadius: 4 }}>
      {/* grid lines at 0.5 and 1.0 */}
      <line x1={0} y1={H / 2} x2={W} y2={H / 2} stroke="#2a2f3a" strokeWidth={1} strokeDasharray="3,3" />
      <line x1={0} y1={0} x2={W} y2={0} stroke="#2a2f3a" strokeWidth={1} />
      <polyline points={points} fill="none" stroke="#7da6ff" strokeWidth={1.5} />
      {data.map((d, i) => {
        const x = n === 1 ? W / 2 : (i / (n - 1)) * W;
        const y = H - d.confidence * H;
        return <circle key={i} cx={x} cy={y} r={2} fill="#7da6ff" />;
      })}
    </svg>
  );
}

function ageInfo(updatedAt?: number): { text: string; isStale: boolean } {
  if (!updatedAt) return { text: '', isStale: false };
  const ageSec = Math.max(0, Math.floor(Date.now() / 1000 - updatedAt));
  const isStale = ageSec >= STALE_THRESHOLD_SEC;
  let text: string;
  if (ageSec < 60) text = `${ageSec}秒前更新`;
  else if (ageSec < 3600) text = `${Math.floor(ageSec / 60)}分前更新`;
  else text = `${Math.floor(ageSec / 3600)}時間前更新`;
  return { text, isStale };
}

export default function ContextSummaryPanel({ open, externalSummary, mediaCtx }: ContextSummaryPanelProps) {
  const [summary, setSummary] = useState<ContextSummary | null>(null);
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(COLLAPSED_KEY) === '1';
    } catch {
      return false;
    }
  });
  const [showCorrection, setShowCorrection] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showEnriched, setShowEnriched] = useState(false);
  const [feedbackStatus, setFeedbackStatus] = useState<{ text: string; error: boolean } | null>(null);
  const [, forceTick] = useState(0);
  const ageTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Form state (full correction form)
  const [fixActivity, setFixActivity] = useState('');
  const [fixTopic, setFixTopic] = useState('');
  const [fixMeeting, setFixMeeting] = useState('');
  const [fixKeywords, setFixKeywords] = useState('');
  const [fixEntities, setFixEntities] = useState('');
  const [fixMood, setFixMood] = useState('');
  const [fixLocation, setFixLocation] = useState('');
  const [fixTimeContext, setFixTimeContext] = useState('');
  const [fixNote, setFixNote] = useState('');

  // Inline field chip state
  const [activeChip, setActiveChip] = useState<FieldKey | null>(null);
  const [chipValue, setChipValue] = useState('');

  // History panel state
  const [historyData, setHistoryData] = useState<{
    confidence_history: { ts: number; confidence: number }[];
    feedback_count: { yes: number; no: number; total: number };
    last_feedback_ts: number | null;
  } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/context-summary`);
      const d = await r.json();
      if (d.ok) setSummary(d.summary);
    } catch {
      // ignore
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/context-summary/history`);
      const d = await r.json();
      if (d.ok) setHistoryData(d);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (showHistory) fetchHistory();
  }, [showHistory, fetchHistory]);

  useEffect(() => {
    if (!open) return;
    refresh();
  }, [open, refresh]);

  useEffect(() => {
    if (externalSummary) setSummary(externalSummary);
  }, [externalSummary]);

  useEffect(() => {
    if (!open) return;
    ageTimerRef.current = setInterval(() => forceTick((n) => n + 1), 10_000);
    return () => {
      if (ageTimerRef.current) clearInterval(ageTimerRef.current);
    };
  }, [open]);

  const flashStatus = useCallback((text: string, error = false) => {
    setFeedbackStatus({ text, error });
    setTimeout(() => setFeedbackStatus(null), 4000);
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(COLLAPSED_KEY, next ? '1' : '0');
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  const openChip = useCallback((field: FieldKey) => {
    if (activeChip === field) {
      setActiveChip(null);
      setChipValue('');
      return;
    }
    setActiveChip(field);
    if (!summary) { setChipValue(''); return; }
    if (field === 'activity') setChipValue(summary.activity ?? '');
    else if (field === 'topic') setChipValue(summary.topic ?? '');
    else if (field === 'is_meeting') setChipValue(summary.is_meeting === true ? 'true' : summary.is_meeting === false ? 'false' : '');
    else if (field === 'keywords') setChipValue((summary.keywords ?? []).join(', '));
    else if (field === 'named_entities') setChipValue((summary.named_entities ?? []).join(', '));
    else if (field === 'mood') setChipValue(summary.mood ?? '');
    else if (field === 'location') setChipValue(summary.location ?? '');
    else if (field === 'time_context') setChipValue(summary.time_context ?? '');
  }, [activeChip, summary]);

  const closeChip = useCallback(() => {
    setActiveChip(null);
    setChipValue('');
  }, []);

  const submitChipCorrection = useCallback(async (field: FieldKey) => {
    if (!summary?.updated_at) {
      flashStatus('まだコンテキストが取得されてないよ', true);
      return;
    }
    const correction: Record<string, unknown> = {};
    const v = chipValue.trim();
    if (field === 'is_meeting') {
      if (v === 'true') correction.is_meeting = true;
      else if (v === 'false') correction.is_meeting = false;
    } else if (field === 'keywords' || field === 'named_entities') {
      correction[field] = v.split(',').map((s) => s.trim()).filter(Boolean);
    } else {
      if (!v) { flashStatus('値を入力してね', true); return; }
      correction[field] = v;
    }
    if (Object.keys(correction).length === 0) {
      flashStatus('値を入力してね', true);
      return;
    }
    try {
      const r = await fetch(`${API_BASE}/context-summary/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: 'no', correction, summary }),
      });
      const d = await r.json();
      if (d.ok) {
        flashStatus('修正を保存したよ ✓');
        closeChip();
      } else {
        flashStatus(`失敗: ${d.error}`, true);
      }
    } catch (err) {
      flashStatus(`失敗: ${(err as Error).message}`, true);
    }
  }, [summary, chipValue, flashStatus, closeChip]);

  const openCorrectionForm = useCallback(() => {
    setShowCorrection(true);
    if (summary) {
      setFixActivity(summary.activity ?? '');
      setFixTopic(summary.topic ?? '');
      setFixMeeting(summary.is_meeting === true ? 'true' : summary.is_meeting === false ? 'false' : '');
      setFixKeywords((summary.keywords ?? []).join(', '));
      setFixEntities((summary.named_entities ?? []).join(', '));
      setFixMood(summary.mood ?? '');
      setFixLocation(summary.location ?? '');
      setFixTimeContext(summary.time_context ?? '');
      setFixNote('');
    }
  }, [summary]);

  const handleYes = useCallback(async () => {
    if (!summary?.updated_at) {
      flashStatus('まだコンテキストが取得されてないよ', true);
      return;
    }
    try {
      const r = await fetch(`${API_BASE}/context-summary/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: 'yes', summary }),
      });
      const d = await r.json();
      if (d.ok) flashStatus('保存したよ ✓');
      else flashStatus(`失敗: ${d.error}`, true);
    } catch (err) {
      flashStatus(`失敗: ${(err as Error).message}`, true);
    }
  }, [summary, flashStatus]);

  const handleNo = useCallback(() => {
    if (showCorrection) setShowCorrection(false);
    else openCorrectionForm();
  }, [showCorrection, openCorrectionForm]);

  const submitCorrection = useCallback(async () => {
    if (!summary?.updated_at) {
      flashStatus('まだコンテキストが取得されてないよ', true);
      return;
    }
    const correction: Record<string, unknown> = {};
    if (fixActivity.trim()) correction.activity = fixActivity.trim();
    if (fixTopic.trim()) correction.topic = fixTopic.trim();
    if (fixMeeting === 'true') correction.is_meeting = true;
    else if (fixMeeting === 'false') correction.is_meeting = false;
    if (fixKeywords.trim()) correction.keywords = fixKeywords.split(',').map((s) => s.trim()).filter(Boolean);
    if (fixEntities.trim()) correction.named_entities = fixEntities.split(',').map((s) => s.trim()).filter(Boolean);
    if (fixMood.trim()) correction.mood = fixMood.trim();
    if (fixLocation.trim()) correction.location = fixLocation.trim();
    if (fixTimeContext.trim()) correction.time_context = fixTimeContext.trim();
    if (fixNote.trim()) correction.note = fixNote.trim();
    if (Object.keys(correction).length === 0) {
      flashStatus('正しい答えを1つ以上入力してね', true);
      return;
    }
    try {
      const r = await fetch(`${API_BASE}/context-summary/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: 'no', correction, summary }),
      });
      const d = await r.json();
      if (d.ok) {
        flashStatus('修正を保存したよ ✓');
        setShowCorrection(false);
      } else {
        flashStatus(`失敗: ${d.error}`, true);
      }
    } catch (err) {
      flashStatus(`失敗: ${(err as Error).message}`, true);
    }
  }, [summary, fixActivity, fixTopic, fixMeeting, fixKeywords, fixEntities, fixMood, fixLocation, fixTimeContext, fixNote, flashStatus]);

  if (!open) return null;

  const conf = summary?.confidence ?? 0;
  const confColor = conf >= 0.7 ? '#7dffaa' : conf >= 0.4 ? '#ffd17d' : '#888';
  const { text: ageLabel, isStale } = ageInfo(summary?.updated_at);

  if (collapsed) {
    return (
      <div style={containerStyle} id="ember-context-summary">
        <div
          role="button"
          tabIndex={0}
          onClick={toggleCollapsed}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              toggleCollapsed();
            }
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
            cursor: 'pointer',
            userSelect: 'none',
          }}
          aria-expanded={false}
          aria-controls="ember-context-summary"
          title="推測コンテキストを開く"
        >
          <span style={{ color: '#7da6ff', fontWeight: 600 }}>推測コンテキスト</span>
          <span style={{ color: '#666', fontSize: 12, lineHeight: 1 }}>▾</span>
        </div>
      </div>
    );
  }

  return (
    <div style={containerStyle} id="ember-context-summary">
      <button
        type="button"
        onClick={toggleCollapsed}
        style={{
          position: 'absolute',
          top: 4,
          right: 4,
          background: '#2a2f3a',
          color: '#888',
          border: '1px solid #3a4050',
          borderRadius: 4,
          padding: '2px 5px',
          cursor: 'pointer',
          fontSize: 9,
          lineHeight: 1.1,
          zIndex: 1,
        }}
        aria-expanded={true}
        aria-controls="ember-context-summary"
        title="推測コンテキストを閉じる"
      >
        ▴
      </button>
      <div style={headerRowStyle}>
        <span style={{ color: '#7da6ff', fontWeight: 600 }}>推測コンテキスト</span>
        <span style={{ color: confColor }}>
          {summary?.updated_at ? `信頼度 ${conf.toFixed(2)}` : '未取得'}
        </span>
        {isStale && (
          <span
            style={{
              background: '#7a1a1a',
              color: '#ff8080',
              border: '1px solid #c0392b',
              borderRadius: 3,
              padding: '1px 6px',
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: '0.05em',
            }}
          >
            STALE
          </span>
        )}
        <span style={{ color: '#666', marginLeft: 'auto' }}>{ageLabel}</span>
        <button
          type="button"
          onClick={refresh}
          style={{
            background: '#1e3050',
            color: '#7da6ff',
            border: '1px solid #2a4a8a',
            borderRadius: 4,
            padding: '2px 8px',
            cursor: 'pointer',
            fontSize: 10,
          }}
        >
          更新
        </button>
      </div>
      <div style={{ lineHeight: 1.5 }}>
        {/* 活動 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={labelStyle}>活動:</span>
          <span style={{ color: '#fff' }}>{summary?.activity || '—'}</span>
          {summary?.is_meeting && <span style={{ color: '#ffb347' }}>【会議】</span>}
          <button
            type="button"
            onClick={() => openChip('activity')}
            style={activeChip === 'activity' ? chipActiveStyle : chipStyle}
          >
            違う
          </button>
        </div>
        {activeChip === 'activity' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 4, marginBottom: 2 }}>
            <select
              value={chipValue}
              onChange={(e) => setChipValue(e.target.value)}
              style={inputStyle}
              onKeyDown={(e) => e.key === 'Escape' && closeChip()}
              autoFocus
            >
              <option value="">(未指定)</option>
              <option value="working">working</option>
              <option value="video_watching">video_watching</option>
              <option value="reading">reading</option>
              <option value="meeting">meeting</option>
              <option value="chatting">chatting</option>
              <option value="idle">idle</option>
            </select>
            <button type="button" onClick={() => submitChipCorrection('activity')} style={{ ...buttonStyle, background: '#2a4a8a', color: '#dde6ff', borderColor: '#3d6dc7' }}>保存</button>
            <button type="button" onClick={closeChip} style={{ ...buttonStyle, background: '#333', color: '#ccc', borderColor: '#555' }}>×</button>
          </div>
        )}
        {/* トピック */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={labelStyle}>トピック:</span>
          <span style={{ color: '#fff' }}>{summary?.topic || '—'}</span>
          <button
            type="button"
            onClick={() => openChip('topic')}
            style={activeChip === 'topic' ? chipActiveStyle : chipStyle}
          >
            違う
          </button>
        </div>
        {activeChip === 'topic' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 4, marginBottom: 2 }}>
            <input
              type="text"
              value={chipValue}
              onChange={(e) => setChipValue(e.target.value)}
              placeholder="例: ピアノ練習動画"
              style={{ ...inputStyle, width: 200 }}
              onKeyDown={(e) => { if (e.key === 'Enter') submitChipCorrection('topic'); else if (e.key === 'Escape') closeChip(); }}
              autoFocus
            />
            <button type="button" onClick={() => submitChipCorrection('topic')} style={{ ...buttonStyle, background: '#2a4a8a', color: '#dde6ff', borderColor: '#3d6dc7' }}>保存</button>
            <button type="button" onClick={closeChip} style={{ ...buttonStyle, background: '#333', color: '#ccc', borderColor: '#555' }}>×</button>
          </div>
        )}
        {/* 会議 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={labelStyle}>会議:</span>
          <span style={{ color: '#fff' }}>{summary?.is_meeting === true ? 'はい' : summary?.is_meeting === false ? 'いいえ' : '—'}</span>
          <button
            type="button"
            onClick={() => openChip('is_meeting')}
            style={activeChip === 'is_meeting' ? chipActiveStyle : chipStyle}
          >
            違う
          </button>
        </div>
        {activeChip === 'is_meeting' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 4, marginBottom: 2 }}>
            <select
              value={chipValue}
              onChange={(e) => setChipValue(e.target.value)}
              style={inputStyle}
              onKeyDown={(e) => e.key === 'Escape' && closeChip()}
              autoFocus
            >
              <option value="">(未指定)</option>
              <option value="true">はい</option>
              <option value="false">いいえ</option>
            </select>
            <button type="button" onClick={() => submitChipCorrection('is_meeting')} style={{ ...buttonStyle, background: '#2a4a8a', color: '#dde6ff', borderColor: '#3d6dc7' }}>保存</button>
            <button type="button" onClick={closeChip} style={{ ...buttonStyle, background: '#333', color: '#ccc', borderColor: '#555' }}>×</button>
          </div>
        )}
        {/* キーワード */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={labelStyle}>キーワード:</span>
          <span style={{ color: '#9fd8ff' }}>{(summary?.keywords ?? []).join(', ') || '—'}</span>
          <button
            type="button"
            onClick={() => openChip('keywords')}
            style={activeChip === 'keywords' ? chipActiveStyle : chipStyle}
          >
            違う
          </button>
        </div>
        {activeChip === 'keywords' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 4, marginBottom: 2 }}>
            <input
              type="text"
              value={chipValue}
              onChange={(e) => setChipValue(e.target.value)}
              placeholder="カンマ区切り: PPO, Atari"
              style={{ ...inputStyle, width: 200 }}
              onKeyDown={(e) => { if (e.key === 'Enter') submitChipCorrection('keywords'); else if (e.key === 'Escape') closeChip(); }}
              autoFocus
            />
            <button type="button" onClick={() => submitChipCorrection('keywords')} style={{ ...buttonStyle, background: '#2a4a8a', color: '#dde6ff', borderColor: '#3d6dc7' }}>保存</button>
            <button type="button" onClick={closeChip} style={{ ...buttonStyle, background: '#333', color: '#ccc', borderColor: '#555' }}>×</button>
          </div>
        )}
        {/* 固有名詞 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={labelStyle}>固有名詞:</span>
          <span style={{ color: '#9fd8ff' }}>{(summary?.named_entities ?? []).join(', ') || '—'}</span>
          <button
            type="button"
            onClick={() => openChip('named_entities')}
            style={activeChip === 'named_entities' ? chipActiveStyle : chipStyle}
          >
            違う
          </button>
        </div>
        {activeChip === 'named_entities' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 4, marginBottom: 2 }}>
            <input
              type="text"
              value={chipValue}
              onChange={(e) => setChipValue(e.target.value)}
              placeholder="カンマ区切り: DeepMind"
              style={{ ...inputStyle, width: 200 }}
              onKeyDown={(e) => { if (e.key === 'Enter') submitChipCorrection('named_entities'); else if (e.key === 'Escape') closeChip(); }}
              autoFocus
            />
            <button type="button" onClick={() => submitChipCorrection('named_entities')} style={{ ...buttonStyle, background: '#2a4a8a', color: '#dde6ff', borderColor: '#3d6dc7' }}>保存</button>
            <button type="button" onClick={closeChip} style={{ ...buttonStyle, background: '#333', color: '#ccc', borderColor: '#555' }}>×</button>
          </div>
        )}
        {/* 気分 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={labelStyle}>気分:</span>
          <span style={{ color: '#fff' }}>{summary?.mood || '—'}</span>
          <button
            type="button"
            onClick={() => openChip('mood')}
            style={activeChip === 'mood' ? chipActiveStyle : chipStyle}
          >
            違う
          </button>
        </div>
        {activeChip === 'mood' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 4, marginBottom: 2 }}>
            <select
              value={chipValue}
              onChange={(e) => setChipValue(e.target.value)}
              style={inputStyle}
              onKeyDown={(e) => e.key === 'Escape' && closeChip()}
              autoFocus
            >
              <option value="">(未指定)</option>
              <option value="calm">calm</option>
              <option value="focused">focused</option>
              <option value="excited">excited</option>
              <option value="stressed">stressed</option>
              <option value="neutral">neutral</option>
            </select>
            <button type="button" onClick={() => submitChipCorrection('mood')} style={{ ...buttonStyle, background: '#2a4a8a', color: '#dde6ff', borderColor: '#3d6dc7' }}>保存</button>
            <button type="button" onClick={closeChip} style={{ ...buttonStyle, background: '#333', color: '#ccc', borderColor: '#555' }}>×</button>
          </div>
        )}
        {/* 場所 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={labelStyle}>場所:</span>
          <span style={{ color: '#fff' }}>{summary?.location || '—'}</span>
          <button
            type="button"
            onClick={() => openChip('location')}
            style={activeChip === 'location' ? chipActiveStyle : chipStyle}
          >
            違う
          </button>
        </div>
        {activeChip === 'location' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 4, marginBottom: 2 }}>
            <select
              value={chipValue}
              onChange={(e) => setChipValue(e.target.value)}
              style={inputStyle}
              onKeyDown={(e) => e.key === 'Escape' && closeChip()}
              autoFocus
            >
              <option value="">(未指定)</option>
              <option value="home">home</option>
              <option value="office">office</option>
              <option value="cafe">cafe</option>
              <option value="commute">commute</option>
              <option value="unknown">unknown</option>
            </select>
            <button type="button" onClick={() => submitChipCorrection('location')} style={{ ...buttonStyle, background: '#2a4a8a', color: '#dde6ff', borderColor: '#3d6dc7' }}>保存</button>
            <button type="button" onClick={closeChip} style={{ ...buttonStyle, background: '#333', color: '#ccc', borderColor: '#555' }}>×</button>
          </div>
        )}
        {/* 時間帯 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={labelStyle}>時間帯:</span>
          <span style={{ color: '#fff' }}>{summary?.time_context || '—'}</span>
          <button
            type="button"
            onClick={() => openChip('time_context')}
            style={activeChip === 'time_context' ? chipActiveStyle : chipStyle}
          >
            違う
          </button>
        </div>
        {activeChip === 'time_context' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 4, marginBottom: 2 }}>
            <select
              value={chipValue}
              onChange={(e) => setChipValue(e.target.value)}
              style={inputStyle}
              onKeyDown={(e) => e.key === 'Escape' && closeChip()}
              autoFocus
            >
              <option value="">(未指定)</option>
              <option value="morning">morning</option>
              <option value="afternoon">afternoon</option>
              <option value="evening">evening</option>
              <option value="night">night</option>
              <option value="unknown">unknown</option>
            </select>
            <button type="button" onClick={() => submitChipCorrection('time_context')} style={{ ...buttonStyle, background: '#2a4a8a', color: '#dde6ff', borderColor: '#3d6dc7' }}>保存</button>
            <button type="button" onClick={closeChip} style={{ ...buttonStyle, background: '#333', color: '#ccc', borderColor: '#555' }}>×</button>
          </div>
        )}
        {/* 特定コンテンツ */}
        <div style={{ marginTop: 6 }}>
          <span style={{ color: '#7da6ff', fontWeight: 600 }}>特定コンテンツ</span>
          {mediaCtx && mediaCtx.inferred_type && mediaCtx.inferred_type !== 'unknown' ? (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                <span style={chipActiveStyle}>{mediaCtx.inferred_type}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
                <span style={labelStyle}>タイトル:</span>
                <span style={{ color: '#fff' }}>{mediaCtx.matched_title || '—'}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
                <span style={labelStyle}>トピック:</span>
                <span style={{ color: '#fff' }}>{mediaCtx.inferred_topic || '—'}</span>
              </div>
              <div style={{ marginTop: 2 }}>
                <span style={labelStyle}>信頼度:</span>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    marginTop: 2,
                  }}
                >
                  <div
                    style={{
                      width: 100,
                      height: 6,
                      background: '#2a2f3a',
                      borderRadius: 3,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        width: `${(mediaCtx.confidence * 100).toFixed(0)}%`,
                        height: '100%',
                        background:
                          mediaCtx.confidence >= 0.7
                            ? '#7dffaa'
                            : mediaCtx.confidence >= 0.4
                              ? '#ffd17d'
                              : '#888',
                      }}
                    />
                  </div>
                  <span style={{ color: '#cfd6e4', fontSize: 10 }}>{(mediaCtx.confidence * 100).toFixed(0)}%</span>
                </div>
              </div>
              {mediaCtx.keywords && mediaCtx.keywords.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
                  <span style={labelStyle}>キーワード:</span>
                  <span style={{ color: '#9fd8ff' }}>{mediaCtx.keywords.join(', ')}</span>
                </div>
              )}
              {mediaCtx.enriched_info && (
                <div style={{ marginTop: 2 }}>
                  <button
                    type="button"
                    onClick={() => setShowEnriched(!showEnriched)}
                    style={{
                      ...buttonStyle,
                      background: '#2a2f3a',
                      color: '#888',
                      borderColor: '#3a4050',
                      padding: '3px 10px',
                      cursor: 'pointer',
                    }}
                  >
                    詳細を見る {showEnriched ? '▲' : '▼'}
                  </button>
                  {showEnriched && (
                    <div
                      style={{
                        marginTop: 4,
                        whiteSpace: 'pre-wrap',
                        color: '#cfd6e4',
                        fontSize: 11,
                        lineHeight: 1.5,
                      }}
                    >
                      {mediaCtx.enriched_info}
                    </div>
                  )}
                </div>
              )}
              {mediaCtx.last_inferred_at && (
                <div style={{ marginTop: 4, textAlign: 'right', color: '#666', fontSize: 10 }}>
                  {ageInfo(mediaCtx.last_inferred_at).text}
                </div>
              )}
            </>
          ) : (
            <span style={{ color: '#666', fontSize: 10 }}>未特定</span>
          )}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6 }}>
        <button type="button" onClick={handleYes} style={yesStyle}>
          Yes ✓ 正しい
        </button>
        <button type="button" onClick={handleNo} style={noStyle}>
          No ✗ 違う
        </button>
        {feedbackStatus && (
          <span style={{ color: feedbackStatus.error ? '#ff6e6e' : '#7dffaa', fontSize: 10 }}>
            {feedbackStatus.text}
          </span>
        )}
      </div>
      {summary && (summary.evidence_snippets ?? []).length > 0 && (
        <div style={{ marginTop: 6 }}>
          <button
            type="button"
            onClick={() => setShowEvidence(!showEvidence)}
            style={{
              ...buttonStyle,
              background: '#2a2f3a',
              color: '#888',
              borderColor: '#3a4050',
              padding: '3px 10px',
              cursor: 'pointer',
            }}
          >
            根拠を見る {showEvidence ? '▲' : '▼'}
          </button>
          {showEvidence && summary.evidence_snippets && (
            <div style={{ marginTop: 4, marginLeft: 6 }}>
              {summary.evidence_snippets.map((snippet, idx) => (
                <div key={idx} style={{ color: '#888', fontSize: 10, lineHeight: 1.4, marginBottom: 2 }}>
                  {snippet}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      <div style={{ marginTop: 6 }}>
        <button
          type="button"
          onClick={() => setShowHistory((v) => !v)}
          style={{
            ...buttonStyle,
            background: '#1a2a3a',
            color: '#7da6ff',
            borderColor: '#2a4a8a',
            padding: '3px 10px',
            cursor: 'pointer',
          }}
        >
          学習状況 {showHistory ? '▲' : '▼'}
        </button>
        {showHistory && (
          <div style={{ marginTop: 6, marginLeft: 2 }}>
            {historyData ? (
              <>
                <ConfidenceChart data={historyData.confidence_history} />
                <div style={{ marginTop: 4, fontSize: 10, color: '#aaa' }}>
                  Yes: {historyData.feedback_count.yes} / No: {historyData.feedback_count.no} / 合計: {historyData.feedback_count.total}
                </div>
                {historyData.last_feedback_ts && (
                  <div style={{ fontSize: 10, color: '#888', marginTop: 2 }}>
                    最終フィードバック: {Math.floor((Date.now() / 1000 - historyData.last_feedback_ts) / 60)}分前
                  </div>
                )}
              </>
            ) : (
              <div style={{ fontSize: 10, color: '#666' }}>読み込み中...</div>
            )}
          </div>
        )}
      </div>
      {showCorrection && (
        <div
          style={{
            marginTop: 8,
            padding: 6,
            background: '#0f1116',
            border: '1px solid #2a2f3a',
            borderRadius: 4,
          }}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '80px 1fr',
              gap: '4px 6px',
              alignItems: 'center',
            }}
          >
            <label style={labelStyle}>活動</label>
            <select value={fixActivity} onChange={(e) => setFixActivity(e.target.value)} style={inputStyle}>
              <option value="">(未指定)</option>
              <option value="working">working</option>
              <option value="video_watching">video_watching</option>
              <option value="reading">reading</option>
              <option value="meeting">meeting</option>
              <option value="chatting">chatting</option>
              <option value="idle">idle</option>
            </select>
            <label style={labelStyle}>トピック</label>
            <input
              type="text"
              value={fixTopic}
              onChange={(e) => setFixTopic(e.target.value)}
              placeholder="例: ピアノ練習動画"
              style={inputStyle}
            />
            <label style={labelStyle}>会議?</label>
            <select value={fixMeeting} onChange={(e) => setFixMeeting(e.target.value)} style={inputStyle}>
              <option value="">(未指定)</option>
              <option value="true">はい</option>
              <option value="false">いいえ</option>
            </select>
            <label style={labelStyle}>キーワード</label>
            <input
              type="text"
              value={fixKeywords}
              onChange={(e) => setFixKeywords(e.target.value)}
              placeholder="カンマ区切り: PPO, Atari"
              style={inputStyle}
            />
            <label style={labelStyle}>固有名詞</label>
            <input
              type="text"
              value={fixEntities}
              onChange={(e) => setFixEntities(e.target.value)}
              placeholder="カンマ区切り: DeepMind"
              style={inputStyle}
            />
            <label style={labelStyle}>気分</label>
            <select value={fixMood} onChange={(e) => setFixMood(e.target.value)} style={inputStyle}>
              <option value="">(未指定)</option>
              <option value="calm">calm</option>
              <option value="focused">focused</option>
              <option value="excited">excited</option>
              <option value="stressed">stressed</option>
              <option value="neutral">neutral</option>
            </select>
            <label style={labelStyle}>場所</label>
            <select value={fixLocation} onChange={(e) => setFixLocation(e.target.value)} style={inputStyle}>
              <option value="">(未指定)</option>
              <option value="home">home</option>
              <option value="office">office</option>
              <option value="cafe">cafe</option>
              <option value="commute">commute</option>
              <option value="unknown">unknown</option>
            </select>
            <label style={labelStyle}>時間帯</label>
            <select value={fixTimeContext} onChange={(e) => setFixTimeContext(e.target.value)} style={inputStyle}>
              <option value="">(未指定)</option>
              <option value="morning">morning</option>
              <option value="afternoon">afternoon</option>
              <option value="evening">evening</option>
              <option value="night">night</option>
              <option value="unknown">unknown</option>
            </select>
            <label style={labelStyle}>メモ</label>
            <input
              type="text"
              value={fixNote}
              onChange={(e) => setFixNote(e.target.value)}
              placeholder="補足（任意）"
              style={inputStyle}
            />
          </div>
          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            <button
              type="button"
              onClick={submitCorrection}
              style={{
                background: '#2a4a8a',
                color: '#dde6ff',
                border: '1px solid #3d6dc7',
                borderRadius: 4,
                padding: '3px 10px',
                cursor: 'pointer',
                fontSize: 11,
              }}
            >
              保存
            </button>
            <button
              type="button"
              onClick={() => setShowCorrection(false)}
              style={{
                background: '#333',
                color: '#ccc',
                border: '1px solid #555',
                borderRadius: 4,
                padding: '3px 10px',
                cursor: 'pointer',
                fontSize: 11,
              }}
            >
              キャンセル
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
