import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { saveAudioFixtureIncoming } from '../api';

// Direct connection to voice_chat server (proxy has issues with POST)
const API = 'http://localhost:8767/api/speaker-id';

const PHRASES = [
  'メイ、今日の天気はどう？',
  'メイ、おはよう',
  'メイ、今何時？',
  'メイ、音楽をかけて',
  'メイ、おやすみ',
];

interface SpeakerProfile {
  name: string;
  display_name: string;
  samples: number;
}

type Step = 'form' | 'recording' | 'done';

const TEST_AUDIO_PRESETS = {
  keyboard: {
    label: 'キーボード / 生活音',
    guidance: '考えなくて大丈夫。この手順どおりに実行して録るだけでいいよ。',
    scriptTitle: 'この手順どおりに録音',
    script: '無言のまま、キーボードを3回打って、1秒置いて、マウスを1回クリックしてください。',
    scenePlaceholder: 'mechanical_short',
    transcriptHint: '例: カタ / コト / なし',
    notesHint: 'キーボードや机の打鍵音っぽい短い断片',
    expectedSource: 'fragmentary',
    expectedIntervention: 'skip',
  },
  monologue: {
    label: '独り言',
    guidance: 'この文をそのまま読めば大丈夫よ。',
    scriptTitle: 'この文をそのまま読む',
    script: '疲れたなあ、ちょっと休もうかな。',
    scenePlaceholder: 'tired_after_work',
    transcriptHint: '例: 疲れたなあ、ちょっと休もうかな。',
    notesHint: 'PC作業中の独り言。短い相槌が自然',
    expectedSource: 'user_likely',
    expectedIntervention: 'backchannel',
  },
  question: {
    label: '名前なし相談',
    guidance: 'この文をそのまま読めば、名前なし相談のサンプルになるわ。',
    scriptTitle: 'この文をそのまま読む',
    script: '今日の予定どうしようかな？',
    scenePlaceholder: 'schedule_planning',
    transcriptHint: '例: 今日の予定どうしようかな？',
    notesHint: '名前なしの相談。人間なら返して自然',
    expectedSource: 'user_likely',
    expectedIntervention: 'reply',
  },
  media: {
    label: 'TV / 動画音声',
    guidance: 'メディア音声の代わりに、このナレーション調の文をそのまま読んでね。',
    scriptTitle: 'この文をナレーションっぽく読む',
    script: 'この動画をご視聴いただきありがとうございました。また次回の動画でお会いしましょう。',
    scenePlaceholder: 'youtube_outro',
    transcriptHint: '例: この動画をご視聴いただきありがとうございました',
    notesHint: '動画や配信の締めっぽい音声',
    expectedSource: 'media_likely',
    expectedIntervention: 'skip',
  },
  multi_party: {
    label: '他人との会話',
    guidance: '一人で悩まなくて大丈夫。この文を会話の一言っぽく読んでね。',
    scriptTitle: 'この文を会話の一言として読む',
    script: 'それ先にお願いしていい？',
    scenePlaceholder: 'room_conversation',
    transcriptHint: '例: それ先にお願いしていい？',
    notesHint: '複数人会話。MEI は見守り寄りが自然',
    expectedSource: 'user_in_conversation',
    expectedIntervention: 'skip',
  },
  wake: {
    label: '明示呼びかけ',
    guidance: 'この文をそのまま読めば、呼びかけサンプルになるわ。',
    scriptTitle: 'この文をそのまま読む',
    script: 'メイ、おはよう。',
    scenePlaceholder: 'good_morning',
    transcriptHint: '例: メイ、おはよう',
    notesHint: '明示呼びかけ。会話開始として拾いたい',
    expectedSource: 'user_initiative',
    expectedIntervention: 'reply',
  },
} as const;

type FixtureCategory = keyof typeof TEST_AUDIO_PRESETS;
type FixtureIntervention = 'skip' | 'backchannel' | 'reply';

function slugify(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '') || 'sample';
}

function encodeWav(audioBuffer: AudioBuffer): Blob {
  const channels = 1;
  const sampleRate = audioBuffer.sampleRate;
  const source = audioBuffer.getChannelData(0);
  const bytesPerSample = 2;
  const blockAlign = channels * bytesPerSample;
  const buffer = new ArrayBuffer(44 + source.length * bytesPerSample);
  const view = new DataView(buffer);

  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  };

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + source.length * bytesPerSample, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bytesPerSample * 8, true);
  writeString(36, 'data');
  view.setUint32(40, source.length * bytesPerSample, true);

  let offset = 44;
  for (let i = 0; i < source.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, source[i]));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    offset += bytesPerSample;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

async function convertRecordedBlobToWav(blob: Blob): Promise<Blob> {
  const arrayBuffer = await blob.arrayBuffer();
  const audioContext = new AudioContext();
  try {
    const decoded = await audioContext.decodeAudioData(arrayBuffer.slice(0));
    return encodeWav(decoded);
  } finally {
    await audioContext.close();
  }
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export default function VoiceEnrollPage() {
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState<SpeakerProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  // Enrollment state
  const [step, setStep] = useState<Step>('form');
  const [newName, setNewName] = useState('');
  const [newDisplayName, setNewDisplayName] = useState('');
  const [newYomigana, setNewYomigana] = useState('');
  const [phraseIndex, setPhraseIndex] = useState(0);
  const [samplesOk, setSamplesOk] = useState(0);
  const [isRecording, setIsRecording] = useState(false);
  const [sampleMsg, setSampleMsg] = useState('');
  const [doneMsg, setDoneMsg] = useState('');

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const fixtureRecorderRef = useRef<MediaRecorder | null>(null);
  const fixtureChunksRef = useRef<Blob[]>([]);
  const fixtureStreamRef = useRef<MediaStream | null>(null);

  const [fixtureCategory, setFixtureCategory] = useState<FixtureCategory>('question');
  const [fixtureScene, setFixtureScene] = useState<string>(TEST_AUDIO_PRESETS.question.scenePlaceholder);
  const [fixtureVariant, setFixtureVariant] = useState('01');
  const [fixtureId, setFixtureId] = useState('question_schedule_planning_01');
  const [fixtureTranscript, setFixtureTranscript] = useState<string>(TEST_AUDIO_PRESETS.question.script);
  const [fixtureExpectedSource, setFixtureExpectedSource] = useState<string>(TEST_AUDIO_PRESETS.question.expectedSource);
  const [fixtureExpectedIntervention, setFixtureExpectedIntervention] = useState<FixtureIntervention>(TEST_AUDIO_PRESETS.question.expectedIntervention);
  const [fixtureNotes, setFixtureNotes] = useState<string>(TEST_AUDIO_PRESETS.question.notesHint);
  const [fixtureRecording, setFixtureRecording] = useState(false);
  const [fixtureStatus, setFixtureStatus] = useState('');
  const [fixtureBlob, setFixtureBlob] = useState<Blob | null>(null);
  const [fixtureWavBlob, setFixtureWavBlob] = useState<Blob | null>(null);
  const [fixtureDurationMs, setFixtureDurationMs] = useState<number | null>(null);
  const [fixtureStartedAt, setFixtureStartedAt] = useState<number | null>(null);
  const [fixtureSavedBaseName, setFixtureSavedBaseName] = useState<string | null>(null);
  const [fixtureSavedPaths, setFixtureSavedPaths] = useState<{ wav: string; json: string } | null>(null);
  const fixtureSaveTimerRef = useRef<number | null>(null);
  const fixtureLastAutosaveKeyRef = useRef<string | null>(null);

  const fetchProfiles = useCallback(async () => {
    try {
      const res = await fetch(`${API}/profiles`);
      const data = await res.json();
      setProfiles(data.profiles || []);
      setError('');
    } catch {
      setError('voice_chat サーバーに接続できません');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchProfiles(); }, [fetchProfiles]);

  // Cleanup mic on unmount
  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop());
      }
      if (fixtureStreamRef.current) {
        fixtureStreamRef.current.getTracks().forEach(t => t.stop());
      }
      if (fixtureSaveTimerRef.current) {
        window.clearTimeout(fixtureSaveTimerRef.current);
      }
    };
  }, []);

  const fixturePreset = TEST_AUDIO_PRESETS[fixtureCategory];
  const fixtureBaseName = `${slugify(fixtureCategory)}__${slugify(fixtureScene)}__${slugify(fixtureVariant)}`;
  const fixtureWavName = `${fixtureBaseName}.wav`;
  const fixtureJsonName = `${fixtureBaseName}.json`;
  const resolvedFixtureId = fixtureId.trim() || `${slugify(fixtureCategory)}_${slugify(fixtureScene)}_${slugify(fixtureVariant)}`;
  const currentFixtureSidecar = useMemo(() => ({
    category: slugify(fixtureCategory),
    scene: slugify(fixtureScene),
    variant: slugify(fixtureVariant),
    id: resolvedFixtureId,
    transcript: fixtureTranscript.trim(),
    expected_source: fixtureExpectedSource,
    expected_intervention: fixtureExpectedIntervention,
    notes: fixtureNotes.trim(),
  }), [
    fixtureCategory,
    fixtureExpectedIntervention,
    fixtureExpectedSource,
    fixtureNotes,
    fixtureScene,
    fixtureTranscript,
    fixtureVariant,
    resolvedFixtureId,
  ]);

  const startEnrollment = async () => {
    const name = newName.trim();
    const displayName = newDisplayName.trim() || name;
    if (!name) { setError('ID を入力してください'); return; }
    setError('');
    try {
      const res = await fetch(`${API}/enroll/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, display_name: displayName }),
      });
      const data = await res.json();
      if (!data.ok) { setError(data.message); return; }
    } catch { setError('サーバーエラー'); return; }

    // Request mic permission
    try {
      streamRef.current = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    } catch (err) {
      console.error('[VoiceEnroll] mic error:', err);
      setError(`マイクへのアクセスが拒否されました: ${err instanceof Error ? err.message : String(err)}`);
      await fetch(`${API}/enroll/cancel`, { method: 'POST' });
      return;
    }

    setPhraseIndex(0);
    setSamplesOk(0);
    setSampleMsg('');
    setStep('recording');
  };

  const startRecording = () => {
    if (!streamRef.current) return;
    chunksRef.current = [];
    try {
      const mr = new MediaRecorder(streamRef.current, { mimeType: 'audio/webm;codecs=opus' });
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mediaRecorderRef.current = mr;
      mr.start(100); // collect chunks every 100ms
      setIsRecording(true);
      setSampleMsg('話してください...');
    } catch (err) {
      console.error('[VoiceEnroll] recorder start error:', err);
      setSampleMsg('録音開始に失敗しました');
    }
  };

  const stopRecording = async () => {
    const mr = mediaRecorderRef.current;
    if (!mr || mr.state !== 'recording') {
      setIsRecording(false);
      return;
    }
    // Stop and wait for final data
    await new Promise<void>((resolve) => {
      mr.onstop = () => resolve();
      mr.stop();
    });
    setIsRecording(false);
    // Send collected audio
    await sendSample();
  };

  const sendSample = async () => {
    const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
    setSampleMsg(`送信中... (${Math.round(blob.size / 1024)}KB)`);
    if (blob.size < 500) { setSampleMsg('音声が短すぎます。もう一度録音してください'); return; }

    const form = new FormData();
    form.append('audio', blob, 'sample.webm');

    try {
      const res = await fetch(`${API}/enroll/sample`, { method: 'POST', body: form });
      const data = await res.json();
      if (data.ok) {
        const n = data.samples || (samplesOk + 1);
        setSamplesOk(n);
        setSampleMsg(`サンプル ${n} / 5 OK`);
        const next = phraseIndex + 1;
        if (next >= PHRASES.length || n >= 5) {
          await finishEnrollment(n);
        } else {
          setPhraseIndex(next);
        }
      } else {
        setSampleMsg(data.message || '失敗 — もう一度録音してください');
      }
    } catch (err) {
      console.error('[VoiceEnroll] send error:', err);
      setSampleMsg('送信エラー — サーバー接続を確認してください');
    }
  };

  const finishEnrollment = async (n: number) => {
    if (n < 3) {
      setSampleMsg(`サンプルが ${n} 個しかありません（最低3個必要）。続けてください。`);
      return;
    }
    try {
      const res = await fetch(`${API}/enroll/finish`, { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        setDoneMsg(data.message || '登録完了');
        setStep('done');
        fetchProfiles();
        // Release mic
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(t => t.stop());
          streamRef.current = null;
        }
      } else {
        setSampleMsg(data.message || '登録失敗');
      }
    } catch {
      setSampleMsg('サーバーエラー');
    }
  };

  const cancelEnrollment = async () => {
    try { await fetch(`${API}/enroll/cancel`, { method: 'POST' }); } catch {}
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    setStep('form');
    setSampleMsg('');
  };

  const resetForm = () => {
    setStep('form');
    setNewName('');
    setNewDisplayName('');
    setNewYomigana('');
    setDoneMsg('');
    setSampleMsg('');
  };

  const deleteProfile = async (name: string) => {
    try {
      await fetch(`${API}/profiles/${name}`, { method: 'DELETE' });
      setDeleteConfirm(null);
      fetchProfiles();
    } catch { setError('削除に失敗しました'); }
  };

  const applyFixturePreset = (category: FixtureCategory) => {
    const preset = TEST_AUDIO_PRESETS[category];
    setFixtureCategory(category);
    setFixtureScene(preset.scenePlaceholder);
    setFixtureVariant('01');
    setFixtureId(`${category}_${preset.scenePlaceholder}_01`);
    setFixtureTranscript(preset.script);
    setFixtureExpectedSource(preset.expectedSource);
    setFixtureExpectedIntervention(preset.expectedIntervention);
    setFixtureNotes(preset.notesHint);
    setFixtureBlob(null);
    setFixtureWavBlob(null);
    setFixtureDurationMs(null);
    setFixtureStatus('');
    setFixtureSavedBaseName(null);
    setFixtureSavedPaths(null);
    fixtureLastAutosaveKeyRef.current = null;
  };

  const ensureFixtureStream = async () => {
    if (fixtureStreamRef.current) return fixtureStreamRef.current;
    fixtureStreamRef.current = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    return fixtureStreamRef.current;
  };

  const startFixtureRecording = async () => {
    try {
      const stream = await ensureFixtureStream();
      fixtureChunksRef.current = [];
      const preferredMime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : undefined;
      const recorder = preferredMime ? new MediaRecorder(stream, { mimeType: preferredMime }) : new MediaRecorder(stream);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) fixtureChunksRef.current.push(event.data);
      };
      fixtureRecorderRef.current = recorder;
      recorder.start(100);
      setFixtureRecording(true);
      setFixtureBlob(null);
      setFixtureWavBlob(null);
      setFixtureStatus('録音中... 画面の台本どおりに読んで、終わったら停止してね。');
      setFixtureStartedAt(Date.now());
    } catch (err) {
      setFixtureStatus(`録音を開始できませんでした: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const stopFixtureRecording = async () => {
    const recorder = fixtureRecorderRef.current;
    if (!recorder || recorder.state !== 'recording') {
      setFixtureRecording(false);
      return;
    }

    await new Promise<void>((resolve) => {
      recorder.onstop = () => resolve();
      recorder.stop();
    });

    const recordedBlob = new Blob(fixtureChunksRef.current, { type: recorder.mimeType || 'audio/webm' });
    setFixtureRecording(false);
    setFixtureStartedAt(null);
    if (recordedBlob.size < 500) {
      setFixtureStatus('音が短すぎるみたい。もう少しだけ長めに録ってみてね。');
      return;
    }

    setFixtureBlob(recordedBlob);
    setFixtureStatus('WAV に変換して `incoming/` へ自動保存しているよ...');
    setFixtureDurationMs(recordedBlob.size);
    try {
      const wavBlob = await convertRecordedBlobToWav(recordedBlob);
      setFixtureWavBlob(wavBlob);
      const result = await saveAudioFixtureIncoming({
        baseName: fixtureBaseName,
        previousBaseName: fixtureSavedBaseName,
        wavBlob,
        sidecar: currentFixtureSidecar,
      });
      setFixtureSavedBaseName(fixtureBaseName);
      setFixtureSavedPaths(result.saved);
      fixtureLastAutosaveKeyRef.current = JSON.stringify({ baseName: fixtureBaseName, sidecar: currentFixtureSidecar });
      setFixtureStatus('録音できたよ。`incoming/` に WAV と JSON を自動保存したわ。必要なら transcript を直すと JSON も更新されるよ。');
    } catch (err) {
      setFixtureStatus(`自動保存に失敗したわ: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const downloadFixtureWav = async () => {
    if (!fixtureWavBlob && !fixtureBlob) {
      setFixtureStatus('先に録音を作成してね。');
      return;
    }
    try {
      setFixtureStatus('WAV を作成中...');
      const wavBlob = fixtureWavBlob ?? await convertRecordedBlobToWav(fixtureBlob as Blob);
      triggerDownload(wavBlob, fixtureWavName);
      setFixtureStatus(`WAV を保存したよ: ${fixtureWavName}`);
    } catch (err) {
      setFixtureStatus(`WAV 変換に失敗したわ: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const downloadFixtureJson = () => {
    triggerDownload(
      new Blob([JSON.stringify(currentFixtureSidecar, null, 2)], { type: 'application/json' }),
      fixtureJsonName,
    );
    setFixtureStatus(`sidecar JSON を保存したよ: ${fixtureJsonName}`);
  };

  useEffect(() => {
    if (!fixtureWavBlob || fixtureRecording) return;
    const autosaveKey = JSON.stringify({ baseName: fixtureBaseName, sidecar: currentFixtureSidecar });
    if (fixtureLastAutosaveKeyRef.current === autosaveKey) return;
    if (fixtureSaveTimerRef.current) {
      window.clearTimeout(fixtureSaveTimerRef.current);
    }
    fixtureSaveTimerRef.current = window.setTimeout(async () => {
      try {
        const result = await saveAudioFixtureIncoming({
          baseName: fixtureBaseName,
          previousBaseName: fixtureSavedBaseName !== fixtureBaseName ? fixtureSavedBaseName : null,
          wavBlob: fixtureWavBlob,
          sidecar: currentFixtureSidecar,
        });
        setFixtureSavedBaseName(fixtureBaseName);
        setFixtureSavedPaths(result.saved);
        fixtureLastAutosaveKeyRef.current = autosaveKey;
        setFixtureStatus('`incoming/` の sidecar を更新したよ。');
      } catch (err) {
        setFixtureStatus(`自動更新に失敗したわ: ${err instanceof Error ? err.message : String(err)}`);
      }
    }, 600);

    return () => {
      if (fixtureSaveTimerRef.current) {
        window.clearTimeout(fixtureSaveTimerRef.current);
      }
    };
  }, [
    currentFixtureSidecar,
    fixtureBaseName,
    fixtureRecording,
    fixtureSavedBaseName,
    fixtureWavBlob,
  ]);

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="inline-flex items-center gap-1.5 text-sm text-[var(--text-dim)] hover:text-[var(--accent)] transition-colors"
      >
        ← 戻る
      </button>
      <h1 className="text-xl font-semibold text-[var(--text)]">録音</h1>
      <p className="text-sm text-[var(--text-dim)]">
        ここでは、MEI 用の声紋登録と、ambient companion の評価に使うテスト音声作成をまとめて進められるよ。
        静かな環境で録音して、1ファイル 1シーンで揃えるのがおすすめ。
      </p>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] p-5">
          <div className="text-xs uppercase tracking-[0.16em] text-[var(--accent)] mb-2">Section 01</div>
          <h2 className="text-lg font-semibold text-[var(--text)]">声紋登録</h2>
          <p className="mt-2 text-sm text-[var(--text-dim)]">
            本人の声を 3〜5 サンプル登録して、MEI が誰の声か見分けられるようにするセクションよ。
          </p>
        </div>
        <div className="rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] p-5">
          <div className="text-xs uppercase tracking-[0.16em] text-[var(--accent)] mb-2">Section 02</div>
          <h2 className="text-lg font-semibold text-[var(--text)]">テスト音声作成</h2>
          <p className="mt-2 text-sm text-[var(--text-dim)]">
            `incoming/` に置く前提の `wav + json` を、カテゴリ別ガイダンス付きでそのまま作れるセクションよ。
          </p>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
          {error}
          <button onClick={() => setError('')} className="ml-2 underline">閉じる</button>
        </div>
      )}

      {/* Registered profiles */}
      <div className="rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] overflow-hidden">
        <div className="px-5 py-3 border-b border-[var(--card-border)] flex items-center justify-between">
          <h2 className="text-sm font-medium text-[var(--text)]">登録済みユーザー</h2>
          <span className="text-xs text-[var(--text-dim)]">{profiles.length} 人</span>
        </div>
        {loading ? (
          <div className="px-5 py-8 text-center text-sm text-[var(--text-dim)]">読み込み中...</div>
        ) : profiles.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-[var(--text-dim)]">
            まだ誰も登録されていません
          </div>
        ) : (
          <div className="divide-y divide-[var(--card-border)]">
            {profiles.map((p) => (
              <div key={p.name} className="px-5 py-3 flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-[var(--text)]">{p.display_name}</span>
                  <span className="ml-2 text-xs text-[var(--text-dim)]">@{p.name}</span>
                  <span className="ml-2 text-xs text-[var(--text-dim)]">{p.samples} サンプル</span>
                </div>
                <div>
                  {deleteConfirm === p.name ? (
                    <span className="text-xs space-x-2">
                      <span className="text-[var(--text-dim)]">削除？</span>
                      <button onClick={() => deleteProfile(p.name)} className="text-red-400 hover:text-red-300">はい</button>
                      <button onClick={() => setDeleteConfirm(null)} className="text-[var(--text-dim)] hover:text-[var(--text)]">いいえ</button>
                    </span>
                  ) : (
                    <button onClick={() => setDeleteConfirm(p.name)} className="text-xs text-[var(--text-dim)] hover:text-red-400 transition-colors">削除</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Enrollment */}
      <div className="rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] overflow-hidden">
        <div className="px-5 py-3 border-b border-[var(--card-border)]">
          <h2 className="text-sm font-medium text-[var(--text)]">新規登録</h2>
        </div>
        <div className="px-5 py-4 space-y-4">

          {/* Step 1: Form */}
          {step === 'form' && (
            <>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs text-[var(--text-dim)] mb-1">ユーザー ID</label>
                  <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="akira"
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] text-[var(--text)] placeholder:text-[var(--text-dim)] focus:outline-none focus:border-[var(--accent)]" />
                </div>
                <div>
                  <label className="block text-xs text-[var(--text-dim)] mb-1">表示名</label>
                  <input type="text" value={newDisplayName} onChange={(e) => setNewDisplayName(e.target.value)} placeholder="Akira"
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] text-[var(--text)] placeholder:text-[var(--text-dim)] focus:outline-none focus:border-[var(--accent)]" />
                </div>
                <div>
                  <label className="block text-xs text-[var(--text-dim)] mb-1">読みがな</label>
                  <input type="text" value={newYomigana} onChange={(e) => setNewYomigana(e.target.value)} placeholder="あきら"
                    className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] text-[var(--text)] placeholder:text-[var(--text-dim)] focus:outline-none focus:border-[var(--accent)]" />
                </div>
              </div>
              <p className="text-xs text-[var(--text-dim)]">
                「登録開始」を押すと、表示されるフレーズを読み上げて録音します（3〜5回）。
                テレビなど周囲の音はミュートにしてください。
              </p>
              <button onClick={startEnrollment} disabled={!newName.trim()}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-[var(--accent)] text-white hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed">
                登録開始
              </button>
            </>
          )}

          {/* Step 2: Recording */}
          {step === 'recording' && (
            <div className="space-y-4">
              {/* Progress */}
              <div className="flex items-center gap-2">
                {PHRASES.map((_, i) => (
                  <div key={i} className={`h-1.5 flex-1 rounded-full transition-colors ${
                    i < samplesOk ? 'bg-green-500' : i === phraseIndex ? 'bg-[var(--accent)]' : 'bg-[var(--card-border)]'
                  }`} />
                ))}
              </div>
              <p className="text-xs text-[var(--text-dim)]">
                サンプル {samplesOk} / 5（最低 3 個で登録可能）
              </p>

              {/* Phrase to read */}
              <div className="p-4 rounded-lg bg-[var(--input-bg)] border border-[var(--card-border)] text-center">
                <p className="text-xs text-[var(--text-dim)] mb-1">以下のフレーズを読んでください:</p>
                <p className="text-lg font-medium text-[var(--text)]">
                  「{PHRASES[phraseIndex]}」
                </p>
              </div>

              {/* Record button */}
              <div className="flex items-center gap-4">
                {!isRecording ? (
                  <button onClick={startRecording}
                    className="px-6 py-3 text-sm font-medium rounded-full bg-red-500 text-white hover:bg-red-600 transition-colors flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-white" />
                    録音開始
                  </button>
                ) : (
                  <button onClick={stopRecording}
                    className="px-6 py-3 text-sm font-medium rounded-full bg-red-700 text-white hover:bg-red-800 transition-colors animate-pulse flex items-center gap-2">
                    <span className="w-3 h-3 rounded-sm bg-white" />
                    録音停止
                  </button>
                )}

                {samplesOk >= 3 && !isRecording && (
                  <button onClick={() => finishEnrollment(samplesOk)}
                    className="px-4 py-3 text-sm font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 transition-colors">
                    登録完了 ({samplesOk} サンプル)
                  </button>
                )}
              </div>

              {sampleMsg && (
                <p className={`text-sm ${sampleMsg.includes('OK') ? 'text-green-400' : 'text-[var(--text-dim)]'}`}>
                  {sampleMsg}
                </p>
              )}

              <button onClick={cancelEnrollment}
                className="text-xs text-[var(--text-dim)] hover:text-[var(--text)] transition-colors underline">
                キャンセル
              </button>
            </div>
          )}

          {/* Step 3: Done */}
          {step === 'done' && (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="w-3 h-3 rounded-full bg-green-500" />
                <span className="text-sm text-green-400">{doneMsg}</span>
              </div>
              <button onClick={resetForm}
                className="px-4 py-2 text-sm rounded-lg border border-[var(--card-border)] text-[var(--text-dim)] hover:text-[var(--text)] transition-colors">
                別のユーザーを登録
              </button>
            </div>
          )}

        </div>
      </div>

      <div className="rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] overflow-hidden">
        <div className="px-5 py-3 border-b border-[var(--card-border)]">
          <h2 className="text-sm font-medium text-[var(--text)]">テスト音声作成</h2>
        </div>
        <div className="px-5 py-4 space-y-5">
          <div className="rounded-xl border border-[var(--card-border)] bg-[var(--input-bg)] p-4 space-y-2">
            <div className="text-xs uppercase tracking-[0.14em] text-[var(--accent)]">Guidance</div>
            <p className="text-sm text-[var(--text)]">{fixturePreset.guidance}</p>
            <div className="grid gap-2 text-xs text-[var(--text-dim)] md:grid-cols-3">
              <div>1. 下の台本をそのまま使う</div>
              <div>2. 0.5〜8秒くらいで止める</div>
              <div>3. 必要なら transcript だけ後で直す</div>
            </div>
          </div>

          <div className="rounded-xl border border-[var(--accent)]/30 bg-[var(--accent)]/8 p-5 text-center space-y-2">
            <div className="text-xs uppercase tracking-[0.14em] text-[var(--accent)]">{fixturePreset.scriptTitle}</div>
            <p className="text-lg font-medium text-[var(--text)]">
              「{fixturePreset.script}」
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <label className="block text-xs text-[var(--text-dim)] mb-1">カテゴリ</label>
              <select
                value={fixtureCategory}
                onChange={(e) => applyFixturePreset(e.target.value as FixtureCategory)}
                className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] text-[var(--text)] focus:outline-none focus:border-[var(--accent)]"
              >
                {Object.entries(TEST_AUDIO_PRESETS).map(([key, preset]) => (
                  <option key={key} value={key}>{preset.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-[var(--text-dim)] mb-1">scene</label>
              <input
                type="text"
                value={fixtureScene}
                onChange={(e) => setFixtureScene(e.target.value)}
                placeholder={fixturePreset.scenePlaceholder}
                className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] text-[var(--text)] placeholder:text-[var(--text-dim)] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>
            <div>
              <label className="block text-xs text-[var(--text-dim)] mb-1">variant</label>
              <input
                type="text"
                value={fixtureVariant}
                onChange={(e) => setFixtureVariant(e.target.value)}
                placeholder="01"
                className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] text-[var(--text)] placeholder:text-[var(--text-dim)] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="block text-xs text-[var(--text-dim)] mb-1">fixture id</label>
              <input
                type="text"
                value={fixtureId}
                onChange={(e) => setFixtureId(e.target.value)}
                placeholder={`${fixtureCategory}_${fixturePreset.scenePlaceholder}_01`}
                className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] text-[var(--text)] placeholder:text-[var(--text-dim)] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>
            <div className="rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] px-3 py-2 text-xs text-[var(--text-dim)] space-y-1">
              <div>WAV: <span className="text-[var(--text)] font-mono">{fixtureWavName}</span></div>
              <div>JSON: <span className="text-[var(--text)] font-mono">{fixtureJsonName}</span></div>
              <div>ID: <span className="text-[var(--text)] font-mono">{resolvedFixtureId}</span></div>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="block text-xs text-[var(--text-dim)] mb-1">expected_source</label>
              <select
                value={fixtureExpectedSource}
                onChange={(e) => setFixtureExpectedSource(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] text-[var(--text)] focus:outline-none focus:border-[var(--accent)]"
              >
                {['user_identified', 'user_initiative', 'user_response', 'user_likely', 'user_in_conversation', 'media_likely', 'fragmentary', 'unknown'].map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-[var(--text-dim)] mb-1">expected_intervention</label>
              <select
                value={fixtureExpectedIntervention}
                onChange={(e) => setFixtureExpectedIntervention(e.target.value as FixtureIntervention)}
                className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] text-[var(--text)] focus:outline-none focus:border-[var(--accent)]"
              >
                {['skip', 'backchannel', 'reply'].map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-xs text-[var(--text-dim)] mb-1">transcript</label>
              <input
                type="text"
                value={fixtureTranscript}
                onChange={(e) => setFixtureTranscript(e.target.value)}
                placeholder={fixturePreset.transcriptHint}
                className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] text-[var(--text)] placeholder:text-[var(--text-dim)] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>
            <div>
              <label className="block text-xs text-[var(--text-dim)] mb-1">notes</label>
              <textarea
                value={fixtureNotes}
                onChange={(e) => setFixtureNotes(e.target.value)}
                rows={3}
                placeholder={fixturePreset.notesHint}
                className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] text-[var(--text)] placeholder:text-[var(--text-dim)] focus:outline-none focus:border-[var(--accent)] resize-y"
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {!fixtureRecording ? (
              <button
                onClick={startFixtureRecording}
                className="px-5 py-2.5 text-sm font-medium rounded-full bg-[var(--accent)] text-white hover:opacity-90 transition-opacity"
              >
                テスト録音を開始
              </button>
            ) : (
              <button
                onClick={stopFixtureRecording}
                className="px-5 py-2.5 text-sm font-medium rounded-full bg-red-600 text-white hover:bg-red-700 transition-colors animate-pulse"
              >
                録音を停止
              </button>
            )}
            <button
              onClick={downloadFixtureWav}
              disabled={!fixtureBlob}
              className="px-4 py-2.5 text-sm rounded-lg border border-[var(--card-border)] text-[var(--text-dim)] hover:text-[var(--text)] transition-colors disabled:opacity-40"
            >
              WAV を保存
            </button>
            <button
              onClick={downloadFixtureJson}
              disabled={!fixtureTranscript.trim() || !fixtureNotes.trim()}
              className="px-4 py-2.5 text-sm rounded-lg border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)]/10 transition-colors disabled:opacity-40"
            >
              JSON を保存
            </button>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] p-4 text-sm text-[var(--text-dim)] space-y-2">
              <div className="font-medium text-[var(--text)]">保存後の置き場所</div>
              <div>1. 録音停止で `incoming/` に自動保存される</div>
              <div>2. transcript や notes を直すと sidecar も自動更新される</div>
              <div>3. あとは `import_incoming.py --dry-run` で確認するだけ</div>
            </div>
            <div className="rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] p-4 text-sm text-[var(--text-dim)] space-y-2">
              <div className="font-medium text-[var(--text)]">録音チェック</div>
              <div>まずは台本どおりに録れば十分</div>
              <div>読み終わったらすぐ停止で大丈夫</div>
              <div>transcript だけ必要に応じて直す</div>
            </div>
          </div>

          {fixtureStatus && (
            <p className="text-sm text-[var(--text-dim)]">{fixtureStatus}</p>
          )}
          {fixtureSavedPaths && (
            <div className="rounded-lg border border-[var(--card-border)] bg-[var(--input-bg)] p-4 text-xs text-[var(--text-dim)] space-y-1">
              <div className="text-[var(--text)] font-medium">自動保存先</div>
              <div className="font-mono break-all">{fixtureSavedPaths.wav}</div>
              <div className="font-mono break-all">{fixtureSavedPaths.json}</div>
            </div>
          )}
          {fixtureStartedAt && fixtureRecording && (
            <p className="text-xs text-[var(--text-dim)]">
              録音開始から {Math.max(1, Math.round((Date.now() - fixtureStartedAt) / 1000))} 秒
            </p>
          )}
          {fixtureDurationMs !== null && !fixtureRecording && (
            <p className="text-xs text-[var(--text-dim)]">
              直近の録音データサイズ: {Math.round(fixtureDurationMs / 1024)} KB
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
