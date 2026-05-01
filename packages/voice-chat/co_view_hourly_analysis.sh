#!/bin/bash
# co_view 毎時分析: ログ分析 → Slack投稿（改善案）
# 自動承認モード時はそのままパッチ適用まで実行
# crontab: 17 * * * * /Users/akira/workspace/ember/packages/voice-chat/co_view_hourly_analysis.sh

CLAUDE_BIN="/Users/akira/.local/bin/claude"
WORKDIR="/Users/akira/workspace/ember/packages/slack-bot"
LOG="/tmp/co_view_cron_hourly.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] hourly analysis start" >> "$LOG"

if [ -f /tmp/co_view_loop_disabled ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] loop disabled via UI, skip" >> "$LOG"
  exit 0
fi

if [ -f /tmp/co_view_auto_approve ]; then
  # 自動承認モード: 分析 + Slack投稿 + パッチ自動適用
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] auto_approve mode: running full loop (Steps 1-6)" >> "$LOG"
  cd "$WORKDIR" && "$CLAUDE_BIN" -p "
/Users/akira/.claude/skills/co-view-improve/skill.md を読んで、Step 1〜6（全ステップ）を実行して。

- 自動承認モードで動作中（Slackの👍なしで即時パッチ適用）
- Step 2のSlack投稿フォーマットに「🤖 自動承認モード（睡眠中）」を冒頭に追記
- Step 2の「💡 改善案 (👍で適用)」の代わりに「💡 適用済み改善」として投稿
- Step 3（Cron登録）はスキップ（既に永続cronが動いている）
- Step 5でサーバー再起動 → Step 6で完了通知をSlackに投稿
- Slack投稿は必ずメインチャンネル C0AHPJMS5QE に（thread_tsは使わない）
- 投稿したメッセージの ts を /tmp/co_view_latest_slack_ts.txt に保存:
  echo \"<ts>\" > /tmp/co_view_latest_slack_ts.txt
" --allowedTools "Bash,mcp__claude_ai_Slack__slack_send_message,Read,Edit" >> "$LOG" 2>&1
else
  # 通常モード: 分析 + Slack投稿のみ（👍待ち）
  cd "$WORKDIR" && "$CLAUDE_BIN" -p "
/Users/akira/.claude/skills/co-view-improve/skill.md を読んで、Step 1〜2（ログ分析 + Slack投稿）を実行して。

- Step 3（Cron登録）はスキップ（既に永続cronが動いている）
- Step 4〜6（パッチ適用）は 👍 承認後に 10分チェック側が実行するのでスキップ
- Slack投稿は必ずメインチャンネル C0AHPJMS5QE に（thread_tsは使わない）
- 投稿したメッセージの ts を /tmp/co_view_latest_slack_ts.txt に保存:
  echo \"<ts>\" > /tmp/co_view_latest_slack_ts.txt
" --allowedTools "Bash,mcp__claude_ai_Slack__slack_send_message,Read" >> "$LOG" 2>&1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] hourly analysis done" >> "$LOG"
