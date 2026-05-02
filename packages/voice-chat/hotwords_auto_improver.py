"""Hotwords auto-improvement loop.

定期的に最近の chunk_transcripts.jsonl から誤認識パターンを LLM 抽出し、
stt_dict_user.json に追記する。

ユーザー承認なしで自動追記するため confidence ゲート（>= 0.7）と
1サイクル追加数上限（5件）、辞書エントリ総数上限（100件）を設ける。

環境変数:
  HOTWORDS_AUTO_DRY_RUN=1 : ファイル書き込みなし、ログのみ
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Awaitable, Any

logger = logging.getLogger("voice_chat")

# ------------------------------------------------------------------ 定数 --
INTERVAL = 1800  # 30 分ごとに実行
WINDOW_SEC = 3600  # 直近 1h の書き起こしを対象
MIN_CONFIDENCE = 0.7  # 候補採用の信頼度閾値
MAX_CANDIDATES_PER_CYCLE = 5  # 1サイクルで追加できる最大件数
MAX_DICT_ENTRIES = 100  # 辞書エントリ総数上限

_CHUNK_FILE = Path(__file__).parent / "chunk_transcripts.jsonl"
_USER_DICT_FILE = Path(__file__).parent / "stt_dict_user.json"

# 既存 _STT_DICT の組み込みエントリー文字列（重複チェック用）
_BUILTIN_REPLACEMENTS = {
    "Claude Code", "ChatGPT", "OpenAI", "Hugging Face", "Anthropic", "Claude",
    "Gemini", "GitHub", "Slack", "Notion", "Shopify", "STORES", "SUZURI",
    "Stripe", "Vercel", "Netlify", "Docker", "Cursor", "Replit", "Codex",
    "LangChain", "Ollama", "Perplexity", "Bedrock", "Vertex AI", "Whisper",
    "Ember", "TypeScript", "JavaScript", "Python", "カレンダー", "プロアクティブ",
    "アンビエント", "WebSocket", "Electron", "Akiraさん",
}

_LLM_SYSTEM_PROMPT = """\
あなたは日本語音声認識の校正専門家です。
以下の音声書き起こしテキスト（Whisper STT の出力）から、
誤認識されている固有名詞・専門用語・ブランド名のパターンを抽出してください。

抽出ルール:
- 片仮名・ひらがなで書かれているが、英語や製品名に見えるもの
- 音韻的に「正しい語」の誤表記に見えるもの
- 既に登録済みのパターン（提示されます）は除外

出力フォーマット: JSON 配列のみを返してください（説明不要）。
各要素の構造:
{
  "incorrect_pattern": "正規表現パターン文字列（re.compile で使用可能）",
  "correct": "正しい表記",
  "confidence": 0.0-1.0,
  "reason": "誤認識と判断した理由（1行）"
}

最大10件まで。confidence が 0.7 未満のものは含めないでください。
JSON 配列以外のテキストは出力しないでください。
"""


# ------------------------------------------------------------------ I/O --

async def collect_recent_transcripts(window_sec: int = WINDOW_SEC) -> list[str]:
    """chunk_transcripts.jsonl の直近 window_sec 秒分のテキストを返す。"""
    if not _CHUNK_FILE.exists():
        logger.debug("[hotwords] chunk_transcripts.jsonl not found, skip")
        return []

    now_ts = datetime.now(tz=timezone.utc).timestamp()
    cutoff = now_ts - window_sec
    texts: list[str] = []

    try:
        lines = _CHUNK_FILE.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        logger.warning(f"[hotwords] failed to read chunk_transcripts.jsonl: {e}")
        return []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        # ts_end フィールド優先、なければ ts をパース
        ts_end = entry.get("ts_end")
        if ts_end is None:
            ts_str = entry.get("ts", "")
            if not ts_str:
                continue
            try:
                from datetime import timezone as _tz
                dt = datetime.fromisoformat(ts_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_tz.utc)
                ts_end = dt.timestamp()
            except Exception:
                continue
        if ts_end < cutoff:
            continue
        text = entry.get("text", "").strip()
        if text:
            texts.append(text)

    logger.info(f"[hotwords] collected {len(texts)} recent transcripts (window={window_sec}s)")
    return texts


def _get_existing_patterns() -> tuple[list[str], list[dict]]:
    """現在の user dict の (パターン文字列リスト, エントリリスト) を返す。"""
    if not _USER_DICT_FILE.exists():
        return [], []
    try:
        entries: list[dict] = json.loads(_USER_DICT_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[hotwords] failed to read user dict: {e}")
        return [], []
    patterns: list[str] = []
    for entry in entries:
        patterns.extend(entry.get("patterns", []))
        patterns.append(entry.get("replacement", ""))
    return patterns, entries


async def extract_hotword_candidates(
    transcripts: list[str],
    existing_patterns: list[str],
    chat_with_llm_fn: Callable[[list[dict], str], Awaitable[str]],
) -> list[dict]:
    """LLM を呼び出して誤認識候補を抽出する。confidence >= MIN_CONFIDENCE のみ返す。"""
    if not transcripts:
        logger.info("[hotwords] no transcripts to analyze")
        return []

    # テキストを結合（長すぎる場合は末尾を切る）
    combined = "\n".join(transcripts)
    if len(combined) > 8000:
        combined = combined[-8000:]

    all_existing = list(_BUILTIN_REPLACEMENTS) + existing_patterns
    existing_block = "登録済みパターン（除外）:\n" + "\n".join(f"- {p}" for p in all_existing[:80])

    user_content = f"{existing_block}\n\n音声書き起こし:\n{combined}"

    messages = [
        {"role": "system", "content": _LLM_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        raw = await asyncio.wait_for(
            chat_with_llm_fn(messages, "gemma4:e4b"),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        logger.warning("[hotwords] LLM call timed out")
        return []
    except Exception as e:
        logger.warning(f"[hotwords] LLM call failed: {e}")
        return []

    # JSON 配列を抽出
    raw = raw.strip()
    # LLM がコードブロックで包むことがある
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    try:
        candidates: list[dict] = json.loads(raw)
        if not isinstance(candidates, list):
            raise ValueError("not a list")
    except Exception as e:
        logger.warning(f"[hotwords] failed to parse LLM response as JSON: {e} | raw={raw[:200]}")
        return []

    # フィルタリング
    valid: list[dict] = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        incorrect = c.get("incorrect_pattern", "")
        correct = c.get("correct", "")
        confidence = float(c.get("confidence", 0.0))
        if not incorrect or not correct:
            continue
        if confidence < MIN_CONFIDENCE:
            continue
        # 正規表現の検証
        try:
            re.compile(incorrect)
        except re.error:
            logger.warning(f"[hotwords] invalid regex skipped: {incorrect!r}")
            continue
        # 組み込み辞書との重複チェック
        if correct in _BUILTIN_REPLACEMENTS:
            logger.debug(f"[hotwords] skip builtin duplicate: {correct}")
            continue
        valid.append({
            "incorrect_pattern": incorrect,
            "correct": correct,
            "confidence": confidence,
            "reason": c.get("reason", ""),
        })

    logger.info(f"[hotwords] extracted {len(valid)} valid candidates from LLM")
    return valid


def merge_into_user_dict(candidates: list[dict], dict_file: Path = _USER_DICT_FILE) -> int:
    """candidates を stt_dict_user.json にマージする。

    - 同じ correct text を持つ既存エントリに patterns を追加（OR 結合）
    - 新規 correct text は新エントリとして追加
    - 個数上限 MAX_DICT_ENTRIES を超えたら古いエントリを削除
    - 戻り値: 実際に追加されたパターン件数
    """
    dry_run = os.environ.get("HOTWORDS_AUTO_DRY_RUN", "0") == "1"

    # 既存エントリをロード
    if dict_file.exists():
        try:
            entries: list[dict] = json.loads(dict_file.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    else:
        entries = []

    # correct → entry index マップ
    correct_to_idx: dict[str, int] = {}
    for i, entry in enumerate(entries):
        r = entry.get("replacement", "")
        if r:
            correct_to_idx[r] = i

    # 既存の全パターン（重複防止）
    existing_pattern_set: set[str] = set()
    for entry in entries:
        for p in entry.get("patterns", []):
            existing_pattern_set.add(p)

    added = 0
    for c in candidates:
        incorrect = c["incorrect_pattern"]
        correct = c["correct"]

        # 既存エントリに同一 correct があればパターン追記
        if correct in correct_to_idx:
            idx = correct_to_idx[correct]
            existing_pats = entries[idx].setdefault("patterns", [])
            if incorrect not in existing_pattern_set:
                existing_pats.append(incorrect)
                existing_pattern_set.add(incorrect)
                added += 1
                logger.info(f"[hotwords] append pattern to '{correct}': {incorrect!r}")
        else:
            # 新エントリ
            if incorrect in existing_pattern_set:
                continue
            new_entry = {
                "id": uuid.uuid4().hex[:12],
                "replacement": correct,
                "patterns": [incorrect],
                "type": "auto",
                "added_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "confidence": c.get("confidence", 0.0),
                "reason": c.get("reason", ""),
            }
            entries.append(new_entry)
            correct_to_idx[correct] = len(entries) - 1
            existing_pattern_set.add(incorrect)
            added += 1
            logger.info(f"[hotwords] new entry: '{correct}' ← {incorrect!r}")

    # 上限超え: 古い auto エントリを削除
    if len(entries) > MAX_DICT_ENTRIES:
        auto_indices = [
            i for i, e in enumerate(entries)
            if e.get("type") == "auto"
        ]
        remove_count = len(entries) - MAX_DICT_ENTRIES
        for i in sorted(auto_indices[:remove_count], reverse=True):
            removed = entries.pop(i)
            logger.info(f"[hotwords] evicted old entry: '{removed.get('replacement')}'")

    if dry_run:
        logger.info(f"[hotwords] DRY_RUN: would write {len(entries)} entries, added={added}")
    else:
        dict_file.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info(f"[hotwords] saved dict ({len(entries)} entries, +{added} this cycle)")

    return added


# ------------------------------------------------------------------ Loop --

async def auto_improve_loop(
    chat_with_llm_fn: Callable[[list[dict], str], Awaitable[str]],
    settings_getter: Callable[[], dict] | None = None,
) -> None:
    """30 分ごとに hotwords 自動改善を実行するバックグラウンドループ。

    settings_getter: 最新 _settings を返す callable。
                     hotwordsAutoImprovementDisabled=true で無効化。
    """
    logger.info("[hotwords] auto_improve_loop started (interval=1800s)")
    await asyncio.sleep(60)  # 起動直後の負荷を避けて 1 分後に初回実行

    while True:
        try:
            # 無効化チェック
            if settings_getter is not None:
                settings = settings_getter()
                if settings.get("hotwordsAutoImprovementDisabled", False):
                    logger.debug("[hotwords] disabled via settings, skip cycle")
                    await asyncio.sleep(INTERVAL)
                    continue

            transcripts = await collect_recent_transcripts()
            if not transcripts:
                logger.info("[hotwords] no recent transcripts, skip cycle")
                await asyncio.sleep(INTERVAL)
                continue

            existing_patterns, _ = _get_existing_patterns()
            candidates = await extract_hotword_candidates(
                transcripts, existing_patterns, chat_with_llm_fn
            )

            # 1 サイクル上限
            candidates = candidates[:MAX_CANDIDATES_PER_CYCLE]

            if candidates:
                added = merge_into_user_dict(candidates)
                if added > 0:
                    logger.info(f"[hotwords] cycle complete: +{added} entries added to user dict")
            else:
                logger.info("[hotwords] cycle complete: no new candidates")

        except asyncio.CancelledError:
            logger.info("[hotwords] auto_improve_loop cancelled")
            return
        except Exception as e:
            logger.warning(f"[hotwords] unexpected error in loop: {e}", exc_info=True)

        await asyncio.sleep(INTERVAL)
