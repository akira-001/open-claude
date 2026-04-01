# エージェント行動強制メカニズム設計

**日付:** 2026-04-01
**ステータス:** 承認済み

## 背景

エージェントは行動ルール（agents.md, soul.md, CLAUDE.md）を「知っている」が、作業の流れの中で適用を忘れる。現状は完全に自己申告制で、技術的な強制メカニズムがない。

### 観測された失敗パターン

| パターン | 既存ルール | 根本原因 |
|---|---|---|
| スキル未使用 | agents.md「スキルを読め」 | 使うべきスキルの判断を忘れる |
| エラーコマンド繰り返し | soul.md「環境要因を先に排除」 | 目の前のタスクに集中して立ち止まれない |
| UI未確認で報告 | CLAUDE.md「/browse で確認」 | 確認ステップを飛ばす |
| 表面的な改善提案 | CLAUDE.md「根本解決」 | 意味判断が必要（機械的に検知不可） |

## 設計原則

- **個別ケースのハードコードはしない**。設定駆動で汎用的に対応する
- **作業を止めない**。Hook は警告のみ（exit 0）、ブロックしない
- **他の cogmem ユーザーにも恩恵がある**汎用機能として実装する

## アーキテクチャ概要

```
┌─────────────────────────────────┐
│         cogmem.toml             │
│  [behavior]                     │
│  consecutive_failure_threshold  │
│  [[skill_triggers]]             │
└──────────┬──────────────────────┘
           │ 参照
     ┌─────┴─────┐
     ▼           ▼
┌──────────┐ ┌──────────────┐
│ cogmem   │ │ cogmem watch │
│ hook     │ │ (wrap時)     │
│ (即時)   │ │ (事後検知)   │
└──────────┘ └──────────────┘
```

同じ `skill_triggers` 設定をリアルタイム層と事後検知層の両方が参照する。

## メカニズム 1: failure-breaker

### 概要

Bash の非ゼロ終了が連続 N 回発生したら、エージェントに警告を注入する。

### 設定

```toml
[behavior]
consecutive_failure_threshold = 2
```

### Hook 設定

- タイミング: `PostToolUse`
- 対象: `Bash`
- 状態管理: `/tmp/cogmem-failure-count-{SESSION}` に連続失敗カウントを保持
- 成功（exit 0）でカウンタリセット

### 注入メッセージ

```
⚠ コマンドが2回連続で失敗しています。
1. 同じアプローチを繰り返さず、エラーメッセージを読んで根本原因を特定してください
2. 環境要因（パス、権限、プロセス状態）を先に排除してください
3. 解決後、再発防止策を検討してください:
   - 既存スキルに手順追加が必要 → cogmem skills track で extra_step を記録
   - 新しいパターン → cogmem skills suggest で記録
```

### ゼロ設定

`cogmem init` で自動的に有効化される。設定不要で全ユーザーが即利用可能。

## メカニズム 2: skill-gate

### 概要

ファイル編集時に、そのファイルに関連するスキルが使用中かを確認し、未使用なら警告を注入する。

### 設定（2層構成）

**組み込みデフォルト（コード内定数）:**

```python
_DEFAULT_SKILL_TRIGGERS = [
    {"pattern": ".claude/skills/**/SKILL.md", "skills": ["skill-improve"]},
    {"pattern": "memory/logs/**", "skills": ["live-logging"]},
]
```

どの cogmem プロジェクトでも共通のマッピング。

**ユーザー定義（cogmem.toml）:**

```toml
[[skill_triggers]]
pattern = "dashboard/templates/**"
skills = ["tdd-dashboard-dev"]

[[skill_triggers]]
pattern = "dashboard/services/**"
skills = ["tdd-dashboard-dev"]

[[skill_triggers]]
pattern = "dashboard/i18n.py"
skills = ["tdd-dashboard-dev"]

[[skill_triggers]]
pattern = "cron-jobs.json"
skills = ["cron-automation"]
```

プロジェクト固有のマッピング。

### Hook 設定

- タイミング: `PreToolUse`
- 対象: `Edit|Write`
- 照合: stdin の `file_path` を skill_triggers のパターンとマッチング
- 判定: `skills.db` の `skill_session_events` で当日の `skill_start` を確認
- 該当スキル未使用なら stderr に警告を出力

### 注入メッセージ

```
⚠ このファイルに関連するスキル [tdd-dashboard-dev] が未使用です。先にスキルを確認してください。
```

### スキル使用判定

`skill_session_events` テーブルで当日の `skill_start` イベントを検索:

```sql
SELECT 1 FROM skill_session_events
WHERE skill_name = ? AND event_type = 'skill_start'
AND date(timestamp) = date('now')
```

## メカニズム 3: cogmem watch 拡張（事後検知）

### 概要

wrap 時に git diff のファイル一覧を skill_triggers と照合し、スキル使用ギャップを検出する。

### フロー

```
wrap Step 0: cogmem watch --since "8 hours ago" --json
  → git diff から編集ファイル一覧を取得
  → skill_triggers（デフォルト + ユーザー定義）とパターンマッチ
  → skill_session_events と照合
  → ギャップを skill_gaps として報告
```

### 出力フォーマット

```json
{
  "skill_gaps": [
    {
      "file": "src/cognitive_memory/dashboard/templates/skills/list.html",
      "expected_skill": "tdd-dashboard-dev",
      "reason": "skill_start not found for today"
    }
  ]
}
```

### wrap での扱い

- `skill_gaps` がある → ログに `[PATTERN]` エントリとして記録
- 引き継ぎの注意事項に「スキル未使用検知: [スキル名]」を追加
- 同じスキルが複数セッションで未使用検知された場合、マッピング不適切の可能性を通知

## cogmem init の強化

`cogmem init` 実行時に:

1. `cogmem.toml` に `[behavior]` セクションを追加（デフォルト閾値付き）
2. `.claude/skills/` をスキャンして既存スキルを検出
3. 検出したスキルに対応する `skill_triggers` テンプレートを `cogmem.toml` にコメントアウト状態で提案
4. `.claude/settings.json` に hooks を登録（既存設定とマージ）

### 生成される settings.json

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Edit|Write",
      "command": "cogmem hook skill-gate"
    }],
    "PostToolUse": [{
      "matcher": "Bash",
      "command": "cogmem hook failure-breaker"
    }]
  }
}
```

## CLI インターフェース

```bash
# Hook から呼ばれる（stdin で JSON を受け取る）
cogmem hook skill-gate       # PreToolUse Edit|Write
cogmem hook failure-breaker  # PostToolUse Bash
```

## 実装の配置

| コンポーネント | 配置場所 | 理由 |
|---|---|---|
| Hook エントリポイント | `cli/hook_cmd.py` | stdin JSON 受信 → 判定 → stderr 出力 |
| skill_triggers 照合 | `skills/store.py` | Hook と Watch の両方が同じ関数を呼ぶ |
| failure-breaker 状態 | `/tmp/cogmem-failure-count-{SESSION}` | セッション単位で隔離 |
| 組み込みデフォルト | `skills/store.py` 定数 | コード内管理 |
| settings.json 生成 | `cli/init_cmd.py` | cogmem init の一部 |

## ドキュメント

- `cogmem readme` に Hooks セクションを追加
- `cogmem skills audit` の出力に「skill_triggers 未設定のスキルがあります」を追加
