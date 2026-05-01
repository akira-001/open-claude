import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';
import type { EventSourceConfig, IntentionalPauseConfig } from './event-sources/types';
import { DEFAULT_EVENT_SOURCE_CONFIG, DEFAULT_INTENTIONAL_PAUSE_CONFIG } from './event-sources/types';

// ---------------------------------------------------------------------------
// Type definitions
// ---------------------------------------------------------------------------

export interface BotPersonality {
  systemPrompt: string;
  chatModel: string;   // model for DM/interactive chat
  cronModel: string;   // model for scheduled jobs
}

export interface BotSlackConfig {
  botToken: string;
  appToken: string;
  signingSecret: string;
  botUserId?: string;  // resolved at runtime via auth.test
}

export interface BotConfigJson {
  id: string;
  name: string;
  enabled: boolean;
  createdAt: string;
  slack: { botToken: string; appToken: string; signingSecret: string };
  personality: {
    type: string;
    motif: string;
    customPrompt: string | null;
    generatedPrompt: string | null;
  };
  models: { chat: string; cron: string };
  proactive: {
    enabled: boolean;
    schedule: string;
    slackTarget: string;
    calendarExclusions: string[];
  };
  rateLimits: {
    messagesPerMinute: number;
    botToBotMaxTurns: number;
    dailyLimit: number;
    cooldownMs: number;
  };
  tokenBudget: { hourlyUsd: number; dailyUsd: number };
  constants: Record<string, number>;
  mcpServers: string[];
  cronJobs: string[];
  eventSources?: EventSourceConfig;
  intentionalPause?: IntentionalPauseConfig;
  stampCompetition: { enabled: boolean };
  cogmem: { enabled: boolean; tokenBudget: number; recentLogs: number };
  debug: boolean;
  statePath: string;
  insightsPath: string;
}

export interface JobBackendConfig {
  backend: 'mlx' | 'ollama';
  model: string;  // model name on the selected backend
}

export interface LocalModelsConfig {
  mlx: {
    url: string;
    model: string;
    timeoutMs: number;
  };
  ollama: {
    url: string;
    embedModel: string;
  };
  jobs?: Record<string, JobBackendConfig>;
}

export const LOCAL_MODELS_DEFAULTS: LocalModelsConfig = {
  mlx: {
    url: 'http://localhost:8080/v1/chat/completions',
    model: 'mlx-community/Qwen3-32B-4bit',
    timeoutMs: 15000,
  },
  ollama: {
    url: 'http://localhost:11434',
    embedModel: 'zylonai/multilingual-e5-large',
  },
};

export interface BotConfigsFile {
  bots: BotConfigJson[];
  global: {
    botConversationChannel: string;
    sharedInsightsPath: string;
    localModels?: LocalModelsConfig;
  };
}

export function getLocalModelsConfig(): LocalModelsConfig {
  try {
    const file = loadBotConfigsJson();
    const saved = file.global?.localModels;
    if (!saved) return LOCAL_MODELS_DEFAULTS;
    return {
      mlx: { ...LOCAL_MODELS_DEFAULTS.mlx, ...saved.mlx },
      ollama: { ...LOCAL_MODELS_DEFAULTS.ollama, ...saved.ollama },
      jobs: saved.jobs,
    };
  } catch {
    return LOCAL_MODELS_DEFAULTS;
  }
}

// Runtime interface (backward compatible)
export interface BotConfig {
  id: string;
  name: string;        // config name
  displayName: string; // Slack profile display name (resolved at startup, fallback: name)
  slack: BotSlackConfig;
  personality: BotPersonality;
  statePath: string;   // per-bot state file path
  insightsPath: string; // shared insights path
  configJson: BotConfigJson; // reference to full JSON config
}

// ---------------------------------------------------------------------------
// Config file path
// ---------------------------------------------------------------------------

const CONFIG_PATH = join(process.cwd(), 'data', 'bot-configs.json');

// ---------------------------------------------------------------------------
// Identity persona loader
// ---------------------------------------------------------------------------

/**
 * Load persona text from identity/personas/<id>.md if it exists.
 * Falls back to empty string (caller uses customPrompt/generatedPrompt).
 * Override directory with EMBER_IDENTITY_DIR env var (useful for tests).
 */
function loadIdentityPersona(botId: string): string {
  const identityDir =
    process.env.EMBER_IDENTITY_DIR || join(process.cwd(), '..', '..', 'identity');
  const personaPath = join(identityDir, 'personas', `${botId}.md`);
  if (existsSync(personaPath)) {
    try {
      return readFileSync(personaPath, 'utf-8');
    } catch (e) {
      console.warn(`[bot-config] failed to read identity persona: ${personaPath}`, e);
    }
  }
  return '';
}

// ---------------------------------------------------------------------------
// Load SHARED_CAPABILITIES from skill files
// ---------------------------------------------------------------------------

function loadSharedCapabilities(): string {
  const SKILLS_DIR = join(process.cwd(), '.claude', 'skills');
  const skillFiles = ['memory-recall.md', 'file-sharing.md', 'user-insight.md', 'information-accuracy.md'];
  const sections: string[] = [];
  for (const file of skillFiles) {
    const filePath = join(SKILLS_DIR, file);
    if (existsSync(filePath)) {
      sections.push(readFileSync(filePath, 'utf-8').trim());
    }
  }
  return sections.join('\n\n');
}

// ---------------------------------------------------------------------------
// Env var expansion (same pattern as mcp-manager.ts)
// ---------------------------------------------------------------------------

function expandEnvVars(value: unknown): unknown {
  if (typeof value === 'string') {
    return value.replace(/\$\{([A-Z_][A-Z0-9_]*)\}/g, (_match, name: string) => {
      const v = process.env[name];
      if (v === undefined) {
        console.warn(`[bot-config] env var \${${name}} not set, leaving placeholder`);
        return _match;
      }
      return v;
    });
  }
  if (Array.isArray(value)) {
    return value.map((v) => expandEnvVars(v));
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = expandEnvVars(v);
    }
    return out;
  }
  return value;
}

// ---------------------------------------------------------------------------
// JSON file operations
// ---------------------------------------------------------------------------

export function loadBotConfigsJson(): BotConfigsFile {
  if (!existsSync(CONFIG_PATH)) {
    throw new Error(`Bot config file not found: ${CONFIG_PATH}`);
  }
  return expandEnvVars(JSON.parse(readFileSync(CONFIG_PATH, 'utf-8'))) as BotConfigsFile;
}

export function saveBotConfigsJson(configs: BotConfigsFile): void {
  writeFileSync(CONFIG_PATH, JSON.stringify(configs, null, 2), 'utf-8');
}

// ---------------------------------------------------------------------------
// Loader (backward compatible)
// ---------------------------------------------------------------------------

/**
 * Load bot configurations from data/bot-configs.json.
 * Builds system prompts by combining customPrompt/generatedPrompt with
 * shared capabilities loaded from .claude/skills/ files.
 */
export function loadBotConfigs(): BotConfig[] {
  const file = loadBotConfigsJson();
  const sharedCaps = loadSharedCapabilities();

  const configs = file.bots
    .filter(bot => bot.enabled)
    .map(bot => {
      // Apply defaults for optional config fields
      const botWithDefaults = {
        ...bot,
        eventSources: bot.eventSources ?? DEFAULT_EVENT_SOURCE_CONFIG,
        intentionalPause: bot.intentionalPause ?? DEFAULT_INTENTIONAL_PAUSE_CONFIG,
      };

      const identityPrompt = loadIdentityPersona(bot.id);
      const basePrompt = identityPrompt || bot.personality.customPrompt || bot.personality.generatedPrompt || '';
      const systemPrompt = basePrompt + '\n\n' + sharedCaps;
      return {
        id: bot.id,
        name: bot.name,
        displayName: bot.name, // resolved at startup via Slack API
        slack: {
          botToken: bot.slack.botToken,
          appToken: bot.slack.appToken,
          signingSecret: bot.slack.signingSecret,
        },
        personality: {
          systemPrompt,
          chatModel: bot.models.chat,
          cronModel: bot.models.cron,
        },
        statePath: bot.statePath,
        insightsPath: bot.insightsPath,
        configJson: botWithDefaults,
      };
    });

  if (configs.length === 0) {
    throw new Error(
      'No enabled bot configurations found in data/bot-configs.json.',
    );
  }

  return configs;
}

/**
 * Convenience: find a single bot config by id.
 */
export function getBotConfig(
  configs: BotConfig[],
  id: string,
): BotConfig | undefined {
  return configs.find((c) => c.id === id);
}
