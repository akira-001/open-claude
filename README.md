# ember

Akiraさんの常時稼働 AI パートナー基盤 (Mei / Eve / Haru) のモノレポ。

## 構成

| Package | 言語 | 役割 |
|---|---|---|
| `packages/slack-bot` | TypeScript | Slack gateway、scheduler、proactive agent |
| `packages/dashboard` | TypeScript (React + Express) | Web UI、状態モニタ |
| `packages/voice-chat` | Python | Whisper STT、Irodori TTS、co_view、meeting digest |
| `packages/ember-chat` | TypeScript (Electron) | デスクトップアプリ shell |

## 共通リソース

- `identity/` — Mei / Eve / Haru ペルソナ（権威）
- `memory/` — cogmem (vectors.db, skills.db, knowledge/, logs/)
- `data/` — 動的状態（P4 で集約予定。現在は `~/workspace/claude-code-slack-bot/data/` 経由）

## 開発

```bash
# Initial setup
pnpm install
uv sync

# Build all packages
pnpm build

# Run tests
pnpm test
```

## マイグレーション

旧 `open-claude` リポと旧 `claude-code-slack-bot` リポを統合中。

| Phase | 内容 | プラン |
|---|---|---|
| P0 | モノレポ骨格作成 | `docs/superpowers/plans/2026-05-01-monorepo-skeleton.md` |
| P1 | slack-bot + dashboard 移植 | (予定) |
| P2 | voice_chat + ember-chat 移植 | (予定) |
| P3 | Slack gateway 集約 | (予定) |
| P4 | State 権威統一 | (予定) |
| P5 | 制御 API 化（sentinel 廃止） | (予定) |
| P6 | UI 統合（Electron を React shell 化） | (予定) |
| P7 | Identity 権威統一 | (予定) |
