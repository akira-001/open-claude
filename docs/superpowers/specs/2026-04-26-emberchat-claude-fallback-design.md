# EmberChat: Local LLM Refusal → Claude Fallback (Chat Path)

**Status:** Spec  
**Date:** 2026-04-26  
**Scope:** `scripts/voice_chat/app.py` (text chat WebSocket path only)

## 問題

EmberChat の通常チャットパス (WebSocket text → Ollama `gemma4:e4b` → TTS) で、ローカルLLMが「できません」「申し訳」「専門外」等の refusal を返した時、ユーザーにそのまま返してしまう。Always-on (常時マイク) モードには既に Slack Bot 経由の Claude フォールバックがあるが、チャットパスには適用されていない。

## ゴール

通常チャットでローカルLLMが refusal を返したら、既存の Claude フォールバック機構を流用してリトライする。

## 既存資産（流用するもの、変更しない）

| コンポーネント | 場所 | 役割 |
|---|---|---|
| `_wait_cache` | `app.py:115-121` | 「ちょっと待ってね、調べてくる」等の事前生成 TTS キャッシュ |
| `_ask_slack_bot()` | `app.py:4783-4828` | claude-code-slack-bot の `http://127.0.0.1:3457/internal/ask` HTTP API → Claude (MCP tools 付き) |
| `_TOOL_ROUTE_FAIL_COUNT/UNTIL` | `app.py:4621-4624` | 連続失敗時 90s cooldown 機構 |
| `_tool_route_in_cooldown()` | `app.py:4657-4658` | cooldown 残時間チェック |

## 変更点

### 1. 新規定数 `_CHAT_REFUSAL_PATTERNS`

`app.py` のモジュールトップ（既存 `_TOOL_NEEDED_KEYWORDS` 付近）に追加:

```python
_CHAT_REFUSAL_PATTERNS = ("申し訳", "役割範囲外", "Claude Code", "できません", "お手伝いできません", "専門外")
```

co_view 側の `_BOT_REFUSAL_PATTERNS` (`app.py:3095`) には「こんにちは！」等の挨拶系ノイズが含まれるが、これは co_view (passive listening) 専用要件のため、チャット側はサブセットのみ採用。

### 2. チャットパス書き換え (`app.py:6130-6139`)

差分:

```python
# 通常モード: LLM
await ws.send_json({"type": "status", "text": "考え中..."})
conversation.append({"role": "user", "content": text})
try:
    reply = await chat_with_llm(conversation, model)
except Exception as e:
    conversation.pop()
    await ws.send_json({"type": "assistant_text", "text": f"[LLM エラー: {e}]"})
    continue

# === 追加: refusal 検知 → Claude フォールバック ===
if any(p in reply for p in _CHAT_REFUSAL_PATTERNS) and _tool_route_in_cooldown() <= 0:
    logger.info(f"[chat] local refusal → Claude fallback: '{reply[:50]}'")
    wait_resp = _wait_cache.get_random()
    if wait_resp:
        wait_text, wait_audio = wait_resp
        await ws.send_json({"type": "assistant_text", "text": wait_text})
        await ws.send_bytes(wait_audio)
    claude_reply = await _ask_slack_bot(text, speaker_id)
    if claude_reply:
        reply = claude_reply

conversation.append({"role": "assistant", "content": reply})
# ... 既存 TTS 処理（変更なし）
```

注: ローカル LLM の refusal は `reply` 変数に入るだけで `conversation` には未追記。fallback 成功時は Claude 応答で `reply` が上書きされ、それだけが assistant として履歴に入る（refusal は履歴に残らない）。fallback 失敗時はローカル refusal が assistant として入る — ユーザーが TTS で聞く内容と履歴を一致させる設計判断。

### 3. スコープ外（やらないこと）

- `_always_on_llm_reply` (`app.py:4831-`) は触らない — 既に動作中
- `_TOOL_NEEDED_KEYWORDS` 事前ルーティングのチャット適用 — v2
- `_BOT_REFUSAL_PATTERNS` (co_view 側) との統合 — 要件が違う
- Claude Code CLI 直叩き — 既存 HTTP API で十分
- claude-code-slack-bot 側の `/internal/ask` 改変 — 既存仕様で十分
- 単体テスト — 既存パスにテストが無く、今回も実機検証で確認

## エラーハンドリング

| 状況 | 動作 |
|---|---|
| `_tool_route_in_cooldown()` > 0 | フォールバック skip。ローカル refusal がそのまま返る |
| `_ask_slack_bot()` が None 返す（HTTP失敗・401・cooldown発動など） | ローカル refusal がそのまま返る。`_ask_slack_bot` 内で fail count++ → 既存 cooldown 機構が発動 |
| 401 Auth エラー | `_ask_slack_bot` 内の既存 `_broadcast_session_error` で UI 通知（既存挙動） |
| `_wait_cache.get_random()` が None（未初期化） | wait メッセージ skip、Claude 直接呼ぶ |

## 検証

1. `restart-bot` スキルで voice_chat サーバー再起動
2. EmberChat UI からローカルLLMが断りそうな質問を投げる（例:「明日の天気教えて」「予定を入れて」など `_TOOL_NEEDED_KEYWORDS` に該当する系）
3. ログで以下を確認:
   - `[chat] local refusal → Claude fallback: '...'` が出ること
   - `[tool_route] Slack Bot replied in NNNms` が出ること
   - UI に wait message → Claude reply の順で表示されること
4. claude-code-slack-bot の `/internal/ask` を停止した状態で同じ質問 → fallback fail → ローカル refusal がそのまま返る + cooldown 発動を確認

## ロールバック

変更は `app.py` の 1 ブロック追加 + 1 定数追加のみ。問題があれば該当行を削除すれば元の挙動に戻る。
