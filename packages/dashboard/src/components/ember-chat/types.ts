// dashboard/src/components/ember-chat/types.ts

export interface ChatMessage {
  id: string;
  type: 'user' | 'assistant' | 'status' | 'proactive' | 'debug';
  text: string;
  botId?: string;
  timestamp: number;
  diagnostic?: DiagnosticEvent;
}

export type DiagnosticKind =
  | 'stt'
  | 'stt_correction'
  | 'ambient'
  | 'batch'
  | 'hallucination'
  | 'tts_eval'
  | 'audio'
  | 'thought'
  | 'unknown';

// Inner Thoughts paper (arxiv 2501.00383) + Anthropic Plan-Generate-Evaluate.
// Surfaces what a bot was thinking before deciding to send / skip — only shown
// in EmberChat when debugMode is on (kind: 'thought' is filtered otherwise).
export interface ThoughtPayload {
  innerThought?: string;
  plan?: string[];
  generateScore?: number[];
  evaluateScore?: number;
  topic?: string;
  category?: string;
  modeEstimate?: string;
}

export interface TtsEvaluation {
  inputText?: string;
  retranscribedText?: string;
  similarity?: number;
  readingMatch?: 'ok' | 'warn' | 'fail';
  durationSec?: number;
  peakDb?: number;
  clipped?: boolean;
  risk?: 'low' | 'medium' | 'high';
}

export interface DiagnosticEvent {
  kind: DiagnosticKind;
  label: string;
  timeLabel?: string;
  summary: string;
  transcript?: string;
  originalText?: string;
  correctedText?: string;
  source?: string;
  action?: 'skip' | 'buffer' | 'reply' | 'backchannel' | 'unknown';
  reason?: string;
  confidence?: number;
  latencySec?: number;
  audioBytes?: number;
  model?: string;
  method?: string;
  potentialFalseTrigger?: boolean;
  tts?: TtsEvaluation;
  thought?: ThoughtPayload;
  botId?: string;
  raw: string;
}

export interface EmberSettings {
  ttsEngine: string;
  voiceSelect: string;
  speedSelect: string;
  modelSelect: string;
  ambientModel: string;
  meiEngine: string;
  meiVoice: string;
  meiSpeed: string;
  eveEngine: string;
  eveVoice: string;
  eveSpeed: string;
  ttsEnabled: boolean;
  proactiveEnabled: boolean;
  emojiEnabled: boolean;
  debugMode: boolean;
  settingsExpanded: boolean;
  yomiganaPersonalEntries: YomiganaEntry[];
  lastSeen: Record<string, string>;
}

export interface Speaker {
  name: string;
  styles: { id: string | number; name: string }[];
}

export interface OllamaModel {
  name: string;
  size: string;
}

export interface YomiganaEntry {
  from: string;
  to: string;
}

export interface YomiganaRule {
  pattern: string;
  replacement: string;
}

export const DEFAULT_SETTINGS: EmberSettings = {
  ttsEngine: 'voicevox',
  voiceSelect: '2',
  speedSelect: '1.0',
  modelSelect: 'gemma4:e4b',
  ambientModel: 'gemma4:e4b',
  meiEngine: 'irodori',
  meiVoice: 'irodori-bright-female',
  meiSpeed: '1.0',
  eveEngine: 'irodori',
  eveVoice: 'irodori-calm-female',
  eveSpeed: '1.0',
  ttsEnabled: true,
  proactiveEnabled: false,
  emojiEnabled: true,
  debugMode: false,
  settingsExpanded: false,
  yomiganaPersonalEntries: [],
  lastSeen: {},
};

export const SPEED_OPTIONS = ['0.8', '1.0', '1.2', '1.5', '2.0'];

export const STEPS_OPTIONS = ['auto', '8', '10', '15', '20', '30', '40'];

export const TTS_ENGINES = [
  { value: 'voicevox', label: 'VOICEVOX' },
  { value: 'irodori', label: 'Irodori' },
  { value: 'gptsovits', label: 'GPT-SoVITS' },
];
