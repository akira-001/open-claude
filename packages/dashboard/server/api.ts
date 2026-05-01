import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import { readFileSync, writeFileSync, appendFileSync, existsSync, mkdirSync, rmSync } from 'fs';
import { execSync, execFile, spawn } from 'child_process';
import path from 'path';
import { homedir } from 'os';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');
const DATA_DIR = path.join(ROOT, 'data');
const BOT_CONFIGS_FILE = path.join(DATA_DIR, 'bot-configs.json');
const INSIGHTS_FILE = path.join(DATA_DIR, 'user-insights.json');
const PERSONALITY_TEMPLATES_FILE = path.join(DATA_DIR, 'personality-templates.json');
const CRON_FILE = path.join(ROOT, 'cron-jobs.json');
const DEFAULT_CRON_SLACK_TARGET = 'C0AHPJMS5QE';
const MCP_FILE = path.join(ROOT, 'mcp-servers.json');
const ENV_FILE = path.join(ROOT, '.env');
const STAMP_DIR = DATA_DIR; // stamp files in data/
const AUDIO_FIXTURE_INCOMING_DIR = path.resolve(ROOT, '../voice-chat/tests/fixtures/audio/incoming');

const app = express();
app.use(express.json({ limit: '1mb' }));

// --- CORS for dashboard dev mode ---
app.use((_req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, PUT, POST, DELETE, PATCH, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type');
  if (_req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

// --- Helpers ---
function readJSON(filePath: string): any {
  if (!existsSync(filePath)) return null;
  return JSON.parse(readFileSync(filePath, 'utf-8'));
}

function writeJSON(filePath: string, data: any): void {
  writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');
}

function loadConfigs(): any {
  return readJSON(BOT_CONFIGS_FILE) || { bots: [], global: {} };
}

function saveConfigs(configs: any): void {
  writeJSON(BOT_CONFIGS_FILE, configs);
}

function findBot(configs: any, botId: string): any {
  return configs.bots.find((b: any) => b.id === botId);
}

function getProactiveCronJobName(botId: string): string {
  return botId === 'mei' ? 'proactive-checkin' : `proactive-checkin-${botId}`;
}

function findProactiveCronJob(cronData: any, botId: string): any | undefined {
  const jobName = getProactiveCronJobName(botId);
  return cronData?.jobs?.find((j: any) => j.name === jobName);
}

function getStatePath(botId: string): string {
  const configs = loadConfigs();
  const bot = findBot(configs, botId);
  return bot ? path.join(ROOT, bot.statePath) : path.join(DATA_DIR, `${botId}-state.json`);
}

function redactCredentials(bot: any): any {
  return {
    ...bot,
    slack: {
      botToken: bot.slack.botToken ? '***' + bot.slack.botToken.slice(-8) : '',
      appToken: bot.slack.appToken ? '***' + bot.slack.appToken.slice(-8) : '',
      signingSecret: bot.slack.signingSecret ? '***' + bot.slack.signingSecret.slice(-8) : '',
    },
  };
}

function ensureDir(dirPath: string): void {
  if (!existsSync(dirPath)) mkdirSync(dirPath, { recursive: true });
}

function sanitizeFixtureBaseName(raw: string): string {
  const value = String(raw || '').trim();
  if (!/^[a-z0-9_]+(?:__[a-z0-9_]+){2}$/.test(value)) {
    throw new Error('Invalid fixture base name');
  }
  return value;
}

function sanitizeFixtureId(raw: string): string {
  const value = String(raw || '').trim();
  if (!/^[a-z0-9_]+$/.test(value)) {
    throw new Error('Invalid fixture id');
  }
  return value;
}

function fixturePaths(baseName: string): { wavPath: string; jsonPath: string } {
  return {
    wavPath: path.join(AUDIO_FIXTURE_INCOMING_DIR, `${baseName}.wav`),
    jsonPath: path.join(AUDIO_FIXTURE_INCOMING_DIR, `${baseName}.json`),
  };
}

function resolveShellPath(): string {
  const candidates = [
    '/bin/zsh',
    '/bin/bash',
    '/bin/sh',
    process.env.CRON_SHELL,
    process.env.SHELL,
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }

  throw new Error('No usable shell found for cron command execution');
}

function parseDirectCommand(command: string, defaultCwd: string): { cwd?: string; file: string; args: string[] } | null {
  const cdMatch = command.match(/^\s*cd\s+(.+?)\s*&&\s*(.+)\s*$/);
  if (cdMatch) {
    const cwd = cdMatch[1].trim();
    const rest = cdMatch[2].trim();
    const parts = rest.match(/(?:"[^"]*"|'[^']*'|\S+)/g);
    if (!parts || parts.length === 0) return null;
    const file = parts[0].replace(/^['"]|['"]$/g, '');
    const args = parts.slice(1).map((part) => part.replace(/^['"]|['"]$/g, ''));
    return {
      cwd,
      file: file.startsWith('/') || file.startsWith('.') ? path.resolve(cwd, file) : file,
      args,
    };
  }

  const parts = command.match(/(?:"[^"]*"|'[^']*'|\S+)/g);
  if (!parts || parts.length === 0) return null;
  if (parts.some((part) => /[|;&<>$`]/.test(part))) {
    return null;
  }

  const file = parts[0].replace(/^['"]|['"]$/g, '');
  const args = parts.slice(1).map((part) => part.replace(/^['"]|['"]$/g, ''));
  return {
    cwd: defaultCwd,
    file: file.startsWith('/') || file.startsWith('.') ? path.resolve(defaultCwd, file) : file,
    args,
  };
}

// ===================================================================
// BOT MANAGEMENT
// ===================================================================

// ===================================================================
// AUDIO FIXTURE INCOMING
// ===================================================================

app.post('/api/audio-fixtures/save', (req, res) => {
  try {
    const {
      baseName,
      previousBaseName,
      wavBase64,
      sidecar,
    } = req.body || {};

    const normalizedBaseName = sanitizeFixtureBaseName(baseName);
    const normalizedPrevious = previousBaseName ? sanitizeFixtureBaseName(previousBaseName) : null;

    if (!wavBase64 || typeof wavBase64 !== 'string') {
      return res.status(400).json({ error: 'wavBase64 is required' });
    }
    if (!sidecar || typeof sidecar !== 'object') {
      return res.status(400).json({ error: 'sidecar is required' });
    }

    const requiredStringFields = ['category', 'scene', 'variant', 'transcript', 'expected_source', 'expected_intervention', 'notes'] as const;
    for (const key of requiredStringFields) {
      if (typeof sidecar[key] !== 'string') {
        return res.status(400).json({ error: `sidecar.${key} must be a string` });
      }
    }

    ensureDir(AUDIO_FIXTURE_INCOMING_DIR);

    if (normalizedPrevious && normalizedPrevious !== normalizedBaseName) {
      const previousPaths = fixturePaths(normalizedPrevious);
      if (existsSync(previousPaths.wavPath)) rmSync(previousPaths.wavPath);
      if (existsSync(previousPaths.jsonPath)) rmSync(previousPaths.jsonPath);
    }

    const payload = {
      category: sidecar.category,
      scene: sidecar.scene,
      variant: sidecar.variant,
      id: sanitizeFixtureId(sidecar.id || `${sidecar.category}_${sidecar.scene}_${sidecar.variant}`),
      transcript: sidecar.transcript,
      expected_source: sidecar.expected_source,
      expected_intervention: sidecar.expected_intervention,
      notes: sidecar.notes,
    };

    const { wavPath, jsonPath } = fixturePaths(normalizedBaseName);
    const wavBuffer = Buffer.from(wavBase64, 'base64');
    writeFileSync(wavPath, wavBuffer);
    writeFileSync(jsonPath, JSON.stringify(payload, null, 2) + '\n', 'utf-8');

    res.json({
      ok: true,
      saved: {
        wav: wavPath,
        json: jsonPath,
      },
    });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// List all bots (summary, credentials redacted)
app.get('/api/bots', (_req, res) => {
  try {
    const configs = loadConfigs();
    const bots = configs.bots.map((b: any) => ({
      id: b.id,
      name: b.name,
      enabled: b.enabled,
      models: b.models,
      personality: { type: b.personality.type, motif: b.personality.motif },
    }));
    res.json(bots);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// Get single bot config (credentials redacted)
app.get('/api/bots/:botId', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    res.json(redactCredentials(bot));
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// Resolve bot identity from Slack token
app.post('/api/bots/resolve-identity', async (req, res) => {
  try {
    const { botToken } = req.body;
    if (!botToken) {
      return res.status(400).json({ error: 'botToken is required' });
    }

    const { App } = await import('@slack/bolt');
    const tempApp = new App({ token: botToken, signingSecret: 'dummy' });

    const auth = await tempApp.client.auth.test({ token: botToken });
    const botId = auth.bot_id as string;
    const userId = auth.user_id as string;

    let displayName = auth.user as string;
    try {
      const userInfo = await tempApp.client.users.info({ token: botToken, user: userId });
      const profile = (userInfo.user as any)?.profile;
      displayName = profile?.display_name || profile?.real_name || displayName;
    } catch {
      // users:read scope missing — fallback to username
    }

    res.json({ botId, userId, displayName, username: auth.user });
  } catch (e: any) {
    res.status(400).json({ error: `Slack API error: ${e.message}` });
  }
});

// Create new bot
app.post('/api/bots', async (req, res) => {
  try {
    const configs = loadConfigs();
    const newBot = req.body;

    // Validate: botToken is required, id/name are auto-resolved if missing
    if (!newBot.slack?.botToken) {
      return res.status(400).json({ error: 'slack.botToken is required' });
    }

    // Auto-resolve id and name from Slack API if not provided
    if (!newBot.id || !newBot.name) {
      const { App } = await import('@slack/bolt');
      const tempApp = new App({ token: newBot.slack.botToken, signingSecret: 'dummy' });
      const auth = await tempApp.client.auth.test({ token: newBot.slack.botToken });

      if (!newBot.id) {
        newBot.id = auth.bot_id as string;
      }
      if (!newBot.name) {
        newBot.name = auth.user as string;
        try {
          const userInfo = await tempApp.client.users.info({
            token: newBot.slack.botToken,
            user: auth.user_id as string,
          });
          const profile = (userInfo.user as any)?.profile;
          newBot.name = profile?.display_name || profile?.real_name || newBot.name;
        } catch { /* fallback to username */ }
      }
    }

    // Check for duplicate ID
    if (findBot(configs, newBot.id)) {
      return res.status(409).json({ error: `Bot with id '${newBot.id}' already exists` });
    }

    // Apply defaults
    const bot = {
      id: newBot.id,
      name: newBot.name,
      enabled: newBot.enabled ?? true,
      createdAt: new Date().toISOString(),
      slack: newBot.slack,
      personality: newBot.personality || { type: 'analyst', motif: 'charlie_munger', customPrompt: null, generatedPrompt: null },
      models: newBot.models || { chat: 'claude-sonnet-4-6', cron: 'claude-sonnet-4-6' },
      proactive: newBot.proactive || { enabled: false, schedule: '0 9,11,14,17,20 * * *', slackTarget: 'U3SFGQXNH', calendarExclusions: [] },
      rateLimits: newBot.rateLimits || { messagesPerMinute: 5, botToBotMaxTurns: 6, dailyLimit: 50, cooldownMs: 60000 },
      tokenBudget: newBot.tokenBudget || { hourlyUsd: 5.0, dailyUsd: 50.0 },
      constants: newBot.constants || {
        LEARNING_RATE: 0.1, WEIGHT_MIN: 0.05, WEIGHT_MAX: 2.0, MAX_HISTORY: 100,
        MAX_BACKOFF_MINUTES: 480, INSIGHT_BASE_HALF_LIFE: 60, INSIGHT_DECAY_FLOOR: 0.3,
        INSIGHT_DEFAULT_AROUSAL: 0.5, INSIGHT_REINFORCE_DELTA: 0.15,
        INSIGHT_ACTIVE_THRESHOLD: 0.35, INSIGHT_SIMILARITY_THRESHOLD: 0.88,
      },
      mcpServers: newBot.mcpServers || [],
      cronJobs: newBot.cronJobs || [],
      stampCompetition: newBot.stampCompetition || { enabled: true },
      cogmem: newBot.cogmem || { enabled: false, tokenBudget: 8000, recentLogs: 3 },
      debug: newBot.debug ?? false,
      statePath: `data/${newBot.id}-state.json`,
      insightsPath: 'data/user-insights.json',
    };

    configs.bots.push(bot);
    saveConfigs(configs);

    // Also add tokens to .env file
    const envAdditions = [
      `SLACK_BOT_TOKEN_${newBot.id.toUpperCase()}=${newBot.slack.botToken}`,
      `SLACK_APP_TOKEN_${newBot.id.toUpperCase()}=${newBot.slack.appToken}`,
      `SLACK_SIGNING_SECRET_${newBot.id.toUpperCase()}=${newBot.slack.signingSecret}`,
    ].join('\n');

    let envContent = existsSync(ENV_FILE) ? readFileSync(ENV_FILE, 'utf-8') : '';
    envContent += '\n' + envAdditions + '\n';
    writeFileSync(ENV_FILE, envContent, 'utf-8');

    res.json({ ok: true, botId: bot.id });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// Update bot config
app.put('/api/bots/:botId', (req, res) => {
  try {
    const configs = loadConfigs();
    const botIndex = configs.bots.findIndex((b: any) => b.id === req.params.botId);
    if (botIndex === -1) return res.status(404).json({ error: 'Bot not found' });

    const updates = req.body;
    // Don't allow changing the id
    delete updates.id;
    // Don't overwrite slack if credentials are redacted (contain ***)
    if (updates.slack && updates.slack.botToken?.includes('***')) {
      delete updates.slack;
    }

    configs.bots[botIndex] = { ...configs.bots[botIndex], ...updates };
    saveConfigs(configs);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// Delete bot
app.delete('/api/bots/:botId', (req, res) => {
  try {
    const configs = loadConfigs();
    const botIndex = configs.bots.findIndex((b: any) => b.id === req.params.botId);
    if (botIndex === -1) return res.status(404).json({ error: 'Bot not found' });
    configs.bots.splice(botIndex, 1);
    saveConfigs(configs);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// Enable bot
app.post('/api/bots/:botId/enable', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    bot.enabled = true;
    saveConfigs(configs);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// Disable bot
app.post('/api/bots/:botId/disable', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    bot.enabled = false;
    saveConfigs(configs);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// PER-BOT STATE
// ===================================================================

// Get bot proactive state
app.get('/api/bots/:botId/state', (req, res) => {
  try {
    const statePath = getStatePath(req.params.botId);
    const state = readJSON(statePath);
    if (!state) {
      return res.json({
        categoryWeights: {}, cooldown: { until: null, consecutiveIgnores: 0, backoffMinutes: 0 },
        history: [], lastCheckAt: null, stats: { totalSent: 0, positiveReactions: 0, negativeReactions: 0 },
      });
    }
    res.json(state);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// Update category weights
app.put('/api/bots/:botId/state/weights', (req, res) => {
  try {
    const statePath = getStatePath(req.params.botId);
    const state = readJSON(statePath);
    if (!state) return res.status(404).json({ error: 'State file not found' });
    state.categoryWeights = { ...state.categoryWeights, ...req.body.categoryWeights };
    writeJSON(statePath, state);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// Reset cooldown
app.put('/api/bots/:botId/state/cooldown/reset', (_req, res) => {
  try {
    const statePath = getStatePath(_req.params.botId);
    const state = readJSON(statePath);
    if (!state) return res.status(404).json({ error: 'State file not found' });
    state.cooldown = { until: null, consecutiveIgnores: 0, backoffMinutes: 0 };
    writeJSON(statePath, state);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// PER-BOT CONSTANTS
// ===================================================================

app.get('/api/bots/:botId/constants', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    res.json(bot.constants);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/bots/:botId/constants', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    bot.constants = { ...bot.constants, ...req.body };
    saveConfigs(configs);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// PER-BOT PROMPT
// ===================================================================

app.get('/api/bots/:botId/prompt', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    res.json({
      prompt: bot.personality.customPrompt || bot.personality.generatedPrompt || '',
      personality: { type: bot.personality.type, motif: bot.personality.motif },
    });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/bots/:botId/prompt', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    if (req.body.prompt !== undefined) bot.personality.customPrompt = req.body.prompt;
    if (req.body.type !== undefined) bot.personality.type = req.body.type;
    if (req.body.motif !== undefined) bot.personality.motif = req.body.motif;
    if (req.body.generatedPrompt !== undefined) bot.personality.generatedPrompt = req.body.generatedPrompt;
    saveConfigs(configs);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// PER-BOT PROACTIVE CONFIG
// ===================================================================

app.get('/api/bots/:botId/proactive', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    // Return actual cron schedule from cron-jobs.json (source of truth)
    const cronData = readJSON(CRON_FILE);
    const cronJob = findProactiveCronJob(cronData, req.params.botId);
    const result = { ...bot.proactive };
    if (cronJob?.cron) result.schedule = cronJob.cron;
    res.json(result);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/bots/:botId/proactive', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    const { schedule, ...rest } = req.body;
    bot.proactive = {
      ...bot.proactive,
      ...rest,
      ...(schedule !== undefined ? { schedule } : {}),
    };
    saveConfigs(configs);

    if (schedule !== undefined) {
      const cronData = readJSON(CRON_FILE) || { jobs: [] };
      cronData.jobs = Array.isArray(cronData.jobs) ? cronData.jobs : [];
      const jobName = getProactiveCronJobName(req.params.botId);
      const cronJob = findProactiveCronJob(cronData, req.params.botId);
      if (cronJob) {
        cronJob.cron = schedule;
      } else {
        cronData.jobs.push({
          name: jobName,
          summary: `${bot.name} プロアクティブチェックイン`,
          description: `${bot.name} のプロアクティブ配信`,
          cron: schedule,
          tz: 'Asia/Tokyo',
          message: '',
          slackTarget: bot.proactive.slackTarget,
          timeoutSeconds: 300,
          enabled: bot.proactive.enabled,
          botId: bot.id,
        });
      }
      writeJSON(CRON_FILE, cronData);
    }

    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// PER-BOT MODELS & LIMITS
// ===================================================================

app.get('/api/bots/:botId/models', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    res.json({ models: bot.models, rateLimits: bot.rateLimits, tokenBudget: bot.tokenBudget });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/bots/:botId/models', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    if (req.body.models) bot.models = { ...bot.models, ...req.body.models };
    if (req.body.rateLimits) bot.rateLimits = { ...bot.rateLimits, ...req.body.rateLimits };
    if (req.body.tokenBudget) bot.tokenBudget = { ...bot.tokenBudget, ...req.body.tokenBudget };
    saveConfigs(configs);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// PER-BOT CRON JOBS
// ===================================================================

app.get('/api/bots/:botId/cron-jobs', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    res.json(bot.cronJobs || []);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/bots/:botId/cron-jobs', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    bot.cronJobs = req.body.cronJobs || [];
    saveConfigs(configs);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// PER-BOT MCP SERVERS
// ===================================================================

app.get('/api/bots/:botId/mcp-servers', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    res.json(bot.mcpServers || []);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/bots/:botId/mcp-servers', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    bot.mcpServers = req.body.mcpServers || [];
    saveConfigs(configs);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// INSIGHTS (shared)
// ===================================================================

app.get('/api/insights', (_req, res) => {
  try {
    const insights = readJSON(INSIGHTS_FILE) ?? [];
    const stripped = insights.map((i: any) => {
      const { embedding, ...rest } = i;
      return rest;
    });
    res.json(stripped);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/insights', (req, res) => {
  try {
    const insights = readJSON(INSIGHTS_FILE) ?? [];
    insights.push({
      insight: req.body.insight,
      learnedAt: new Date().toISOString(),
      source: req.body.source ?? 'dashboard',
      arousal: req.body.arousal ?? 0.5,
      reinforceCount: 0,
    });
    writeJSON(INSIGHTS_FILE, insights);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/insights/:index', (req, res) => {
  try {
    const insights = readJSON(INSIGHTS_FILE) ?? [];
    const idx = parseInt(req.params.index);
    if (idx < 0 || idx >= insights.length) return res.status(404).json({ error: 'Index out of range' });
    insights[idx] = { ...insights[idx], ...req.body };
    writeJSON(INSIGHTS_FILE, insights);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.delete('/api/insights/:index', (req, res) => {
  try {
    const insights = readJSON(INSIGHTS_FILE) ?? [];
    const idx = parseInt(req.params.index);
    if (idx < 0 || idx >= insights.length) return res.status(404).json({ error: 'Index out of range' });
    insights.splice(idx, 1);
    writeJSON(INSIGHTS_FILE, insights);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// PERSONALITY TEMPLATES
// ===================================================================

app.get('/api/personality/templates', (_req, res) => {
  try {
    const templates = readJSON(PERSONALITY_TEMPLATES_FILE);
    if (!templates) return res.status(404).json({ error: 'personality-templates.json not found' });
    res.json(templates);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/personality/generate', (req, res) => {
  try {
    const templates = readJSON(PERSONALITY_TEMPLATES_FILE);
    if (!templates) return res.status(404).json({ error: 'personality-templates.json not found' });

    const { botName, type, motif } = req.body;
    if (!botName || !type || !motif) {
      return res.status(400).json({ error: 'botName, type, and motif are required' });
    }

    const typeTemplate = templates.types.find((t: any) => t.id === type);
    const motifTemplate = templates.motifs.find((m: any) => m.id === motif);

    if (!typeTemplate) return res.status(404).json({ error: `Type '${type}' not found` });
    if (!motifTemplate) return res.status(404).json({ error: `Motif '${motif}' not found` });

    let prompt = templates.promptTemplate;
    prompt = prompt.replace(/\{\{botName\}\}/g, botName);
    prompt = prompt.replace(/\{\{typeLabel\}\}/g, typeTemplate.label);
    prompt = prompt.replace(/\{\{thinkingStyle\}\}/g, typeTemplate.thinkingStyle);
    prompt = prompt.replace(/\{\{debateStyle\}\}/g, typeTemplate.debateStyle);
    prompt = prompt.replace(/\{\{motifLabel\}\}/g, motifTemplate.label);
    prompt = prompt.replace(/\{\{background\}\}/g, motifTemplate.background);
    prompt = prompt.replace(/\{\{perspective\}\}/g, motifTemplate.perspective);

    res.json({ prompt });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// GLOBAL RESOURCES
// ===================================================================

// All cron jobs
app.get('/api/cron-jobs', (_req, res) => {
  try {
    const data = readJSON(CRON_FILE);
    if (!data) return res.json([]);
    res.json(data.jobs || []);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// Cron job detail with execution history
const CRON_HISTORY_FILE = path.join(ROOT, 'data', 'cron-history.jsonl');

function readCronHistory(jobName?: string, limit = 50): any[] {
  if (!existsSync(CRON_HISTORY_FILE)) return [];
  try {
    const lines = readFileSync(CRON_HISTORY_FILE, 'utf-8').split('\n').filter(l => l.trim());
    let entries = lines.map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
    if (jobName) entries = entries.filter((e: any) => e.jobName === jobName);
    // newest first
    entries.reverse();
    return entries.slice(0, limit);
  } catch {
    return [];
  }
}

app.get('/api/cron-jobs/:name', (req, res) => {
  try {
    const data = readJSON(CRON_FILE);
    if (!data) return res.status(404).json({ error: 'cron-jobs.json not found' });
    const job = (data.jobs || []).find((j: any) => j.name === req.params.name);
    if (!job) return res.status(404).json({ error: 'Job not found' });
    const history = readCronHistory(req.params.name, 20);
    res.json({ job, history });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/cron-jobs/:name/history', (req, res) => {
  try {
    const history = readCronHistory(req.params.name, 50);
    res.json(history);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/cron-jobs', (req, res) => {
  try {
    const data = readJSON(CRON_FILE) || { jobs: [] };
    const { name, summary, cron, message, command, slackTarget, timeoutSeconds, botId } = req.body;
    if (!name || !cron) return res.status(400).json({ error: 'name and cron are required' });
    if ((data.jobs || []).some((j: any) => j.name === name)) {
      return res.status(409).json({ error: `Job "${name}" already exists` });
    }
    const newJob = {
      name,
      summary: summary || '',
      description: '',
      cron,
      tz: 'Asia/Tokyo',
      message: message || '',
      command: command || undefined,
      slackTarget: slackTarget || DEFAULT_CRON_SLACK_TARGET,
      timeoutSeconds: timeoutSeconds || 120,
      enabled: true,
      botId: botId || 'mei',
    };
    data.jobs.push(newJob);
    writeJSON(CRON_FILE, data);
    res.json({ ok: true, job: newJob });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/cron-jobs/:name', (req, res) => {
  try {
    const data = readJSON(CRON_FILE);
    if (!data) return res.status(404).json({ error: 'cron-jobs.json not found' });
    const jobIndex = (data.jobs || []).findIndex((j: any) => j.name === req.params.name);
    if (jobIndex === -1) return res.status(404).json({ error: 'Job not found' });

    data.jobs[jobIndex] = { ...data.jobs[jobIndex], ...req.body };
    writeJSON(CRON_FILE, data);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// Run cron job manually
app.post('/api/cron-jobs/:name/run', (req, res) => {
  try {
    const data = readJSON(CRON_FILE);
    if (!data) return res.status(404).json({ error: 'cron-jobs.json not found' });
    const job = (data.jobs || []).find((j: any) => j.name === req.params.name);
    if (!job) return res.status(404).json({ error: 'Job not found' });

    const startTime = Date.now();
    const timeoutMs = (job.timeoutSeconds || 300) * 1000;
    const INTERNAL_API = `http://127.0.0.1:${process.env.INTERNAL_API_PORT || 3457}`;

    // Proactive checkin or jobs with no command/message: use internal API
    if (!job.command && !job.message) {
      (async () => {
        try {
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), timeoutMs);
          const botId = job.botId || 'mei';
          const resp = await fetch(`${INTERNAL_API}/internal/run-proactive?botId=${botId}`, {
            method: 'POST',
            signal: controller.signal,
          });
          clearTimeout(timeout);
          const result = await resp.json() as any;
          const durationMs = Date.now() - startTime;

          const entry: any = {
            jobName: job.name,
            startedAt: new Date(startTime).toISOString(),
            completedAt: new Date().toISOString(),
            durationMs,
            status: result.status === 'success' ? 'success' : 'error',
            botId: job.botId || 'mei',
            error: result.error || null,
            outputPreview: '',
          };

          try {
            mkdirSync(path.join(ROOT, 'data'), { recursive: true });
            appendFileSync(CRON_HISTORY_FILE, JSON.stringify(entry) + '\n');
          } catch { /* ignore */ }

          res.json({ status: result.status || 'success', durationMs });
        } catch (e: any) {
          res.json({ status: 'error', error: e.message, durationMs: Date.now() - startTime });
        }
      })();
      return;
    }

    // Jobs with command: run directly
    if (job.command) {
      const direct = parseDirectCommand(job.command, ROOT);
      if (direct) {
        execFile(direct.file, direct.args, { timeout: timeoutMs, cwd: direct.cwd || ROOT }, (error, stdout, stderr) => {
          const durationMs = Date.now() - startTime;
          const output = stdout || stderr || '';
          const entry: any = {
            jobName: job.name,
            startedAt: new Date(startTime).toISOString(),
            completedAt: new Date().toISOString(),
            durationMs,
            status: error ? 'error' : 'success',
            botId: job.botId || 'mei',
            error: error ? (error.message || 'Unknown error') : null,
            outputPreview: (() => {
              // Try to extract Slack payload JSON from output (may have log lines before it)
              const lines = output.trim().split('\n');
              for (let i = lines.length - 1; i >= 0; i--) {
                const line = lines[i].trim();
                if (line.startsWith('{') && line.includes('"text"')) {
                  try {
                    const payload = JSON.parse(line);
                    // Store compact version: text + first 2 attachments (text only)
                    const compact: any = { text: payload.text || '' };
                    if (payload.attachments?.length) {
                      compact.attachments = payload.attachments.slice(0, 2).map((a: any) => ({
                        title: a.title, text: a.text?.substring(0, 500), color: a.color
                      }));
                    }
                    return JSON.stringify(compact);
                  } catch { /* not valid JSON */ }
                }
              }
              return output.substring(0, 2000);
            })(),
          };

          // Append to history
          try {
            mkdirSync(path.join(ROOT, 'data'), { recursive: true });
            appendFileSync(CRON_HISTORY_FILE, JSON.stringify(entry) + '\n');
          } catch { /* ignore */ }

          if (error) {
            res.json({ status: 'error', error: error.message, durationMs });
            return;
          }
          res.json({ status: 'success', durationMs });
        });
        return;
      }
      const shellPath = resolveShellPath();
      execFile(shellPath, ['-lc', job.command], { timeout: timeoutMs, cwd: ROOT }, (error, stdout, stderr) => {
      const durationMs = Date.now() - startTime;
      const output = stdout || stderr || '';
      const entry: any = {
        jobName: job.name,
        startedAt: new Date(startTime).toISOString(),
        completedAt: new Date().toISOString(),
        durationMs,
        status: error ? 'error' : 'success',
        botId: job.botId || 'mei',
        error: error ? (error.message || 'Unknown error') : null,
        outputPreview: (() => {
          // Try to extract Slack payload JSON from output (may have log lines before it)
          const lines = output.trim().split('\n');
          for (let i = lines.length - 1; i >= 0; i--) {
            const line = lines[i].trim();
            if (line.startsWith('{') && line.includes('"text"')) {
              try {
                const payload = JSON.parse(line);
                // Store compact version: text + first 2 attachments (text only)
                const compact: any = { text: payload.text || '' };
                if (payload.attachments?.length) {
                  compact.attachments = payload.attachments.slice(0, 2).map((a: any) => ({
                    title: a.title, text: a.text?.substring(0, 500), color: a.color
                  }));
                }
                return JSON.stringify(compact);
              } catch { /* not valid JSON */ }
            }
          }
          return output.substring(0, 2000);
        })(),
      };

      // Append to history
      try {
        mkdirSync(path.join(ROOT, 'data'), { recursive: true });
        appendFileSync(CRON_HISTORY_FILE, JSON.stringify(entry) + '\n');
      } catch { /* ignore */ }

      if (error) {
        res.json({ status: 'error', error: error.message || 'Unknown error', durationMs });
      } else {
        res.json({ status: 'success', output, durationMs });
      }
    });
      return;
    }

    // Jobs without command: run via Claude Code SDK
    if (!job.message) {
      return res.json({ status: 'error', error: 'No command or message defined for this job' });
    }

    (async () => {
      try {
        let responseText = '';
        const abortController = new AbortController();
        const timeout = setTimeout(() => abortController.abort(), timeoutMs);

        // Load bot config for model selection
        const configs = loadConfigs();
        const botCfg = findBot(configs, job.botId || 'mei');
        const model = botCfg?.models?.cron || 'claude-sonnet-4-6';

        try {
          const { queryWithFallback } = await import('@ember/slack-bot/openai-fallback');
          for await (const message of queryWithFallback({
            prompt: job.message,
            options: {
              outputFormat: 'stream-json',
              permissionMode: 'bypassPermissions',
              cwd: ROOT,
              model,
              abortController,
            },
          })) {
            if (message.type === 'assistant' && (message as any).subtype === 'text') {
              responseText += (message as any).text || '';
            }
            if (message.type === 'result' && !responseText) {
              responseText = (message as any).result || '';
            }
          }
        } finally {
          clearTimeout(timeout);
        }

        const durationMs = Date.now() - startTime;
        const entry: any = {
          jobName: job.name,
          startedAt: new Date(startTime).toISOString(),
          completedAt: new Date().toISOString(),
          durationMs,
          status: 'success',
          botId: job.botId || 'mei',
          error: null,
          outputPreview: responseText.substring(0, 2000),
        };

        try {
          mkdirSync(path.join(ROOT, 'data'), { recursive: true });
          appendFileSync(CRON_HISTORY_FILE, JSON.stringify(entry) + '\n');
        } catch { /* ignore */ }

        res.json({ status: 'success', output: responseText, durationMs });
      } catch (e: any) {
        const durationMs = Date.now() - startTime;
        const entry: any = {
          jobName: job.name,
          startedAt: new Date(startTime).toISOString(),
          completedAt: new Date().toISOString(),
          durationMs,
          status: 'error',
          botId: job.botId || 'mei',
          error: e.message || 'Unknown error',
          outputPreview: '',
        };

        try {
          appendFileSync(CRON_HISTORY_FILE, JSON.stringify(entry) + '\n');
        } catch { /* ignore */ }

        res.json({ status: 'error', error: e.message || 'Unknown error', durationMs });
      }
    })();
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// All MCP servers
app.get('/api/mcp-servers', (_req, res) => {
  try {
    const data = readJSON(MCP_FILE);
    if (!data) return res.json([]);
    res.json(Object.keys(data.mcpServers || {}));
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// Stamp competition data
app.get('/api/stamps', (_req, res) => {
  try {
    const stampFile = path.join(DATA_DIR, 'stamp-scores.json');
    const historyFile = path.join(DATA_DIR, 'stamp-history.json');
    const raw: any = readJSON(stampFile) || {};
    const historyRaw: any = readJSON(historyFile) || { weeks: [] };

    // Build breakdown per bot from stamps array
    const buildBreakdown = (stamps: any[], botId: string): Record<string, number> => {
      const bd: Record<string, number> = {};
      for (const s of stamps) {
        if (s.botId === botId) {
          bd[s.emoji] = (bd[s.emoji] || 0) + 1;
        }
      }
      return bd;
    };

    // Transform current week: { scores: {mei: 7}, stamps: [...] } → { scores: {mei: {total, breakdown}} }
    const scores: Record<string, any> = {};
    if (raw.scores) {
      for (const [botId, total] of Object.entries(raw.scores)) {
        scores[botId] = {
          total: total as number,
          breakdown: buildBreakdown(raw.stamps || [], botId),
        };
      }
    }

    // Compute weekEnd (Sunday 23:59 JST) from weekStart
    const computeWeekEnd = (weekStart: string): string => {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + 6);
      return d.toISOString().slice(0, 10);
    };

    const currentWeek = raw.weekStart
      ? { weekStart: raw.weekStart.slice(0, 10), weekEnd: computeWeekEnd(raw.weekStart), scores }
      : undefined;

    // Transform history weeks
    const history = (historyRaw.weeks || []).map((w: any) => ({
      weekStart: (w.weekStart || '').slice(0, 10),
      weekEnd: computeWeekEnd(w.weekStart || ''),
      scores: w.scores || {},
    }));

    res.json({ currentWeek, history });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// Reward signals (intrinsic + extrinsic) from bot state files
app.get('/api/rewards', (_req, res) => {
  try {
    const botsConfig: any = readJSON(path.join(DATA_DIR, 'bot-configs.json')) || { bots: [] };
    const stampFile = path.join(DATA_DIR, 'stamp-scores.json');
    const stampHistoryFile = path.join(DATA_DIR, 'stamp-history.json');
    const stampRaw: any = readJSON(stampFile) || {};
    const stampHistory: any = readJSON(stampHistoryFile) || { weeks: [] };

    const result: Record<string, any> = {};

    for (const bot of botsConfig.bots) {
      const stateFile = path.join(DATA_DIR, `${bot.id}-state.json`);
      const state: any = readJSON(stateFile) || {};
      const history: any[] = state.history || [];

      // Aggregate intrinsic signals
      const signalAgg: Record<string, { count: number; totalValue: number; mission: number }> = {};
      const dailySignals: Record<string, Record<string, number>> = {};
      const dailyBoosts: Record<string, { sum: number; count: number }> = {};
      const rewardLogAgg: Record<string, { count: number; totalValue: number }> = {};

      for (const entry of history) {
        const date = entry.sentAt ? entry.sentAt.slice(0, 10) : null;

        // Intrinsic rewards
        const ir = entry.intrinsicReward || {};
        for (const s of ir.signals || []) {
          if (!signalAgg[s.id]) signalAgg[s.id] = { count: 0, totalValue: 0, mission: s.mission };
          signalAgg[s.id].count++;
          signalAgg[s.id].totalValue += s.value;

          if (date) {
            if (!dailySignals[date]) dailySignals[date] = {};
            dailySignals[date][s.id] = (dailySignals[date][s.id] || 0) + 1;
          }
        }

        if (date && ir.compositeBoost !== undefined) {
          if (!dailyBoosts[date]) dailyBoosts[date] = { sum: 0, count: 0 };
          dailyBoosts[date].sum += ir.compositeBoost;
          dailyBoosts[date].count++;
        }

        // Reward log (external reactions + reply signals)
        for (const rl of entry.rewardLog || []) {
          const key = rl.signal || rl.type || 'unknown';
          if (!rewardLogAgg[key]) rewardLogAgg[key] = { count: 0, totalValue: 0 };
          rewardLogAgg[key].count++;
          rewardLogAgg[key].totalValue += rl.value || 0;
        }
      }

      // External stamps (from stamp tracker)
      const externalStamps = stampRaw.scores?.[bot.id] || 0;
      const historicalStamps = (stampHistory.weeks || []).reduce((sum: number, w: any) => sum + (w.scores?.[bot.id] || 0), 0);

      // Reactions breakdown
      const reactions: Record<string, number> = {};
      for (const entry of history) {
        if (entry.reaction) {
          reactions[entry.reaction] = (reactions[entry.reaction] || 0) + 1;
        }
      }

      // Recent entries with full reward detail (last 20)
      const recentEntries = history.slice(-20).map((e: any) => ({
        sentAt: e.sentAt,
        category: e.category,
        preview: (e.preview || '').slice(0, 80),
        reaction: e.reaction,
        intrinsicSignals: (e.intrinsicReward?.signals || []).map((s: any) => ({
          id: s.id,
          mission: s.mission,
          value: s.value,
          reason: s.reason,
        })),
        compositeBoost: e.intrinsicReward?.compositeBoost ?? 0,
        rewardLog: e.rewardLog || [],
      }));

      result[bot.id] = {
        name: bot.name,
        totalMessages: history.length,
        signalAgg,
        rewardLogAgg,
        reactions,
        externalStamps: { current: externalStamps, historical: historicalStamps, total: externalStamps + historicalStamps },
        dailySignals,
        dailyBoosts,
        recentEntries,
      };
    }

    res.json(result);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// PM2 restart
app.post('/api/pm2/restart', (_req, res) => {
  try {
    execSync('pm2 restart claude-slack-bot', { timeout: 10000 });
    res.json({ message: '再起動しました' });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// CMUX BRIDGE STATUS
// ===================================================================

app.get('/api/cmux/status', (_req, res) => {
  try {
    const bridgeRunning = (() => {
      try {
        const out = execSync("pgrep -f 'cmux-bridge/bridge.sh'", { encoding: 'utf-8', timeout: 3000 }).trim();
        return out.length > 0;
      } catch { return false; }
    })();

    const bridgeDir = path.join(homedir(), '.cmux-bridge');
    const logPath = path.join(bridgeDir, 'bridge.log');
    let lastLog = '';
    if (existsSync(logPath)) {
      const lines = readFileSync(logPath, 'utf-8').trim().split('\n');
      lastLog = lines.slice(-5).join('\n');
    }

    // Check for pending requests
    const pendingRequests = (() => {
      try {
        const out = execSync(`ls ${bridgeDir}/request-* 2>/dev/null | wc -l`, { encoding: 'utf-8', timeout: 3000 });
        return parseInt(out.trim()) || 0;
      } catch { return 0; }
    })();

    res.json({ running: bridgeRunning, lastLog, pendingRequests });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/cmux/restart', (_req, res) => {
  try {
    // Kill existing bridge
    try { execSync("pkill -f 'cmux-bridge/bridge.sh'", { timeout: 3000 }); } catch {}
    // Can't start from here (outside cmux process tree). User needs to open cmux terminal.
    res.json({ message: 'ブリッジを停止した。cmuxターミナルで新しいシェルを開くと自動起動するよ。' });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// BACKWARD COMPAT: Redirects for old endpoints
// ===================================================================

// Old /api/state -> redirect to mei state
app.get('/api/state', (req, res) => {
  const statePath = getStatePath('mei');
  const state = readJSON(statePath);
  if (!state) return res.json({ categoryWeights: {}, cooldown: { until: null, consecutiveIgnores: 0, backoffMinutes: 0 }, history: [], lastCheckAt: null, stats: { totalSent: 0, positiveReactions: 0, negativeReactions: 0 } });
  res.json(state);
});

// ===================================================================
// PROACTIVE ANALYTICS
// ===================================================================

app.get('/api/proactive/stats', (req, res) => {
  try {
    const botId = (req.query.botId as string) || 'mei';
    const statePath = path.join(DATA_DIR, `${botId}-state.json`);
    const state = readJSON(statePath);
    if (!state) return res.json({ error: 'No state found' });

    const history = state.history || [];
    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString();

    const totalSent = history.length;
    const thisWeek = history.filter((h: any) => h.sentAt >= weekAgo).length;
    const todayCount = history.filter((h: any) => h.sentAt?.startsWith(today)).length;
    const withReaction = history.filter((h: any) => h.reaction !== null).length;
    const positive = history.filter((h: any) => h.reactionDelta > 0).length;
    const negative = history.filter((h: any) => h.reactionDelta < 0).length;

    // Category distribution
    const categoryDist: Record<string, number> = {};
    const interestDist: Record<string, number> = {};
    for (const h of history) {
      categoryDist[h.category] = (categoryDist[h.category] || 0) + 1;
      if (h.interestCategory) {
        interestDist[h.interestCategory] = (interestDist[h.interestCategory] || 0) + 1;
      }
    }

    // Time-of-day stats
    const hourStats: Record<number, { sent: number; reacted: number; positive: number }> = {};
    for (const h of history) {
      const hour = new Date(h.sentAt).getHours();
      if (!hourStats[hour]) hourStats[hour] = { sent: 0, reacted: 0, positive: 0 };
      hourStats[hour].sent++;
      if (h.reaction) hourStats[hour].reacted++;
      if (h.reactionDelta > 0) hourStats[hour].positive++;
    }

    // Proactive schedule — derive from cron-jobs.json
    const cronData = readJSON(CRON_FILE);
    const proactiveCron = findProactiveCronJob(cronData, botId);
    let scheduledHours: number[] = [];
    if (proactiveCron?.cron) {
      // Parse hour field from cron expression (minute hour day month weekday)
      const hourField = proactiveCron.cron.split(/\s+/)[1] || '';
      if (hourField === '*') {
        scheduledHours = Array.from({ length: 24 }, (_, i) => i);
      } else {
        scheduledHours = hourField.split(',').map(Number).filter((n: number) => !isNaN(n)).sort((a: number, b: number) => a - b);
      }
    }
    const remainingToday = scheduledHours.filter(h => h > now.getHours()).length;

    res.json({
      totalSent,
      thisWeek,
      todayCount,
      reactionRate: totalSent > 0 ? Math.round((withReaction / totalSent) * 100) : 0,
      positiveRate: withReaction > 0 ? Math.round((positive / withReaction) * 100) : 0,
      positive,
      negative,
      remainingToday,
      scheduledHours,
      categoryDist,
      interestDist,
      hourStats,
      categoryWeights: state.categoryWeights || {},
      todayMessages: state.todayMessages || [],
      lastDecisionLog: state.lastDecisionLog || null,
      scoredCandidates: state.lastScoredCandidates || [],
      learningState: state.learningState || null,
      allowNoReply: state.allowNoReply ?? true,
      lastAuthError: state.lastAuthError || null,
      conversationProfile: state.conversationProfile || 'balanced',
    });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.patch('/api/proactive/state', (req, res) => {
  try {
    const botId = (req.query.botId as string) || 'mei';
    const statePath = path.join(DATA_DIR, `${botId}-state.json`);
    const state = readJSON(statePath);
    if (!state) return res.status(404).json({ error: 'No state found' });
    if (req.body.allowNoReply !== undefined) {
      state.allowNoReply = req.body.allowNoReply;
    }
    if (req.body.conversationProfile) {
      state.conversationProfile = req.body.conversationProfile;
    }
    if (req.body.emojiEnabled !== undefined) {
      state.emojiEnabled = req.body.emojiEnabled;
    }
    writeFileSync(statePath, JSON.stringify(state, null, 2));
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// --- Thought Trace (#3 retro 2026-04-25) ---
// Surfaces inner_thought / plan / generate_score / evaluate_score recorded in
// each bot's heartbeat. Read by ThoughtTracePage (table) and EmberChat
// (Debug-mode polling).
app.get('/api/thought-trace', (req, res) => {
  try {
    const days = parseInt(req.query.days as string) || 7;
    const botFilter = (req.query.botId as string) || '';
    const sinceTs = (req.query.since as string) || '';
    const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;
    const bots = botFilter ? [botFilter] : ['mei', 'eve'];

    const entries: any[] = [];
    for (const botId of bots) {
      const hbPath = path.join(DATA_DIR, `${botId}-heartbeat.json`);
      if (!existsSync(hbPath)) continue;
      let arr: any[] = [];
      try {
        arr = JSON.parse(readFileSync(hbPath, 'utf-8'));
      } catch {
        continue;
      }
      if (!Array.isArray(arr)) continue;
      for (const e of arr) {
        if (!e?.timestamp) continue;
        const t = new Date(e.timestamp).getTime();
        if (Number.isNaN(t) || t < cutoff) continue;
        if (sinceTs && e.timestamp <= sinceTs) continue;
        entries.push({
          timestamp: e.timestamp,
          timeDisplay: e.timeDisplay,
          bot: botId,
          type: e.type,
          decision: e.decision,
          modeEstimate: e.modeEstimate,
          message: e.message,
          reason: e.reason,
          inner_thought: e.inner_thought,
          plan: e.plan,
          generate_score: e.generate_score,
          evaluate_score: e.evaluate_score,
          category: e.category,
          emoji: e.emoji,
          replyPreview: e.replyPreview,
        });
      }
    }
    entries.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
    res.json({ entries });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/proactive/history', (req, res) => {
  try {
    const botId = (req.query.botId as string) || 'mei';
    const limit = parseInt(req.query.limit as string) || 20;
    const statePath = path.join(DATA_DIR, `${botId}-state.json`);
    const state = readJSON(statePath);
    if (!state) return res.json([]);

    const history = (state.history || [])
      .slice(-limit)
      .reverse(); // newest first

    res.json(history);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// --- Learning State Management ---

app.put('/api/proactive/learning-state', (req, res) => {
  try {
    const botId = (req.query.botId as string) || 'mei';
    const statePath = path.join(DATA_DIR, `${botId}-state.json`);
    const state = readJSON(statePath);
    if (!state) return res.status(404).json({ error: 'State not found' });

    const { priors } = req.body;
    if (!priors || typeof priors !== 'object') {
      return res.status(400).json({ error: 'priors object required' });
    }

    // Validate and update each axis
    for (const [axis, prior] of Object.entries(priors) as [string, any][]) {
      if (typeof prior.alpha !== 'number' || typeof prior.beta !== 'number') continue;
      if (prior.alpha < 0.1 || prior.beta < 0.1) continue; // safety floor
      if (!state.learningState?.priors[axis]) continue;
      state.learningState.priors[axis] = {
        alpha: Math.round(prior.alpha * 10) / 10,
        beta: Math.round(prior.beta * 10) / 10,
      };
    }
    state.learningState.lastUpdated = new Date().toISOString();

    writeJSON(statePath, state);
    res.json({ ok: true, learningState: state.learningState });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/proactive/learning-state/reset', (req, res) => {
  try {
    const botId = (req.query.botId as string) || 'mei';
    const statePath = path.join(DATA_DIR, `${botId}-state.json`);
    const state = readJSON(statePath);
    if (!state) return res.status(404).json({ error: 'State not found' });

    const { axis } = req.body; // optional: reset single axis

    const DEFAULT_PRIORS: Record<string, { alpha: number; beta: number }> = {
      timeliness:    { alpha: 5, beta: 5 },
      novelty:       { alpha: 4, beta: 6 },
      continuity:    { alpha: 4, beta: 6 },
      emotional_fit: { alpha: 3, beta: 7 },
      affinity:      { alpha: 2, beta: 8 },
      surprise:      { alpha: 2, beta: 8 },
    };

    if (axis && DEFAULT_PRIORS[axis]) {
      // Reset single axis
      state.learningState.priors[axis] = { ...DEFAULT_PRIORS[axis] };
    } else {
      // Full reset
      state.learningState = {
        priors: { ...DEFAULT_PRIORS },
        totalSelections: 0,
        categorySelections: {},
        lastUpdated: new Date().toISOString(),
        version: (state.learningState?.version || 0) + 1,
      };
    }
    state.learningState.lastUpdated = new Date().toISOString();

    writeJSON(statePath, state);
    res.json({ ok: true, learningState: state.learningState });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.patch('/api/proactive/intrinsic-config', (req, res) => {
  try {
    const botId = (req.query.botId as string) || 'mei';
    const statePath = getStatePath(botId);
    const state = readJSON(statePath);
    if (!state) return res.status(404).json({ error: 'State not found' });

    const { lambda, enabledSignals } = req.body;
    if (!state.intrinsicConfig) {
      state.intrinsicConfig = { lambda: 0.3, enabledSignals: ['M1-a','M2-a','M2-b','M3-a','M3-b','M4-a','M4-b','M5-a','M5-b','R1','R2','R3','R4','R5'] };
    }
    if (typeof lambda === 'number' && lambda >= 0 && lambda <= 1) {
      state.intrinsicConfig.lambda = Math.round(lambda * 100) / 100;
    }
    if (Array.isArray(enabledSignals)) {
      state.intrinsicConfig.enabledSignals = enabledSignals;
    }
    writeJSON(statePath, state);
    res.json({ ok: true, intrinsicConfig: state.intrinsicConfig });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/proactive/interests', (_req, res) => {
  try {
    const cachePath = path.join(DATA_DIR, 'interest-cache.json');
    const cache = readJSON(cachePath);
    if (!cache) return res.json({ lastUpdated: null, categories: {}, topItems: [] });
    res.json(cache);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// GLOBAL CONFIG
// ===================================================================

app.get('/api/global', (_req, res) => {
  try {
    const configs = readJSON(BOT_CONFIGS_FILE) || { bots: [], global: {} };
    res.json(configs.global || {});
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/global', (req, res) => {
  try {
    const configs = readJSON(BOT_CONFIGS_FILE) || { bots: [], global: {} };
    configs.global = { ...(configs.global || {}), ...req.body };
    writeJSON(BOT_CONFIGS_FILE, configs);
    res.json({ ok: true, global: configs.global });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// LOCAL MODELS
// ===================================================================

const DEFAULT_LOCAL_MODELS = {
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

async function checkServerAlive(url: string, timeoutMs = 2000): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timer);
    return res.ok;
  } catch {
    return false;
  }
}

app.get('/api/local-models', async (_req, res) => {
  try {
    const configs = loadConfigs();
    const config = { ...DEFAULT_LOCAL_MODELS, ...((configs.global || {}).localModels || {}) };
    // Merge nested objects
    config.mlx = { ...DEFAULT_LOCAL_MODELS.mlx, ...((configs.global || {}).localModels || {}).mlx };
    config.ollama = { ...DEFAULT_LOCAL_MODELS.ollama, ...((configs.global || {}).localModels || {}).ollama };

    const mlxBaseUrl = config.mlx.url.replace(/\/v1\/chat\/completions$/, '');
    const [mlxAlive, ollamaAlive] = await Promise.all([
      checkServerAlive(`${mlxBaseUrl}/v1/models`),
      checkServerAlive(`${config.ollama.url}/`),
    ]);

    res.json({
      config,
      status: { mlx: mlxAlive, ollama: ollamaAlive },
    });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/local-models', (req, res) => {
  try {
    const configs = loadConfigs();
    if (!configs.global) configs.global = {};
    const existing = configs.global.localModels || {};
    // Deep merge mlx and ollama
    configs.global.localModels = {
      mlx: { ...DEFAULT_LOCAL_MODELS.mlx, ...existing.mlx, ...(req.body.mlx || {}) },
      ollama: { ...DEFAULT_LOCAL_MODELS.ollama, ...existing.ollama, ...(req.body.ollama || {}) },
      jobs: { ...(existing.jobs || {}), ...(req.body.jobs || {}) },
    };
    saveConfigs(configs);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// Job definitions: jobId → default settings
const JOB_DEFS: Record<string, { name: string; defaultBackend: 'mlx' | 'ollama'; description: string; usedBy: string }> = {
  'deep-reward-analysis': { name: 'Deep Reward Analysis', defaultBackend: 'mlx', description: 'ユーザー返信のミッション達成分析', usedBy: 'intrinsic-rewards.ts' },
  'embedding':            { name: 'Embedding',            defaultBackend: 'ollama', description: 'プロアクティブ状態の意味検索', usedBy: 'proactive-state.ts' },
};

function resolveJobModel(jobId: string, backend: 'mlx' | 'ollama', jobs: any, mlxConfig: any, ollamaConfig: any): string {
  const savedModel = jobs?.[jobId]?.model;
  if (savedModel) return savedModel;
  return backend === 'mlx' ? mlxConfig.model : ollamaConfig.embedModel;
}

app.get('/api/local-models/jobs', (_req, res) => {
  try {
    const configs = loadConfigs();
    const lm = (configs.global || {}).localModels || {};
    const mlxConfig = { ...DEFAULT_LOCAL_MODELS.mlx, ...lm.mlx };
    const ollamaConfig = { ...DEFAULT_LOCAL_MODELS.ollama, ...lm.ollama };
    const jobs = lm.jobs || {};

    const result = Object.entries(JOB_DEFS).map(([jobId, def]) => {
      const backend = jobs[jobId]?.backend || def.defaultBackend;
      return {
        id: jobId,
        name: def.name,
        type: backend,
        description: def.description,
        usedBy: def.usedBy,
        model: resolveJobModel(jobId, backend, jobs, mlxConfig, ollamaConfig),
      };
    });

    res.json(result);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.patch('/api/local-models/jobs/:jobId', (req, res) => {
  try {
    const { jobId } = req.params;
    if (!JOB_DEFS[jobId]) return res.status(404).json({ error: `Unknown job: ${jobId}` });

    const { backend, model } = req.body;
    if (backend && !['mlx', 'ollama'].includes(backend)) {
      return res.status(400).json({ error: 'backend must be mlx or ollama' });
    }

    const configs = loadConfigs();
    if (!configs.global) configs.global = {};
    if (!configs.global.localModels) configs.global.localModels = {} as any;
    if (!configs.global.localModels!.jobs) configs.global.localModels!.jobs = {};

    const existing = configs.global.localModels!.jobs![jobId] || {};
    const backendChanged = backend && existing.backend && backend !== existing.backend;
    configs.global.localModels!.jobs![jobId] = {
      ...existing,
      ...(backend ? { backend } : {}),
      // backend 変更時は model をリセット（デフォルトに戻す）
      ...(backendChanged && !model ? { model: undefined } : {}),
      ...(model ? { model } : {}),
    };

    saveConfigs(configs);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// --- Ollama Available Models ---
app.get('/api/local-models/ollama/models', async (_req, res) => {
  try {
    const configs = loadConfigs();
    const ollamaUrl = ((configs.global || {}).localModels || {}).ollama?.url || DEFAULT_LOCAL_MODELS.ollama.url;
    const resp = await fetch(`${ollamaUrl}/api/tags`);
    if (!resp.ok) return res.json([]);
    const data = await resp.json() as { models?: Array<{ name: string; size: number; details?: { parameter_size?: string; quantization_level?: string } }> };
    const models = (data.models || []).map(m => ({
      name: m.name,
      size: `${(m.size / (1024 ** 3)).toFixed(1)}GB`,
      paramSize: m.details?.parameter_size || '',
      quant: m.details?.quantization_level || '',
    }));
    res.json(models);
  } catch {
    res.json([]);
  }
});

// --- Server Management ---

const HOME = homedir();
const MLX_PLIST = path.join(HOME, 'Library/LaunchAgents/local.mlx.serve.plist');
const OLLAMA_SERVE_PLIST = path.join(HOME, 'Library/LaunchAgents/local.ollama.serve2.plist');
const WHISPER_PLIST = path.join(HOME, 'Library/LaunchAgents/local.whisper.serve.plist');
const DASHBOARD_PLIST = path.join(HOME, 'Library/LaunchAgents/local.dashboard.serve.plist');
const GPTSOVITS_PLIST = path.join(HOME, 'Library/LaunchAgents/local.gptsovits.serve.plist');
const IRODORI_PLIST = path.join(HOME, 'Library/LaunchAgents/local.irodori.serve.plist');

function isLaunchdLoaded(label: string): boolean {
  try {
    const out = execSync('launchctl list', { encoding: 'utf-8' });
    return out.includes(label);
  } catch {
    return false;
  }
}

function findProcessPid(pattern: string): number | null {
  const pids = findAllProcessPids(pattern);
  return pids.length > 0 ? pids[0] : null;
}

function findAllProcessPids(pattern: string): number[] {
  try {
    const out = execSync('ps aux', { encoding: 'utf-8' });
    const pids: number[] = [];
    for (const line of out.split('\n')) {
      if (line.includes(pattern) && !line.includes('grep')) {
        const parts = line.trim().split(/\s+/);
        const pid = parseInt(parts[1], 10);
        if (!isNaN(pid)) pids.push(pid);
      }
    }
    return pids;
  } catch {
    return [];
  }
}

async function fetchJson(url: string, timeoutMs = 3000): Promise<any> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timer);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    clearTimeout(timer);
    return null;
  }
}

app.get('/api/local-models/server-status', async (_req, res) => {
  try {
    // MLX status
    const mlxPid = findProcessPid('mlx_lm server');
    const mlxRunning = mlxPid !== null;
    const mlxAutoStart = isLaunchdLoaded('local.mlx.serve');
    let mlxLoadedModels: string[] = [];
    if (mlxRunning) {
      const data = await fetchJson('http://localhost:8080/v1/models');
      if (data?.data) {
        mlxLoadedModels = data.data.map((m: any) => m.id);
      }
    }

    // Ollama status
    const ollamaPid = findProcessPid('ollama serve');
    const ollamaRunning = ollamaPid !== null;
    const ollamaAutoStart = isLaunchdLoaded('local.ollama.serve2');
    const ollamaRunnerPids = findAllProcessPids('ollama runner');
    let ollamaLoadedModels: { name: string; size: string }[] = [];
    if (ollamaRunning) {
      const data = await fetchJson('http://localhost:11434/api/ps');
      if (data?.models) {
        ollamaLoadedModels = data.models.map((m: any) => ({
          name: m.name || m.model || 'unknown',
          size: m.size ? `${(m.size / 1e9).toFixed(1)} GB` : 'unknown',
        }));
      }
    }

    // Whisper (voice_chat) status — HTTP check first, lsof as fallback for PID
    const whisperAutoStart = isLaunchdLoaded('local.whisper.serve');
    const whisperAlive = await checkServerAlive('http://localhost:8767/');
    let whisperPid: number | null = null;
    if (whisperAlive) {
      try {
        const lsof = execSync('lsof -ti :8767', { encoding: 'utf-8' }).trim();
        if (lsof) whisperPid = parseInt(lsof.split('\n')[0], 10) || null;
      } catch { /* PID lookup failed, but server is alive */ }
    }
    const whisperRunning = whisperAlive;
    const whisperModel = whisperAlive ? 'large-v3 (int8)' : '';

    // VOICEVOX (Docker) status
    let voicevoxRunning = false;
    let voicevoxAutoStart = false;
    let voicevoxContainerId: string | null = null;
    try {
      const out = execSync('/usr/local/bin/docker inspect voicevox --format "{{.State.Running}}|{{.HostConfig.RestartPolicy.Name}}|{{.Id}}"', { encoding: 'utf-8' }).trim();
      const [running, restartPolicy, id] = out.split('|');
      voicevoxRunning = running === 'true';
      voicevoxAutoStart = restartPolicy === 'always' || restartPolicy === 'unless-stopped';
      voicevoxContainerId = id ? id.substring(0, 12) : null;
    } catch {
      // container not found or docker not available
    }

    // GPT-SoVITS status
    const gptsovitsAutoStart = isLaunchdLoaded('local.gptsovits.serve');
    // GPT-SoVITS returns 404 on /, so check if connection succeeds (any HTTP response = alive)
    let gptsovitsAlive = false;
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 2000);
      await fetch('http://localhost:9880/', { signal: ctrl.signal });
      clearTimeout(t);
      gptsovitsAlive = true;  // any response (including 404) means server is running
    } catch {}
    let gptsovitsPid: number | null = null;
    if (gptsovitsAlive) {
      try {
        const lsof = execSync('lsof -ti :9880', { encoding: 'utf-8' }).trim();
        if (lsof) gptsovitsPid = parseInt(lsof.split('\n')[0], 10) || null;
      } catch {}
    }

    // Irodori TTS status (port 7860, launchd: local.irodori.serve)
    let irodoriAlive = false;
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 2000);
      await fetch('http://localhost:7860/health', { signal: ctrl.signal });
      clearTimeout(t);
      irodoriAlive = true;
    } catch {}
    let irodoriPid: number | null = null;
    if (irodoriAlive) {
      try {
        const lsof = execSync('lsof -ti :7860', { encoding: 'utf-8' }).trim();
        const pids = lsof.split('\n').map(p => parseInt(p, 10)).filter(p => p && p !== process.pid);
        if (pids.length) irodoriPid = pids[0];
      } catch {}
    }
    const irodoriAutoStart = isLaunchdLoaded('local.irodori.serve');

    // Dashboard API status (self)
    const dashboardAutoStart = isLaunchdLoaded('local.dashboard.serve');
    const dashboardPid = process.pid;

    res.json({
      mlx: { running: mlxRunning, autoStart: mlxAutoStart, loadedModels: mlxLoadedModels, pid: mlxPid },
      ollama: { running: ollamaRunning, autoStart: ollamaAutoStart, loadedModels: ollamaLoadedModels, pid: ollamaPid, runnerPids: ollamaRunnerPids },
      whisper: { running: whisperRunning, autoStart: whisperAutoStart, model: whisperModel, pid: whisperPid },
      voicevox: { running: voicevoxRunning, autoStart: voicevoxAutoStart, containerId: voicevoxContainerId },
      gptsovits: { running: gptsovitsAlive, autoStart: gptsovitsAutoStart, pid: gptsovitsPid },
      irodori: { running: irodoriAlive, autoStart: irodoriAutoStart, pid: irodoriPid },
      dashboard: { running: true, autoStart: dashboardAutoStart, pid: dashboardPid },
    });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/local-models/mlx/start', (_req, res) => {
  try {
    execSync(`launchctl load "${MLX_PLIST}"`, { encoding: 'utf-8' });
    res.json({ ok: true, message: 'MLX server started' });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/mlx/stop', (_req, res) => {
  try {
    execSync(`launchctl unload "${MLX_PLIST}"`, { encoding: 'utf-8' });
    res.json({ ok: true, message: 'MLX server stopped' });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/mlx/auto-start', (req, res) => {
  try {
    const { enabled } = req.body;
    if (enabled) {
      execSync(`launchctl load "${MLX_PLIST}"`, { encoding: 'utf-8' });
    } else {
      execSync(`launchctl unload "${MLX_PLIST}"`, { encoding: 'utf-8' });
    }
    res.json({ ok: true, message: `MLX auto-start ${enabled ? 'enabled' : 'disabled'}` });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/ollama/start', (_req, res) => {
  try {
    // Try launchd first, fallback to direct process start
    try {
      execSync(`launchctl load "${OLLAMA_SERVE_PLIST}"`, { encoding: 'utf-8' });
    } catch {
      // launchd failed, start directly with env vars
      spawn('/usr/local/bin/ollama', ['serve'], {
        detached: true,
        stdio: 'ignore',
        env: { ...process.env, OLLAMA_HOST: '0.0.0.0:11434', OLLAMA_KEEP_ALIVE: '-1', OLLAMA_NUM_PARALLEL: '1', OLLAMA_MAX_LOADED_MODELS: '3' },
      }).unref();
    }
    res.json({ ok: true, message: 'Ollama started' });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/ollama/stop', (_req, res) => {
  try {
    // Try launchd unload first, then kill processes
    try { execSync(`launchctl unload "${OLLAMA_SERVE_PLIST}"`, { encoding: 'utf-8' }); } catch {}
    execSync("pkill -f 'ollama serve' || true; pkill -f 'Ollama' || true", { encoding: 'utf-8' });
    res.json({ ok: true, message: 'Ollama stopped' });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/ollama/auto-start', (req, res) => {
  try {
    const { enabled } = req.body;
    if (enabled) {
      // Try launchctl load, fallback to bootout+bootstrap
      try {
        execSync(`launchctl load "${OLLAMA_SERVE_PLIST}"`, { encoding: 'utf-8' });
      } catch {
        try {
          execSync(`launchctl bootout gui/$(id -u)/local.ollama.serve2 2>/dev/null; launchctl bootstrap gui/$(id -u) "${OLLAMA_SERVE_PLIST}"`, { encoding: 'utf-8', shell: '/bin/zsh' });
        } catch {}
      }
    } else {
      try {
        execSync(`launchctl unload "${OLLAMA_SERVE_PLIST}"`, { encoding: 'utf-8' });
      } catch {
        try {
          execSync(`launchctl bootout gui/$(id -u)/local.ollama.serve2`, { encoding: 'utf-8', shell: '/bin/zsh' });
        } catch {}
      }
    }
    res.json({ ok: true, message: `Ollama auto-start ${enabled ? 'enabled' : 'disabled'}` });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

// --- Whisper (voice_chat) ---
const VOICE_CHAT_DIR = path.join(HOME, 'workspace/ember/packages/voice-chat');

app.post('/api/local-models/whisper/start', (_req, res) => {
  try {
    // Try launchd first, fallback to direct spawn
    try {
      execSync(`launchctl load "${WHISPER_PLIST}"`, { encoding: 'utf-8' });
    } catch {
      spawn(path.join(VOICE_CHAT_DIR, '.venv/bin/python'), ['app.py'], {
        cwd: VOICE_CHAT_DIR,
        detached: true,
        stdio: 'ignore',
        env: { ...process.env },
      }).unref();
    }
    res.json({ ok: true, message: 'Whisper server starting' });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/whisper/stop', (_req, res) => {
  try {
    try { execSync(`launchctl unload "${WHISPER_PLIST}"`, { encoding: 'utf-8' }); } catch {}
    let pid: number | null = null;
    try {
      const lsof = execSync('lsof -ti :8767', { encoding: 'utf-8' }).trim();
      if (lsof) pid = parseInt(lsof.split('\n')[0], 10) || null;
    } catch {}
    if (pid) {
      process.kill(pid, 'SIGTERM');
    }
    res.json({ ok: true, message: 'Whisper server stopped' });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/whisper/auto-start', (req, res) => {
  try {
    const { enabled } = req.body;
    if (enabled) {
      execSync(`launchctl load "${WHISPER_PLIST}"`, { encoding: 'utf-8' });
    } else {
      execSync(`launchctl unload "${WHISPER_PLIST}"`, { encoding: 'utf-8' });
    }
    res.json({ ok: true, message: `Whisper auto-start ${enabled ? 'enabled' : 'disabled'}` });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

// --- Dashboard (self) ---
app.post('/api/local-models/dashboard/auto-start', (req, res) => {
  try {
    const { enabled } = req.body;
    if (enabled) {
      execSync(`launchctl load "${DASHBOARD_PLIST}"`, { encoding: 'utf-8' });
    } else {
      execSync(`launchctl unload "${DASHBOARD_PLIST}"`, { encoding: 'utf-8' });
    }
    res.json({ ok: true, message: `Dashboard auto-start ${enabled ? 'enabled' : 'disabled'}` });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

// --- VOICEVOX (Docker) ---
app.post('/api/local-models/voicevox/start', (_req, res) => {
  try {
    execSync('/usr/local/bin/docker start voicevox', { encoding: 'utf-8' });
    res.json({ ok: true, message: 'VOICEVOX started' });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/voicevox/stop', (_req, res) => {
  try {
    execSync('/usr/local/bin/docker stop voicevox', { encoding: 'utf-8' });
    res.json({ ok: true, message: 'VOICEVOX stopped' });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/voicevox/auto-start', (req, res) => {
  try {
    const { enabled } = req.body;
    const policy = enabled ? 'unless-stopped' : 'no';
    execSync(`/usr/local/bin/docker update --restart ${policy} voicevox`, { encoding: 'utf-8' });
    res.json({ ok: true, message: `VOICEVOX auto-start ${enabled ? 'enabled' : 'disabled'}` });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

// --- GPT-SoVITS ---
app.post('/api/local-models/gptsovits/start', (_req, res) => {
  try {
    execSync(`launchctl load "${GPTSOVITS_PLIST}"`, { encoding: 'utf-8' });
    res.json({ ok: true, message: 'GPT-SoVITS started' });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/gptsovits/stop', (_req, res) => {
  try {
    try { execSync(`launchctl unload "${GPTSOVITS_PLIST}"`, { encoding: 'utf-8' }); } catch {}
    let pid: number | null = null;
    try {
      const lsof = execSync('lsof -ti :9880', { encoding: 'utf-8' }).trim();
      if (lsof) pid = parseInt(lsof.split('\n')[0], 10) || null;
    } catch {}
    if (pid) process.kill(pid, 'SIGTERM');
    res.json({ ok: true, message: 'GPT-SoVITS stopped' });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/gptsovits/auto-start', (req, res) => {
  try {
    const { enabled } = req.body;
    if (enabled) {
      execSync(`launchctl load "${GPTSOVITS_PLIST}"`, { encoding: 'utf-8' });
    } else {
      execSync(`launchctl unload "${GPTSOVITS_PLIST}"`, { encoding: 'utf-8' });
    }
    res.json({ ok: true, message: `GPT-SoVITS auto-start ${enabled ? 'enabled' : 'disabled'}` });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

// --- Irodori TTS (launchd: local.irodori.serve) ---
app.post('/api/local-models/irodori/start', (_req, res) => {
  try {
    execSync(`launchctl load "${IRODORI_PLIST}"`, { encoding: 'utf-8' });
    res.json({ ok: true, message: 'Irodori TTS started' });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/irodori/stop', (_req, res) => {
  try {
    try { execSync(`launchctl unload "${IRODORI_PLIST}"`, { encoding: 'utf-8' }); } catch {}
    let pid: number | null = null;
    try {
      const lsof = execSync('lsof -ti :7860', { encoding: 'utf-8' }).trim();
      if (lsof) pid = parseInt(lsof.split('\n')[0], 10) || null;
    } catch {}
    if (pid) process.kill(pid, 'SIGTERM');
    res.json({ ok: true, message: 'Irodori TTS stopped' });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/irodori/auto-start', (req, res) => {
  try {
    const { enabled } = req.body;
    if (enabled) {
      execSync(`launchctl load "${IRODORI_PLIST}"`, { encoding: 'utf-8' });
    } else {
      execSync(`launchctl unload "${IRODORI_PLIST}"`, { encoding: 'utf-8' });
    }
    res.json({ ok: true, message: `Irodori TTS auto-start ${enabled ? 'enabled' : 'disabled'}` });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/ollama/load', async (req, res) => {
  try {
    const { model } = req.body;
    if (!model) return res.status(400).json({ ok: false, message: 'model is required' });
    const response = await fetch('http://localhost:11434/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: 'hi' }],
        stream: false,
        options: { num_predict: 1 },
        keep_alive: -1,
      }),
    });
    if (!response.ok) {
      const text = await response.text();
      return res.status(500).json({ ok: false, message: `Ollama error: ${text}` });
    }
    res.json({ ok: true, message: `Model ${model} loaded` });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

app.post('/api/local-models/ollama/unload', async (req, res) => {
  try {
    const { model } = req.body;
    if (!model) return res.status(400).json({ ok: false, message: 'model is required' });
    const response = await fetch('http://localhost:11434/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: 'hi' }],
        stream: false,
        options: { num_predict: 1 },
        keep_alive: 0,
      }),
    });
    if (!response.ok) {
      const text = await response.text();
      return res.status(500).json({ ok: false, message: `Ollama error: ${text}` });
    }
    res.json({ ok: true, message: `Model ${model} unloaded` });
  } catch (e: any) {
    res.status(500).json({ ok: false, message: e.message });
  }
});

// ===================================================================
// PROFILE API
// ===================================================================

const PROFILE_FILE = path.join(ROOT, 'data', 'user-profile.json');

// Layers and their valid fields
const PROFILE_SCHEMA: Record<string, string[]> = {
  identity: ['coreValues', 'nonNegotiables', 'aversions', 'cognitiveStyle', 'problemSolvingPattern', 'interpersonalStyle', 'energySource', 'drainFactors', 'careerTurningPoints', 'successPatterns', 'failureLessons', 'expertiseMap'],
  vision: ['futureState', 'aspirationText', 'antiVision', 'roleModels', 'careerGoal', 'personalGoal', 'relationshipGoal', 'maturity'],
  strategy: ['gapAnalysis', 'strategicOptions', 'constraints'],
  execution: ['activeProjects', 'habits', 'learningInputs', 'decisionLog', 'currentMilestones'],
  state: ['physicalEnergy', 'mentalEnergy', 'motivation', 'stressLevel', 'currentMode', 'topConcern', 'recentSuccess', 'recentSetback'],
};

function computeCompletionRate(fields: Record<string, any>): number {
  const entries = Object.values(fields);
  if (entries.length === 0) return 0;
  const filled = entries.filter((f: any) => {
    if (f && typeof f === 'object' && 'value' in f) {
      return f.value !== null && f.value !== '' && !(Array.isArray(f.value) && f.value.length === 0);
    }
    return false;
  }).length;
  return Math.round((filled / entries.length) * 100) / 100;
}

app.get('/api/profile', (_req, res) => {
  try {
    const data = readJSON(PROFILE_FILE);
    if (!data) return res.status(404).json({ error: 'user-profile.json not found' });
    // Recompute completion rates
    for (const [layerName, layerData] of Object.entries(data.layers || {})) {
      (layerData as any).completionRate = computeCompletionRate((layerData as any).fields || {});
    }
    res.json(data);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/profile/completions', (_req, res) => {
  try {
    const data = readJSON(PROFILE_FILE);
    if (!data) return res.status(404).json({ error: 'user-profile.json not found' });
    const completions: Record<string, number> = {};
    for (const [layerName, layerData] of Object.entries(data.layers || {})) {
      completions[layerName] = computeCompletionRate((layerData as any).fields || {});
    }
    res.json(completions);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/profile/layers/:layer/fields/:field', (req, res) => {
  try {
    const { layer, field } = req.params;
    if (!PROFILE_SCHEMA[layer]) return res.status(400).json({ error: `Invalid layer: ${layer}` });
    if (!PROFILE_SCHEMA[layer].includes(field)) return res.status(404).json({ error: `Field ${field} not found in layer ${layer}` });
    const data = readJSON(PROFILE_FILE);
    if (!data) return res.status(404).json({ error: 'user-profile.json not found' });
    const layerData = data.layers?.[layer];
    if (!layerData?.fields) return res.status(500).json({ error: 'Invalid profile structure' });
    layerData.fields[field] = {
      ...layerData.fields[field],
      ...req.body,
      collectedAt: req.body.collectedAt || new Date().toISOString().split('T')[0],
    };
    data.lastUpdated = new Date().toISOString();
    layerData.completionRate = computeCompletionRate(layerData.fields);
    writeJSON(PROFILE_FILE, data);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/profile/config', (req, res) => {
  try {
    const data = readJSON(PROFILE_FILE);
    if (!data) return res.status(404).json({ error: 'user-profile.json not found' });
    data.collectionConfig = { ...data.collectionConfig, ...req.body };
    data.lastUpdated = new Date().toISOString();
    writeJSON(PROFILE_FILE, data);
    res.json({ ok: true });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// EVENT SOURCES
// ===================================================================

const DEFAULT_EVENT_SOURCE_CONFIG = {
  gmail: { enabled: false, intervalMinutes: 5, query: 'is:unread is:important' },
  calendar: { enabled: false, intervalMinutes: 15, alertBeforeMinutes: 10 },
  rss: { enabled: false, intervalMinutes: 30 },
  github: { enabled: false, webhookSecret: '' },
};

const DEFAULT_INTENTIONAL_PAUSE_CONFIG = {
  enabled: false,
  premiseTexts: { light: null, medium: 'ちょっと思ったんだけど...', heavy: 'ねえ、少し大事な話なんだけど...' },
  waitSeconds: { light: 1, medium: 3, heavy: 5 },
};

const VALID_EVENT_SOURCES = ['gmail', 'calendar', 'rss', 'github'];

app.get('/api/bots/:botId/event-sources', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    res.json(bot.eventSources || DEFAULT_EVENT_SOURCE_CONFIG);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/bots/:botId/event-sources/:source', (req, res) => {
  try {
    const { botId, source } = req.params;
    if (!VALID_EVENT_SOURCES.includes(source)) {
      return res.status(400).json({ error: `Invalid source: ${source}. Must be one of ${VALID_EVENT_SOURCES.join(', ')}` });
    }
    const configs = loadConfigs();
    const bot = findBot(configs, botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    if (!bot.eventSources) bot.eventSources = { ...DEFAULT_EVENT_SOURCE_CONFIG };
    bot.eventSources[source] = { ...bot.eventSources[source], ...req.body };
    saveConfigs(configs);
    res.json(bot.eventSources);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// CALENDAR LIST (for exclude UI)
// ===================================================================

app.get('/api/calendars', async (_req, res) => {
  try {
    // Read Google OAuth credentials from ~/.gmail-mcp/
    const gmailMcpDir = path.join(homedir(), '.gmail-mcp');
    const credsFile = path.join(gmailMcpDir, 'credentials.json');
    const oauthFile = path.join(gmailMcpDir, 'gcp-oauth.keys.json');
    if (!existsSync(credsFile) || !existsSync(oauthFile)) {
      return res.status(500).json({ error: 'Google OAuth credentials not found in ~/.gmail-mcp/' });
    }
    const creds = JSON.parse(readFileSync(credsFile, 'utf-8'));
    const oauthKeys = JSON.parse(readFileSync(oauthFile, 'utf-8'));
    const oauthInfo = oauthKeys.installed || oauthKeys.web || {};
    const clientId = oauthInfo.client_id;
    const clientSecret = oauthInfo.client_secret;
    const refreshToken = creds.refresh_token;
    if (!clientId || !clientSecret || !refreshToken) {
      return res.status(500).json({ error: 'Google OAuth credentials incomplete' });
    }
    const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        refresh_token: refreshToken,
        grant_type: 'refresh_token',
      }),
    });
    const tokenData = await tokenRes.json() as any;
    if (!tokenData.access_token) {
      return res.status(500).json({ error: 'Failed to get access token' });
    }
    const calRes = await fetch('https://www.googleapis.com/calendar/v3/users/me/calendarList', {
      headers: { Authorization: `Bearer ${tokenData.access_token}` },
    });
    const calData = await calRes.json() as any;
    const items = (calData.items ?? []).map((c: any) => ({
      id: c.id,
      summary: c.summary,
      primary: c.primary ?? false,
    }));
    res.json(items);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// INTENTIONAL PAUSE
// ===================================================================

app.get('/api/bots/:botId/intentional-pause', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    res.json(bot.intentionalPause || DEFAULT_INTENTIONAL_PAUSE_CONFIG);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/bots/:botId/intentional-pause', (req, res) => {
  try {
    const configs = loadConfigs();
    const bot = findBot(configs, req.params.botId);
    if (!bot) return res.status(404).json({ error: 'Bot not found' });
    bot.intentionalPause = { ...(bot.intentionalPause || DEFAULT_INTENTIONAL_PAUSE_CONFIG), ...req.body };
    saveConfigs(configs);
    res.json(bot.intentionalPause);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// EVENT LOG
// ===================================================================

app.get('/api/event-log', (_req, res) => {
  try {
    const cronHistoryPath = path.join(DATA_DIR, 'cron-history.jsonl');
    if (!existsSync(cronHistoryPath)) return res.json([]);
    const lines = readFileSync(cronHistoryPath, 'utf-8').trim().split('\n').filter(Boolean);
    const entries = lines.map((line) => {
      try { return JSON.parse(line); } catch { return null; }
    }).filter(Boolean);
    res.json(entries.slice(-100).reverse());
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ===================================================================
// STATIC FILES (built dashboard)
// ===================================================================

// ===================================================================
// WHISPER PROXY — forward /whisper/* and /ws to Whisper Server (8767)
// ===================================================================
const WHISPER_TARGET = 'http://localhost:8767';

// HTTP proxy: /whisper/* → localhost:8767/*
app.use('/whisper', createProxyMiddleware({
  target: WHISPER_TARGET,
  changeOrigin: true,
  pathRewrite: { '^/whisper': '' },
}));

// --- Implicit Memory ---
const IMPLICIT_MEMORY_FILE = path.join(DATA_DIR, 'implicit-memory.json');
const MEMORY_LAYERS = ['facts', 'preferences', 'patterns', 'values', 'expressions'] as const;

function readImplicitMemory(botId: string): any {
  const data = readJSON(IMPLICIT_MEMORY_FILE) || {};
  const bot = data[botId] || { facts: [], preferences: [], patterns: [], values: [], expressions: [], corrections: [] };
  return bot;
}

function writeImplicitMemory(botId: string, memory: any): void {
  const data = readJSON(IMPLICIT_MEMORY_FILE) || {};
  data[botId] = memory;
  writeJSON(IMPLICIT_MEMORY_FILE, data);
}

app.get('/api/bots/:botId/implicit-memory', (req, res) => {
  res.json(readImplicitMemory(req.params.botId));
});

app.get('/api/bots/:botId/implicit-memory/stats', (req, res) => {
  const mem = readImplicitMemory(req.params.botId);
  const stats: any = {};
  let total = 0;
  for (const layer of MEMORY_LAYERS) {
    stats[layer] = (mem[layer] || []).length;
    total += stats[layer];
  }
  stats.corrections = (mem.corrections || []).length;
  stats.total = total;
  res.json(stats);
});

app.get('/api/bots/:botId/implicit-memory/:layer', (req, res) => {
  const mem = readImplicitMemory(req.params.botId);
  const layer = req.params.layer;
  res.json(mem[layer] || []);
});

app.delete('/api/bots/:botId/implicit-memory/:layer/:id', (req, res) => {
  const mem = readImplicitMemory(req.params.botId);
  const layer = req.params.layer;
  if (Array.isArray(mem[layer])) {
    mem[layer] = mem[layer].filter((e: any) => e.id !== req.params.id);
  }
  writeImplicitMemory(req.params.botId, mem);
  res.json({ ok: true });
});

// WebSocket proxy: /ws → localhost:8767/ws
const wsProxy = createProxyMiddleware({
  target: WHISPER_TARGET,
  changeOrigin: true,
  ws: true,
});
app.use('/ws', wsProxy);

const DIST_DIR = path.join(__dirname, '..', 'dist');
if (existsSync(DIST_DIR)) {
  app.use(express.static(DIST_DIR));
  // SPA fallback: serve index.html for all non-API routes
  app.get('*', (req, res) => {
    if (req.path.startsWith('/api/')) return res.status(404).json({ error: 'Not found' });
    res.sendFile(path.join(DIST_DIR, 'index.html'));
  });
}

// ===================================================================
// START
// ===================================================================

const PORT = 3456;
const server = app.listen(PORT, '0.0.0.0', () => {
  console.log(`Dashboard API server running on http://0.0.0.0:${PORT}`);
});

// Upgrade HTTP → WebSocket for /ws path
server.on('upgrade', (req: any, socket: any, head: any) => {
  if (req.url === '/ws') {
    (wsProxy as any).upgrade(req, socket, head);
  }
});
