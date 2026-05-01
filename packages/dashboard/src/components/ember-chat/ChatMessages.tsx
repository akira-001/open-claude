import { useEffect, useRef } from 'react';
import type { ChatMessage } from './types';
import {
  compactLabel,
  describeInterventionRisk,
  formatDb,
  formatPercent,
  formatSeconds,
  summarizeDiagnostics,
  titleForDiagnostic,
} from './diagnostics';

interface Props {
  messages: ChatMessage[];
}

export default function ChatMessages({ messages }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const summary = summarizeDiagnostics(messages);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="text-5xl mb-3 opacity-40">&#x1F525;</div>
          <p className="text-sm text-[var(--text-dim)]">Voice or text, your call.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-2">
      <div className="grid gap-2 md:grid-cols-5">
        <SummaryPill label="STT補正" value={summary.corrections} tone="amber" />
        <SummaryPill label="Media除外" value={summary.mediaSkips} tone="green" />
        <SummaryPill label="誤認識除外" value={summary.hallucinations} tone="slate" />
        <SummaryPill label="誤反応候補" value={summary.possibleFalseTriggers} tone={summary.possibleFalseTriggers > 0 ? 'red' : 'green'} />
        <SummaryPill label="発声注意" value={summary.ttsWarnings} tone={summary.ttsWarnings > 0 ? 'red' : 'green'} />
      </div>
      {messages.map((msg) => {
        if (msg.type === 'status' && msg.diagnostic) {
          return <DiagnosticMessage key={msg.id} message={msg} />;
        }
        if (msg.type === 'status') {
          return (
            <div key={msg.id} className="text-center text-xs text-[var(--text-dim)] italic py-1">
              {msg.text}
            </div>
          );
        }
        const isUser = msg.type === 'user';
        return (
          <div key={msg.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[80%] min-w-0 px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                isUser
                  ? 'bg-[var(--accent)]/10 border-l-2 border-[var(--accent)] text-[var(--text)]'
                  : 'bg-[var(--surface)] border border-[var(--border)] text-[var(--text)]'
              } ${isUser ? 'rounded-br-md' : 'rounded-bl-md'}`}
              style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}
            >
              {msg.botId && !isUser && (
                <span className="text-[10px] font-semibold text-[var(--accent)] uppercase tracking-wider block mb-1">
                  {msg.botId}
                </span>
              )}
              <span style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</span>
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}

function SummaryPill({ label, value, tone }: { label: string; value: number; tone: 'green' | 'amber' | 'red' | 'slate' }) {
  const toneClass = {
    green: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
    amber: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
    red: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
    slate: 'border-[var(--border)] bg-[var(--surface)] text-[var(--text-dim)]',
  }[tone];

  // Dim pills with no events so they recede into the background instead of
  // competing with the active diagnostic cards (esp. the 'thought' card).
  const idle = value === 0;

  return (
    <div className={`rounded-2xl border px-3 py-2 ${toneClass} ${idle ? 'opacity-40' : ''}`}>
      <div className="text-[10px] uppercase tracking-[0.18em] opacity-70">{label}</div>
      <div className="text-lg font-semibold leading-none mt-1">{value}</div>
    </div>
  );
}

function DiagnosticMessage({ message }: { message: ChatMessage }) {
  const diagnostic = message.diagnostic!;
  const interventionRisk = describeInterventionRisk(diagnostic);
  const tts = diagnostic.tts;
  const thought = diagnostic.thought;
  const severityClass =
    diagnostic.kind === 'hallucination' ? 'border-slate-500/30 bg-slate-900/40' :
    diagnostic.kind === 'ambient' && diagnostic.action !== 'skip' && diagnostic.potentialFalseTrigger ? 'border-rose-500/35 bg-rose-500/8' :
    diagnostic.kind === 'tts_eval' && (tts?.risk === 'high' || tts?.readingMatch === 'fail' || tts?.clipped) ? 'border-rose-500/35 bg-rose-500/8' :
    diagnostic.kind === 'stt_correction' ? 'border-amber-500/35 bg-amber-500/8' :
    diagnostic.kind === 'thought' ? 'border-violet-500/30 bg-violet-500/8' :
    'border-[var(--border)] bg-[var(--surface)]';

  return (
    <div className={`rounded-2xl border px-4 py-3 text-sm ${severityClass}`}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--text-dim)]">
            {titleForDiagnostic(diagnostic)}
          </div>
          <div className="text-[var(--text)] font-medium">{diagnostic.summary}</div>
        </div>
        {diagnostic.timeLabel && (
          <div className="text-xs text-[var(--text-dim)] font-mono">{diagnostic.timeLabel}</div>
        )}
      </div>

      {diagnostic.transcript && (
        <div className="mt-2 text-[var(--text)]">
          <span className="text-[var(--text-dim)] mr-2">Text</span>
          {compactLabel(diagnostic.transcript)}
        </div>
      )}

      {diagnostic.kind === 'stt_correction' && (
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          <KeyValue label="Raw" value={diagnostic.originalText} />
          <KeyValue label="Corrected" value={diagnostic.correctedText} />
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        {diagnostic.latencySec != null && <Tag label={`Latency ${formatSeconds(diagnostic.latencySec)}`} />}
        {diagnostic.source && <Tag label={`Source ${diagnostic.source}`} />}
        {diagnostic.method && <Tag label={`Method ${diagnostic.method}`} />}
        {diagnostic.model && <Tag label={`Model ${diagnostic.model}`} />}
        {diagnostic.reason && <Tag label={diagnostic.reason} tone={diagnostic.action === 'skip' ? 'green' : 'amber'} />}
        {diagnostic.audioBytes != null && <Tag label={`Audio ${diagnostic.audioBytes} bytes`} />}
      </div>

      {interventionRisk && (
        <div className="mt-3 text-xs text-[var(--text-dim)]">{interventionRisk}</div>
      )}

      {tts && (
        <div className="mt-3 grid gap-2 md:grid-cols-3">
          <Metric label="Text Match" value={formatPercent(tts.similarity) || 'n/a'} tone={tts.similarity != null && tts.similarity < 0.85 ? 'red' : 'green'} />
          <Metric label="Reading" value={tts.readingMatch?.toUpperCase() || 'n/a'} tone={tts.readingMatch === 'fail' ? 'red' : tts.readingMatch === 'warn' ? 'amber' : 'green'} />
          <Metric label="Risk" value={(tts.risk || 'n/a').toUpperCase()} tone={tts.risk === 'high' ? 'red' : tts.risk === 'medium' ? 'amber' : 'green'} />
          <Metric label="Duration" value={formatSeconds(tts.durationSec) || 'n/a'} tone="slate" />
          <Metric label="Peak" value={formatDb(tts.peakDb) || 'n/a'} tone="slate" />
          <Metric label="Clipping" value={tts.clipped ? 'Detected' : 'None'} tone={tts.clipped ? 'red' : 'green'} />
          <KeyValue label="Input" value={tts.inputText} />
          <KeyValue label="Re-STT" value={tts.retranscribedText} />
        </div>
      )}

      {thought && (
        <div className="mt-3 space-y-2">
          {diagnostic.botId && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase tracking-[0.18em] text-violet-300">{diagnostic.botId}</span>
              {thought.modeEstimate && (
                <span className="text-[10px] text-[var(--text-dim)]">{thought.modeEstimate}</span>
              )}
              {diagnostic.action === 'reply' && (
                <span className="rounded-full border border-emerald-400/60 bg-emerald-500/25 text-emerald-100 text-[10px] font-bold px-2 py-0.5 tracking-wider">SEND</span>
              )}
              {diagnostic.action === 'skip' && (
                <span className="rounded-full border border-amber-400/60 bg-amber-500/20 text-amber-100 text-[10px] font-bold px-2 py-0.5 tracking-wider">SKIP</span>
              )}
              {thought.evaluateScore != null && (
                <span className={`text-xs font-mono font-semibold ml-auto ${thought.evaluateScore >= 0.7 ? 'text-emerald-200' : thought.evaluateScore >= 0.4 ? 'text-amber-200' : 'text-rose-200'}`}>
                  eval {thought.evaluateScore.toFixed(2)}
                </span>
              )}
            </div>
          )}
          {thought.plan && thought.plan.length > 0 && (
            <div className="grid gap-1.5">
              {thought.plan.map((p, i) => {
                const score = thought.generateScore?.[i];
                const isTopPick = score != null && thought.generateScore != null
                  && score === Math.max(...thought.generateScore);
                return (
                  <div
                    key={i}
                    className={`flex items-center gap-2 text-xs rounded-lg border px-2.5 py-1.5 ${
                      isTopPick
                        ? 'border-violet-400/50 bg-violet-500/15'
                        : 'border-[var(--border)] bg-black/15'
                    }`}
                  >
                    <span className="text-violet-200 font-mono font-semibold w-5">#{i + 1}</span>
                    <span className="flex-1 text-[var(--text)]">{p}</span>
                    {score != null && (
                      <span className={`font-mono font-semibold ${score >= 0.7 ? 'text-emerald-200' : score >= 0.4 ? 'text-amber-200' : 'text-rose-200'}`}>
                        {score.toFixed(2)}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {thought.topic && (
            <KeyValue label="Topic" value={thought.topic} />
          )}
        </div>
      )}
    </div>
  );
}

function Tag({ label, tone = 'slate' }: { label: string; tone?: 'slate' | 'green' | 'amber' }) {
  const toneClass = {
    slate: 'border-[var(--border)] bg-black/10 text-[var(--text-dim)]',
    green: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
    amber: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  }[tone];

  return <span className={`rounded-full border px-2.5 py-1 ${toneClass}`}>{label}</span>;
}

function Metric({ label, value, tone }: { label: string; value: string; tone: 'green' | 'amber' | 'red' | 'slate' }) {
  const toneClass = {
    green: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100',
    amber: 'border-amber-500/30 bg-amber-500/10 text-amber-100',
    red: 'border-rose-500/30 bg-rose-500/10 text-rose-100',
    slate: 'border-[var(--border)] bg-black/10 text-[var(--text)]',
  }[tone];

  return (
    <div className={`rounded-xl border px-3 py-2 ${toneClass}`}>
      <div className="text-[10px] uppercase tracking-[0.18em] opacity-70">{label}</div>
      <div className="text-sm font-medium mt-1">{value}</div>
    </div>
  );
}

function KeyValue({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="rounded-xl border border-[var(--border)] bg-black/10 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--text-dim)]">{label}</div>
      <div className="text-sm text-[var(--text)] mt-1 break-words">{compactLabel(value)}</div>
    </div>
  );
}
