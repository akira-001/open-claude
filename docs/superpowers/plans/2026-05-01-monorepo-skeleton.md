# Ember Monorepo Skeleton (P0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `open-claude` を `ember` リポにリネームし、pnpm + uv の monorepo 骨格を追加する。既存の `scripts/voice_chat`、`scripts/ember-chat`、launchd `local.whisper.serve`、pm2 `claude-slack-bot`、dashboard `:3456` は **P0 では一切触らない**。実コードの `packages/` 移植は P1（slack-bot）/ P2（voice_chat + ember-chat）で別途実施。

**Architecture:**
1. GitHub `akira-001/open-claude` を `akira-001/ember` にリネーム
2. ローカル `~/workspace/open-claude` を `~/workspace/ember` に rename + remote URL 更新
3. ルートに pnpm workspace 設定 + uv workspace 設定を追加
4. `packages/{slack-bot, dashboard, voice-chat, ember-chat}/` を予約（中身は placeholder のみ、実装は後続プラン）
5. `~/workspace/open-claude → ~/workspace/ember` に後方互換 symlink を貼り、launchd / cron / 絶対パス参照を全て温存
6. 旧 `claude-code-slack-bot` リポは README に migration notice を追加するのみ（archive は P3 後）

**Tech Stack:**
- Node.js 24+ (nodenv)
- pnpm 9+
- Python 3.13+
- uv 0.4+
- TypeScript 5+

**前提条件:**
- `gh` CLI が認証済み (`gh auth status` で確認)
- `pnpm` と `uv` がインストール済み (`which pnpm uv` で確認)
- 両既存リポ (`open-claude`, `claude-code-slack-bot`) が clean、リモート push 済み

---

## Task 1: 事前確認 — 両リポ状態と稼働サービス把握

**Files:** なし（観察のみ）

- [ ] **Step 1: 両リポの作業状態確認**

```bash
cd /Users/akira/workspace/open-claude && git status --short
cd /Users/akira/workspace/claude-code-slack-bot && git status --short
```

期待: 両方ほぼ空出力。ただし `open-claude` 側で `?? docs/superpowers/plans/2026-05-01-monorepo-skeleton.md` の untracked 行は OK（Task 11 でコミット予定）。それ以外の dirty 状態（modified / staged）があれば本タスク中断、`git stash` または個別コミットで処理してから再開。

- [ ] **Step 2: リモート push 状況確認**

```bash
cd /Users/akira/workspace/open-claude && git log origin/main..HEAD --oneline
cd /Users/akira/workspace/claude-code-slack-bot && git log origin/main..HEAD --oneline
```

期待: 両方空（local commit が push 済み）。

- [ ] **Step 3: 稼働中サービス確認**

```bash
launchctl list | grep -i whisper
pm2 list | grep claude-slack-bot
curl -sI http://localhost:8767/ -m 3 | head -1
curl -sI http://localhost:3456/ -m 3 | head -1
```

期待: voice_chat (8767) と claude-slack-bot online、dashboard が 200/302 応答。

- [ ] **Step 4: launchd plist の参照パス記録**

```bash
plutil -p ~/Library/LaunchAgents/local.whisper.serve.plist | grep -E "WorkingDirectory|/Users"
```

期待: `/Users/akira/workspace/open-claude/scripts/voice_chat/` を含む文字列が出る。**P0 では一切変更しない**。次タスクで symlink で互換性を保つ。

- [ ] **Step 5: コミット不要（観察のみ）**

---

## Task 2: GitHub リポ名変更（open-claude → ember）

**Files:** GitHub 設定 + `~/workspace/open-claude/.git/config`

- [ ] **Step 1: gh CLI 経由でリネーム**

```bash
gh repo rename ember --repo akira-001/open-claude
```

期待出力: `✓ Renamed repository akira-001/open-claude to akira-001/ember`

- [ ] **Step 2: ローカル remote URL 更新**

```bash
cd /Users/akira/workspace/open-claude
git remote set-url origin git@github.com.sub:akira-001/ember.git
git remote -v
```

期待: `origin git@github.com.sub:akira-001/ember.git (fetch/push)` 2行。

- [ ] **Step 3: fetch して接続確認**

```bash
git fetch origin
```

期待: エラーなし、最新リモートにアクセス可。

- [ ] **Step 4: コミット不要（remote URL は .git/config のみ、tracked file ではない）**

---

## Task 3: ローカルディレクトリ rename + symlink

**Files:**
- Rename: `/Users/akira/workspace/open-claude` → `/Users/akira/workspace/ember`
- Create symlink: `/Users/akira/workspace/open-claude` → `/Users/akira/workspace/ember`

- [ ] **Step 1: open-claude を ember に rename**

```bash
mv /Users/akira/workspace/open-claude /Users/akira/workspace/ember
ls -la /Users/akira/workspace/ember | head -3
```

期待: ember ディレクトリが存在、中身は元の open-claude 全部。

- [ ] **Step 2: 後方互換 symlink を貼る**

```bash
ln -s /Users/akira/workspace/ember /Users/akira/workspace/open-claude
ls -la /Users/akira/workspace/open-claude
```

期待出力に `open-claude -> /Users/akira/workspace/ember` が含まれる。これで launchd / cron / 絶対パス参照すべて生きる。

- [ ] **Step 3: 稼働サービス健全性確認**

```bash
sleep 2
curl -sI http://localhost:8767/ -m 3 | head -1
pm2 list | grep claude-slack-bot
```

期待: voice_chat も bot も応答継続（symlink 経由でアクセス可能）。

- [ ] **Step 4: コミット不要（ファイルシステム操作のみ）**

---

## Task 3.5: monorepo-skeleton ブランチ作成

**Files:** なし（git ブランチ操作のみ）

main への commit を防ぐため、最初の commit が出る Task 4 の前に専用ブランチに切り替える。

- [ ] **Step 1: 現在のブランチ確認**

```bash
cd /Users/akira/workspace/ember
git branch --show-current
```

期待: `main`

- [ ] **Step 2: monorepo-skeleton ブランチ作成 + 切替**

```bash
git checkout -b monorepo-skeleton
git branch --show-current
```

期待: `monorepo-skeleton`

- [ ] **Step 3: コミット不要**

---

## Task 4: pnpm-workspace.yaml 作成

**Files:**
- Create: `/Users/akira/workspace/ember/pnpm-workspace.yaml`

- [ ] **Step 1: pnpm-workspace.yaml を書く**

`/Users/akira/workspace/ember/pnpm-workspace.yaml`:

```yaml
packages:
  - 'packages/*'
```

- [ ] **Step 2: 確認**

```bash
cat /Users/akira/workspace/ember/pnpm-workspace.yaml
```

期待: 上記内容と一致。

- [ ] **Step 3: コミット**

```bash
cd /Users/akira/workspace/ember
git add pnpm-workspace.yaml
git commit -m "feat(monorepo): add pnpm-workspace.yaml"
```

---

## Task 5: ルート package.json 作成

**Files:**
- Create: `/Users/akira/workspace/ember/package.json`

- [ ] **Step 1: ルート package.json を書く**

`/Users/akira/workspace/ember/package.json`:

```json
{
  "name": "ember-monorepo",
  "version": "0.1.0",
  "private": true,
  "description": "Akira's always-on AI partner platform — voice, Slack, identity, memory, dashboard",
  "engines": {
    "node": ">=24",
    "pnpm": ">=9"
  },
  "scripts": {
    "build": "pnpm -r run build",
    "test": "pnpm -r run test",
    "lint": "pnpm -r run lint",
    "typecheck": "pnpm -r run typecheck"
  },
  "devDependencies": {
    "typescript": "^5.6.0"
  }
}
```

- [ ] **Step 2: pnpm install 実行**

```bash
cd /Users/akira/workspace/ember
pnpm install
```

期待: `Done in <Ns`、エラーなし。`pnpm-lock.yaml` と `node_modules/` が生成される。

- [ ] **Step 3: コミット**

```bash
git add package.json pnpm-lock.yaml
git commit -m "feat(monorepo): add root package.json with pnpm workspaces"
```

---

## Task 6: pyproject.toml 作成（uv ルート）

**Files:**
- Create: `/Users/akira/workspace/ember/pyproject.toml`

- [ ] **Step 1: ルート pyproject.toml を書く**

P0 では workspace member は宣言しない（voice-chat はまだ実装が `scripts/voice_chat/` にあり packages/ 配下が空のため）。P2 で `members = ["packages/voice-chat"]` を追加する。

`/Users/akira/workspace/ember/pyproject.toml`:

```toml
[project]
name = "ember-monorepo"
version = "0.1.0"
description = "Akira's always-on AI partner platform — Python packages root"
requires-python = ">=3.13"

[tool.uv]
managed = true
```

- [ ] **Step 2: uv lock で構文確認**

```bash
cd /Users/akira/workspace/ember
uv lock
```

期待: `Resolved 0 packages` 程度の即終了、エラーなし、`uv.lock` 生成。

- [ ] **Step 3: コミット**

```bash
git add pyproject.toml uv.lock
git commit -m "feat(monorepo): add root pyproject.toml with uv"
```

---

## Task 7: tsconfig.base.json 作成

**Files:**
- Create: `/Users/akira/workspace/ember/tsconfig.base.json`

- [ ] **Step 1: tsconfig.base.json を書く**

`/Users/akira/workspace/ember/tsconfig.base.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "esModuleInterop": true,
    "strict": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "forceConsistentCasingInFileNames": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true
  }
}
```

- [ ] **Step 2: コミット**

```bash
git add tsconfig.base.json
git commit -m "feat(monorepo): add shared tsconfig.base.json"
```

---

## Task 8: .gitignore 拡張

**Files:**
- Modify: `/Users/akira/workspace/ember/.gitignore`

- [ ] **Step 1: 既存 .gitignore 確認**

```bash
cat /Users/akira/workspace/ember/.gitignore
```

- [ ] **Step 2: monorepo 用エントリ追記**

`.gitignore` の末尾に以下を追記:

```gitignore

# === Monorepo additions (P0) ===
node_modules/
**/node_modules/
.pnpm-store/
**/dist/
**/.next/
**/.turbo/

# Python (uv)
**/.venv/
__pycache__/
**/__pycache__/
*.pyc
.uv-cache/

# Editor
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```

注: 既存 `.venv/` 行があれば `**/.venv/` だけを追加（重複行にならないよう確認）。

- [ ] **Step 3: コミット**

```bash
git add .gitignore
git commit -m "chore: extend .gitignore for monorepo (pnpm, uv, editors)"
```

---

## Task 9: packages/ ディレクトリ予約 + placeholder package.json 群

**Files:**
- Create: `/Users/akira/workspace/ember/packages/slack-bot/package.json`
- Create: `/Users/akira/workspace/ember/packages/dashboard/package.json`
- Create: `/Users/akira/workspace/ember/packages/ember-chat/package.json`
- Create: `/Users/akira/workspace/ember/packages/voice-chat/README.md`
- Create: `/Users/akira/workspace/ember/packages/{slack-bot,dashboard,ember-chat}/README.md`

注: voice-chat は P0 では Python ソースを置かない（実体は `scripts/voice_chat/` のまま）。pyproject.toml は P2 で追加する。

- [ ] **Step 1: ディレクトリ作成**

```bash
mkdir -p /Users/akira/workspace/ember/packages/{slack-bot,dashboard,voice-chat,ember-chat}
```

- [ ] **Step 2: slack-bot placeholder package.json**

`/Users/akira/workspace/ember/packages/slack-bot/package.json`:

```json
{
  "name": "@ember/slack-bot",
  "version": "0.0.0",
  "private": true,
  "description": "Slack gateway, scheduler, proactive agents (P1 で移植予定)",
  "scripts": {
    "build": "echo 'P1 で実装' && exit 0",
    "test": "echo 'P1 で実装' && exit 0"
  }
}
```

- [ ] **Step 3: dashboard placeholder package.json**

`/Users/akira/workspace/ember/packages/dashboard/package.json`:

```json
{
  "name": "@ember/dashboard",
  "version": "0.0.0",
  "private": true,
  "description": "React dashboard + Express server (P1 で移植予定)",
  "scripts": {
    "build": "echo 'P1 で実装' && exit 0",
    "test": "echo 'P1 で実装' && exit 0"
  }
}
```

- [ ] **Step 4: ember-chat placeholder package.json**

`/Users/akira/workspace/ember/packages/ember-chat/package.json`:

```json
{
  "name": "@ember/chat",
  "version": "0.0.0",
  "private": true,
  "description": "Electron shell for ember (P2 で移植予定、P6 で React shell 化)",
  "scripts": {
    "build": "echo 'P2 で実装' && exit 0",
    "test": "echo 'P2 で実装' && exit 0"
  }
}
```

- [ ] **Step 5: 各 package の README.md**

`/Users/akira/workspace/ember/packages/slack-bot/README.md`:
```markdown
# @ember/slack-bot

Slack gateway + scheduler + proactive agents.

- **移植元**: `~/workspace/claude-code-slack-bot/src/`
- **移植プラン**: P1 (`docs/superpowers/plans/2026-05-XX-monorepo-slack-bot-migration.md` 予定)
- **状態**: P0 では空。pnpm workspace 予約のみ。
```

`/Users/akira/workspace/ember/packages/dashboard/README.md`:
```markdown
# @ember/dashboard

React + Vite dashboard, Express API server.

- **移植元**: `~/workspace/claude-code-slack-bot/dashboard/`
- **移植プラン**: P1
- **状態**: P0 では空。pnpm workspace 予約のみ。
```

`/Users/akira/workspace/ember/packages/voice-chat/README.md`:
```markdown
# voice-chat

Whisper STT + Irodori TTS + co_view + meeting digest.

- **移植元**: `~/workspace/ember/scripts/voice_chat/`（rename 後、もとは open-claude）
- **移植プラン**: P2
- **状態**: P0 では空ディレクトリのみ。実コードは `scripts/voice_chat/` で稼働中。pyproject.toml は P2 で追加。
```

`/Users/akira/workspace/ember/packages/ember-chat/README.md`:
```markdown
# @ember/chat

Electron shell hosting the dashboard UI.

- **移植元**: `~/workspace/ember/scripts/ember-chat/`（rename 後、もとは open-claude）
- **移植プラン**: P2（移動）→ P6（React shell 化）
- **状態**: P0 では空。pnpm workspace 予約のみ。
```

- [ ] **Step 6: pnpm install 検証**

```bash
cd /Users/akira/workspace/ember
pnpm install
```

期待: 3 つの placeholder package が workspace 認識される。エラーなし。

- [ ] **Step 7: コミット**

```bash
git add packages/ pnpm-lock.yaml
git commit -m "feat(monorepo): scaffold packages/{slack-bot,dashboard,voice-chat,ember-chat}"
```

---

## Task 10: ルート README.md 作成

**Files:**
- Modify: `/Users/akira/workspace/ember/README.md`（既存があれば overwrite）

- [ ] **Step 1: 既存 README 確認**

```bash
test -f /Users/akira/workspace/ember/README.md && head -5 /Users/akira/workspace/ember/README.md || echo "(no existing README)"
```

- [ ] **Step 2: monorepo 用 README.md を書く**

`/Users/akira/workspace/ember/README.md`:

```markdown
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
```

- [ ] **Step 3: コミット**

```bash
git add README.md
git commit -m "docs: add monorepo README"
```

---

## Task 11: P0 プランドキュメントをコミット

このプラン文書 (`docs/superpowers/plans/2026-05-01-monorepo-skeleton.md`) は既にローカル存在する。コミットするだけ。

- [ ] **Step 1: ファイル存在確認**

```bash
ls /Users/akira/workspace/ember/docs/superpowers/plans/2026-05-01-monorepo-skeleton.md
```

期待: ファイルが存在。

- [ ] **Step 2: コミット**

```bash
cd /Users/akira/workspace/ember
git add docs/superpowers/plans/2026-05-01-monorepo-skeleton.md
git commit -m "docs(plan): add P0 monorepo skeleton plan"
```

---

## Task 12: push + PR 作成

**Files:** GitHub PR

ブランチは Task 3.5 で既に `monorepo-skeleton` に切替済み。ここでは push と PR 作成のみ。

- [ ] **Step 1: 現在のブランチ確認**

```bash
cd /Users/akira/workspace/ember
git branch --show-current
```

期待: `monorepo-skeleton`（Task 3.5 で切替済み）。

- [ ] **Step 2: push**

```bash
git push -u origin monorepo-skeleton
```

期待: `Branch 'monorepo-skeleton' set up to track 'origin/monorepo-skeleton'`。

- [ ] **Step 3: PR 作成**

```bash
gh pr create --base main --head monorepo-skeleton --title "feat(monorepo): P0 skeleton — pnpm + uv workspaces" --body "$(cat <<'EOF'
## 概要
P0: モノレポ骨格作成。`open-claude` を `ember` にリネームし、pnpm + uv の workspace 配管を追加。

## 内容
- pnpm-workspace.yaml + ルート package.json
- pyproject.toml (uv)
- tsconfig.base.json
- packages/{slack-bot, dashboard, voice-chat, ember-chat}/ 予約（中身は placeholder のみ、P1/P2 で実コード移植）
- 既存 scripts/voice_chat と scripts/ember-chat は触らず、launchd / dashboard 接続は健全
- ローカル symlink `~/workspace/open-claude → ~/workspace/ember` で旧パス参照を温存

## 検証
- [x] pnpm install 成功
- [x] uv lock 成功
- [x] voice_chat (8767) 応答確認
- [x] claude-slack-bot (3457) 応答確認
- [x] dashboard (3456) 応答確認

## 次のステップ
- P1: slack-bot を packages/ に移植
- P2: voice_chat / ember-chat を scripts/ から packages/ に移動 + launchd plist 更新
EOF
)"
```

期待: `https://github.com/akira-001/ember/pull/N` が出力される。

- [ ] **Step 4: PR URL を記録**

PR URL を後続作業のために控えておく（コミット不要）。

---

## Task 13: 旧 claude-code-slack-bot に migration notice

**Files:**
- Modify: `/Users/akira/workspace/claude-code-slack-bot/README.md`

- [ ] **Step 1: README.md の冒頭に notice を追加**

`/Users/akira/workspace/claude-code-slack-bot/README.md` の **1行目（H1 の前）** に以下を挿入:

```markdown
> **⚠️ MIGRATION NOTICE (2026-05-01)**: このリポジトリは [ember monorepo](https://github.com/akira-001/ember) へ統合中。最新の開発は ember 側で行う。P3 完了後（予定 2026-XX）にこのリポは archive される。

```

- [ ] **Step 2: コミット & push**

```bash
cd /Users/akira/workspace/claude-code-slack-bot
git add README.md
git commit -m "docs: add migration notice (ember monorepo)"
git push origin main
```

---

## Task 14: 動作確認 — 既存サービスの最終健全性チェック

**Files:** なし（観察のみ）

すべての変更が稼働中サービスを壊していないか確認。

- [ ] **Step 1: voice_chat 応答**

```bash
curl -sI http://localhost:8767/ -m 3 | head -1
```

期待: `HTTP/1.1 200 OK` または `HTTP/1.1 404`（応答していれば OK）。

- [ ] **Step 2: claude-slack-bot 応答 + cron 動作**

```bash
pm2 list | grep claude-slack-bot
curl -sS -X POST http://127.0.0.1:3457/internal/run-job/co-view-improve -m 5
```

期待: pm2 status `online`、internal API が `{"status":"success",...}` を返す。

- [ ] **Step 3: dashboard 応答**

```bash
curl -sI http://localhost:3456/ -m 3 | head -1
```

期待: 200 / 302（dev server 起動中なら）。停止中なら起動して再確認。

- [ ] **Step 4: launchd plist の参照パスが symlink 経由で生きているか**

```bash
plutil -p ~/Library/LaunchAgents/local.whisper.serve.plist | grep "/Users"
ls -la /Users/akira/workspace/open-claude
```

期待: plist が `/Users/akira/workspace/open-claude/...` を参照しており、`open-claude` が `ember` への symlink である。

- [ ] **Step 5: 一日経過後のサービス健全性再確認（手動）**

実運用で 24h 経って launchd / pm2 / cron 全部が問題なく動いているか確認。問題なければ P1 へ。

- [ ] **Step 6: コミット不要（観察のみ）**

---

## P0 完了条件（DoD）

1. ✅ `~/workspace/ember/` が monorepo 化されている
2. ✅ `pnpm install` と `uv lock` が成功する
3. ✅ `packages/{slack-bot, dashboard, voice-chat, ember-chat}/` が予約済み（placeholder のみ）
4. ✅ **既存サービス（voice_chat 8767、claude-slack-bot 3457、dashboard 3456）が壊れていない**
5. ✅ PR が GitHub `akira-001/ember` 上に存在
6. ✅ このプラン文書がコミット済み
7. ✅ 旧 `claude-code-slack-bot` の README に migration notice
8. ✅ 24h 後も全サービス健全

---

## P0 後の状態

```
~/workspace/
├── open-claude → ember           (symlink、旧パス参照を温存)
├── ember/                        (旧 open-claude 中身 + monorepo 配管)
│   ├── packages/
│   │   ├── slack-bot/            (空、P1 で移植)
│   │   ├── dashboard/            (空、P1 で移植)
│   │   ├── voice-chat/           (空、P2 で移植)
│   │   └── ember-chat/           (空、P2 で移植)
│   ├── scripts/
│   │   ├── voice_chat/           (旧来のまま — launchd が指す)
│   │   └── ember-chat/           (旧来のまま)
│   ├── identity/                 (旧来のまま、P7 で権威化)
│   ├── memory/                   (旧来のまま、P4 で slack-bot 側とマージ予定)
│   ├── package.json              (新)
│   ├── pnpm-workspace.yaml       (新)
│   ├── pnpm-lock.yaml            (新)
│   ├── pyproject.toml            (新)
│   ├── uv.lock                   (新)
│   ├── tsconfig.base.json        (新)
│   └── README.md                 (新)
└── claude-code-slack-bot/        (現状維持、archive notice のみ追加)
```

---

## ロールバック手順（万が一）

P0 中に何か壊れたら以下で復旧:

1. `rm /Users/akira/workspace/open-claude && mv /Users/akira/workspace/ember /Users/akira/workspace/open-claude` でディレクトリ名を戻す
2. `gh repo rename open-claude --repo akira-001/ember` で GitHub 名を戻す
3. `cd /Users/akira/workspace/open-claude && git remote set-url origin git@github.com.sub:akira-001/open-claude.git`
4. `monorepo-skeleton` ブランチを削除、main に戻す: `git checkout main && git branch -D monorepo-skeleton`
5. PR は close、`claude-code-slack-bot/README.md` の notice もリバート
