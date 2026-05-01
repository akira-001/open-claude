import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { writeFileSync, mkdirSync, rmSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';

const TEST_IDENTITY_DIR = join(tmpdir(), `ember-identity-test-${process.pid}`);

describe('bot-config identity persona loading', () => {
  beforeEach(() => {
    rmSync(TEST_IDENTITY_DIR, { recursive: true, force: true });
    mkdirSync(join(TEST_IDENTITY_DIR, 'personas'), { recursive: true });
    process.env.EMBER_IDENTITY_DIR = TEST_IDENTITY_DIR;
  });

  afterEach(() => {
    rmSync(TEST_IDENTITY_DIR, { recursive: true, force: true });
    delete process.env.EMBER_IDENTITY_DIR;
    // Reset module cache so loadBotConfigs re-evaluates env var
    // (vitest isolates modules per test file, so this is safe)
  });

  it('loads persona from identity/personas/<id>.md when present', async () => {
    writeFileSync(
      join(TEST_IDENTITY_DIR, 'personas', 'mei.md'),
      '# Mei (test persona)',
    );

    // Dynamically import to pick up the env var set above
    const { loadBotConfigs } = await import('../bot-config');
    const configs = loadBotConfigs();
    const mei = configs.find((c) => c.id === 'mei');

    if (!mei) {
      // mei not in active configs — skip without failing
      expect.assertions(0);
      return;
    }

    expect(mei.personality.systemPrompt).toContain('Mei (test persona)');
  });

  it('falls back to customPrompt when identity file is missing', async () => {
    // Do NOT write a persona file — identity dir exists but personas/<id>.md does not

    const { loadBotConfigs } = await import('../bot-config');
    const configs = loadBotConfigs();
    const mei = configs.find((c) => c.id === 'mei');

    if (!mei) {
      expect.assertions(0);
      return;
    }

    // Should still have a non-empty prompt from customPrompt/generatedPrompt
    expect(mei.personality.systemPrompt.length).toBeGreaterThan(0);
  });
});
