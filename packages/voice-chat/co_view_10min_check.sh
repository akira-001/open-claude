#!/bin/bash
# co_view 10分チェック: 音声監視 + 👍チェック（通常モード時のみ）
# crontab: */10 * * * * /Users/akira/workspace/ember/packages/voice-chat/co_view_10min_check.sh

CLAUDE_BIN="/Users/akira/.local/bin/claude"
WORKDIR="/Users/akira/workspace/ember/packages/slack-bot"
LOG="/tmp/co_view_cron_10min.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 10min check start" >> "$LOG"

if [ -f /tmp/co_view_loop_disabled ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] loop disabled via UI, skip" >> "$LOG"
  exit 0
fi

if [ -f /tmp/co_view_auto_approve ]; then
  # 自動承認モード: 音声監視のみ（パッチ適用は hourly が担当）
  cd "$WORKDIR" && "$CLAUDE_BIN" -p "
co_view 音声監視のみ実行して（自動承認モード中）。

## Step 1: 音声確認
直近5分以内に [co_view/stt] または buffer=[1-9] のログがあるか確認:
\`\`\`bash
FIVE_MIN_AGO=\$(date -v-5M '+%Y-%m-%d %H:%M' 2>/dev/null || date -d '5 minutes ago' '+%Y-%m-%d %H:%M')
grep -E '\[co_view/stt\]|buffer=[1-9]' /tmp/whisper-serve.log | awk -v t=\"\$FIVE_MIN_AGO\" '\$0 >= t' | tail -3
\`\`\`

注意: 無音検知時は Slack (C0AHPJMS5QE メインチャンネル) に警告投稿のみ。YouTube シークやパッチ適用はしない。
" --allowedTools "Bash,mcp__claude_ai_Slack__slack_send_message" >> "$LOG" 2>&1
else
  # 通常モード: 音声監視 + 👍チェック
  cd "$WORKDIR" && "$CLAUDE_BIN" -p "
co_view 音声監視 + 👍チェックを実行して。以下の順で実行:

## Step 1: 音声確認
直近5分以内に [co_view/stt] または buffer=[1-9] のログがあるか確認:
\`\`\`bash
FIVE_MIN_AGO=\$(date -v-5M '+%Y-%m-%d %H:%M' 2>/dev/null || date -d '5 minutes ago' '+%Y-%m-%d %H:%M')
grep -E '\[co_view/stt\]|buffer=[1-9]' /tmp/whisper-serve.log | awk -v t=\"\$FIVE_MIN_AGO\" '\$0 >= t' | tail -3
\`\`\`

無音検知時は Slack (C0AHPJMS5QE メインチャンネル) に警告投稿のみ。YouTube シークはしない。

## Step 2: 👍チェック
Slackチャンネル C0AHPJMS5QE の最新メッセージを読み（mcp__claude_ai_Slack__slack_read_channel で limit=5）、
「🎬 co_view 改善ループ」または「🎬 co_view」を含む最新メッセージに 👍 リアクションがあるか確認。

👍がある場合のみ → /Users/akira/.claude/skills/co-view-improve/skill.md の Step 4〜6 を実行（パッチ適用・再起動・完了通知）。
👍がない場合 → 何もしない。

注意: Slack投稿は必ずメインチャンネル C0AHPJMS5QE に（thread_tsは使わない）。
" --allowedTools "Bash,mcp__claude_ai_Slack__slack_read_channel,mcp__claude_ai_Slack__slack_send_message,Edit,Read" >> "$LOG" 2>&1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 10min check done" >> "$LOG"
