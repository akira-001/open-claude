# Smart Auto-Commit Messages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop hook の auto-commit メッセージに変更内容のサマリーを含め、git log の可読性を向上させる

**Architecture:** `save-session-summary.sh` の git commit セクションを改善。`git diff --cached --stat` の出力から変更ファイル数と主要ファイルを抽出し、コミットメッセージに含める。session ログの named commit（Wrap 時に Claude が書くもの）はそのまま残し、auto-commit のみ改善する。

**Tech Stack:** Bash, git

---

## NOT in scope

- **open-claude リポジトリへのテスト追加**: agents.md は AI への行動指示であってコードではない。ユニットテストの対象にならない。プロトコル遵守は `cogmem watch`（git パターン検知）と `skill-creator`（eval）で検証済み。
- **stop hook の大規模リファクタリング**: 現行の hook は安定動作している。コミットメッセージ改善のみに限定。
- **named commit（Wrap 時）の変更**: Claude が Wrap 時に書くコミットメッセージは既に十分な情報を含んでいる。

## What already exists

- `~/.claude/hooks/save-session-summary.sh` — 現行の stop hook。auto-commit 部分は最後の15行。
- 現行のコミットメッセージ: `session: ${DATE} auto-commit on exit` — 何が変わったか不明。
- git の `--stat` オプション — 変更ファイルのサマリーを取得可能。

---

## ファイル構成

| ファイル | 役割 |
|---------|------|
| `~/.claude/hooks/save-session-summary.sh` (修正) | コミットメッセージ生成ロジックの改善 |

---

### Task 1: コミットメッセージに変更サマリーを追加

**Files:**
- Modify: `~/.claude/hooks/save-session-summary.sh`

- [ ] **Step 1: 現行の auto-commit セクションを確認**

現行コード（42-51行目付近）:
```bash
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard 2>/dev/null)" ]; then
    git add -A 2>/dev/null
    git commit -m "session: ${DATE} auto-commit on exit" 2>/dev/null
fi
```

- [ ] **Step 2: 改善版のコミットメッセージ生成ロジックを実装**

`git add -A` の後、`git diff --cached --stat` で変更サマリーを取得し、コミットメッセージに含める。

```bash
  if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard 2>/dev/null)" ]; then
    git add -A 2>/dev/null

    # Build smart commit message from staged changes
    STAT=$(git diff --cached --stat 2>/dev/null | tail -1)
    # Extract changed file names (top 3, without path prefix for brevity)
    FILES=$(git diff --cached --name-only 2>/dev/null | head -3 | xargs -I{} basename {} | paste -sd ', ' -)
    FILE_COUNT=$(git diff --cached --name-only 2>/dev/null | wc -l | tr -d ' ')

    if [ "$FILE_COUNT" -gt 3 ]; then
      MSG="session: ${DATE} auto-commit (${FILES}, +$((FILE_COUNT - 3)) more)"
    elif [ -n "$FILES" ]; then
      MSG="session: ${DATE} auto-commit (${FILES})"
    else
      MSG="session: ${DATE} auto-commit on exit"
    fi

    git commit -m "$MSG" 2>/dev/null
  fi
```

**期待される出力例:**
- `session: 2026-03-25 auto-commit (agents.md, 2026-03-25.md)`
- `session: 2026-03-25 auto-commit (agents.md, skills.db, summary.md, +2 more)`
- `session: 2026-03-25 auto-commit on exit`（変更なしフォールバック）

- [ ] **Step 3: 手動テスト**

テスト用に一時ファイルを作成し、hook を直接実行してコミットメッセージを確認:

```bash
cd /Users/akira/workspace/open-claude
echo "test" > /tmp/test-hook-check.txt
# hookを手動実行する代わりに、ロジック部分だけ抽出して確認
git add -A --dry-run 2>/dev/null | head -5
```

- [ ] **Step 4: 実際の hook ファイルを更新**

`~/.claude/hooks/save-session-summary.sh` の auto-commit セクション（`git add -A` と `git commit` の間）を Step 2 のコードに置き換える。

- [ ] **Step 5: コミット**

```bash
cd /Users/akira/workspace/open-claude
git add docs/superpowers/plans/2026-03-25-smart-auto-commit-messages.md
git commit -m "docs: plan for smart auto-commit messages"
```

---

## 検証方法

1. Claude Code セッションを終了して stop hook が発火することを確認
2. `git log --oneline -5` で新しいフォーマットのコミットメッセージを確認
3. ファイル名が含まれていることを確認
