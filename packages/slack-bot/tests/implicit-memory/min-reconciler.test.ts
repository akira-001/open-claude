import { describe, it, expect, vi } from 'vitest';
import { Reconciler } from '../../src/implicit-memory/reconciler';
import { ImplicitMemoryStore } from '../../src/implicit-memory/store';
import { createMemoryEntry } from '../../src/implicit-memory/types';
import { join } from 'path';
import os from 'os';

describe('Reconciler min test', () => {
  it('imports ok', () => {
    expect(Reconciler).toBeDefined();
  });

  it('stores new entry', async () => {
    const tmpPath = join(os.tmpdir(), `min-test-${Date.now()}.json`);
    const store = new ImplicitMemoryStore(tmpPath, 'mei');
    const mockJudge = vi.fn();
    const mockGetEmbedding = vi.fn().mockResolvedValue([1, 0, 0]);
    const mockCosineSimilarity = vi.fn().mockReturnValue(0.3);

    const reconciler = new Reconciler(store, {
      judge: mockJudge,
      getEmbedding: mockGetEmbedding,
      cosineSimilarity: mockCosineSimilarity,
    });

    const entry = createMemoryEntry({
      content: 'test',
      context: 'test',
      source: 'slack_message',
      layer: 'facts',
    });
    entry.embedding = [1, 0, 0];

    const result = await reconciler.checkAndReconcile('facts', entry);
    expect(result).toBe('new');
  });
});
