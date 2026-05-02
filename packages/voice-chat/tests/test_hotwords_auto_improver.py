"""Unit tests for hotwords_auto_improver.py"""
import asyncio
import json
import os
import sys
import time
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock
import unittest.mock as mock

import pytest

# voice-chat ディレクトリを sys.path に追加
_VOICE_CHAT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_VOICE_CHAT_DIR))

from hotwords_auto_improver import (
    collect_recent_transcripts,
    extract_hotword_candidates,
    merge_into_user_dict,
    MIN_CONFIDENCE,
    MAX_CANDIDATES_PER_CYCLE,
    MAX_DICT_ENTRIES,
)


# ------------------------------------------------------------------ helpers --

def run(coro):
    """asyncio.run のラッパー（Python 3.14 互換）。"""
    return asyncio.run(coro)


# ------------------------------------------------------------------ fixtures --

@pytest.fixture()
def tmp_dict_file(tmp_path: Path) -> Path:
    """空の stt_dict_user.json を一時ディレクトリに作成。"""
    f = tmp_path / "stt_dict_user.json"
    f.write_text("[]", encoding="utf-8")
    return f


@pytest.fixture()
def tmp_chunk_file(tmp_path: Path) -> Path:
    """直近のダミー書き起こし JSONL を一時ファイルに作成。"""
    now = time.time()
    entries = [
        {"ts_end": now - 100, "text": "スマートAIグラスは使いやすいですね"},
        {"ts_end": now - 200, "text": "キュウちゃんモデルで処理しました"},
        {"ts_end": now - 7200, "text": "これは 1 時間以上前の古いデータです"},  # 範囲外
    ]
    f = tmp_path / "chunk_transcripts.jsonl"
    f.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries), encoding="utf-8")
    return f


# ------------------------------------------------------------------ TestCollectRecentTranscripts --

class TestCollectRecentTranscripts:
    def test_returns_only_recent(self, tmp_chunk_file: Path, monkeypatch):
        """window 内のエントリだけ返す。"""
        import hotwords_auto_improver as m
        monkeypatch.setattr(m, "_CHUNK_FILE", tmp_chunk_file)

        result = run(collect_recent_transcripts(window_sec=3600))
        assert len(result) == 2
        assert any("スマートAIグラス" in t for t in result)
        assert all("古いデータ" not in t for t in result)

    def test_missing_file_returns_empty(self, monkeypatch):
        """ファイルが存在しない場合は空リスト。"""
        import hotwords_auto_improver as m
        monkeypatch.setattr(m, "_CHUNK_FILE", Path("/nonexistent/path.jsonl"))

        result = run(collect_recent_transcripts())
        assert result == []


# ------------------------------------------------------------------ TestExtractHotwordCandidates --

class TestExtractHotwordCandidates:
    def test_filters_low_confidence(self):
        """confidence < MIN_CONFIDENCE の候補は除外される。"""
        llm_response = json.dumps([
            {
                "incorrect_pattern": "スマートAIグラス",
                "correct": "SmartAI Glass",
                "confidence": 0.9,
                "reason": "英語製品名の誤認識",
            },
            {
                "incorrect_pattern": "キュウちゃんモデル",
                "correct": "Q-chan Model",
                "confidence": 0.4,  # 閾値以下
                "reason": "低確信度",
            },
        ])

        async def mock_llm(messages, model):
            return llm_response

        result = run(
            extract_hotword_candidates(
                ["スマートAIグラスは使いやすい", "キュウちゃんモデルで処理"],
                [],
                mock_llm,
            )
        )
        assert len(result) == 1
        assert result[0]["correct"] == "SmartAI Glass"

    def test_rejects_invalid_regex(self):
        """不正な正規表現はスキップされる。"""
        llm_response = json.dumps([
            {
                "incorrect_pattern": "[invalid(",  # 不正
                "correct": "Valid",
                "confidence": 0.95,
                "reason": "invalid regex",
            },
        ])

        async def mock_llm(messages, model):
            return llm_response

        result = run(extract_hotword_candidates(["テスト"], [], mock_llm))
        assert result == []

    def test_handles_llm_codeblock_wrapping(self):
        """LLM がコードブロックで包んだ場合も正しくパース。"""
        candidates = [
            {
                "incorrect_pattern": "スマートプラス",
                "correct": "SmartPlus",
                "confidence": 0.85,
                "reason": "製品名",
            }
        ]
        llm_response = f"```json\n{json.dumps(candidates)}\n```"

        async def mock_llm(messages, model):
            return llm_response

        result = run(extract_hotword_candidates(["スマートプラスを購入した"], [], mock_llm))
        assert len(result) == 1
        assert result[0]["correct"] == "SmartPlus"

    def test_skips_builtin_replacements(self):
        """組み込み辞書の correct text と重複する候補はスキップ。"""
        llm_response = json.dumps([
            {
                "incorrect_pattern": "クロード",
                "correct": "Claude",  # 組み込み済み
                "confidence": 0.95,
                "reason": "builtin duplicate",
            },
        ])

        async def mock_llm(messages, model):
            return llm_response

        result = run(extract_hotword_candidates(["クロードはすごい"], [], mock_llm))
        assert result == []

    def test_empty_transcripts_returns_empty(self):
        """書き起こしが空のとき LLM を呼ばない。"""
        call_count = 0

        async def counting_llm(messages, model):
            nonlocal call_count
            call_count += 1
            return "[]"

        result = run(extract_hotword_candidates([], [], counting_llm))
        assert result == []
        assert call_count == 0

    def test_llm_timeout_returns_empty(self):
        """LLM がタイムアウトしても空リストを返す（例外伝播しない）。"""
        import hotwords_auto_improver as m

        async def fast_timeout(coro, timeout):
            raise asyncio.TimeoutError()

        async def run_with_mock():
            with mock.patch.object(m.asyncio, "wait_for", fast_timeout):
                return await extract_hotword_candidates(["テスト"], [], AsyncMock())

        result = run(run_with_mock())
        assert result == []


# ------------------------------------------------------------------ TestMergeIntoUserDict --

class TestMergeIntoUserDict:
    def test_adds_new_entry(self, tmp_dict_file: Path):
        """新規 correct → 新エントリを追加する。"""
        candidates = [
            {
                "incorrect_pattern": "スマートAIグラス",
                "correct": "SmartAI Glass",
                "confidence": 0.9,
                "reason": "test",
            }
        ]
        added = merge_into_user_dict(candidates, tmp_dict_file)
        assert added == 1

        entries = json.loads(tmp_dict_file.read_text())
        assert len(entries) == 1
        assert entries[0]["replacement"] == "SmartAI Glass"
        assert "スマートAIグラス" in entries[0]["patterns"]
        assert entries[0]["type"] == "auto"

    def test_appends_pattern_to_existing(self, tmp_dict_file: Path):
        """既存の correct に別パターンを追記する。"""
        existing = [
            {
                "id": "abc123",
                "replacement": "SmartAI Glass",
                "patterns": ["スマートAI"],
                "type": "auto",
                "added_at": "2026-01-01T00:00:00",
            }
        ]
        tmp_dict_file.write_text(json.dumps(existing, ensure_ascii=False))

        candidates = [
            {
                "incorrect_pattern": "スマートAIグラス",
                "correct": "SmartAI Glass",
                "confidence": 0.85,
                "reason": "test",
            }
        ]
        added = merge_into_user_dict(candidates, tmp_dict_file)
        assert added == 1

        entries = json.loads(tmp_dict_file.read_text())
        assert len(entries) == 1
        assert "スマートAIグラス" in entries[0]["patterns"]
        assert "スマートAI" in entries[0]["patterns"]

    def test_no_duplicate_patterns(self, tmp_dict_file: Path):
        """同じパターンを二重追加しない。"""
        candidates = [
            {
                "incorrect_pattern": "スマートAIグラス",
                "correct": "SmartAI Glass",
                "confidence": 0.9,
                "reason": "test",
            }
        ] * 2  # 同じ候補を 2 回

        added = merge_into_user_dict(candidates, tmp_dict_file)
        assert added == 1  # 最初の 1 件だけ追加

        entries = json.loads(tmp_dict_file.read_text())
        assert entries[0]["patterns"].count("スマートAIグラス") == 1

    def test_evicts_old_auto_entries_over_limit(self, tmp_dict_file: Path):
        """MAX_DICT_ENTRIES を超えたら古い auto エントリを削除。"""
        old_entries = [
            {
                "id": f"id{i:04d}",
                "replacement": f"Word{i}",
                "patterns": [f"pattern{i}"],
                "type": "auto",
                "added_at": "2026-01-01T00:00:00",
            }
            for i in range(MAX_DICT_ENTRIES)
        ]
        tmp_dict_file.write_text(json.dumps(old_entries, ensure_ascii=False))

        candidates = [
            {
                "incorrect_pattern": "newpattern",
                "correct": "NewWord",
                "confidence": 0.9,
                "reason": "test",
            }
        ]
        merge_into_user_dict(candidates, tmp_dict_file)

        entries = json.loads(tmp_dict_file.read_text())
        assert len(entries) == MAX_DICT_ENTRIES

    def test_dry_run_does_not_write(self, tmp_dict_file: Path, monkeypatch):
        """HOTWORDS_AUTO_DRY_RUN=1 の場合ファイルを書き換えない。"""
        monkeypatch.setenv("HOTWORDS_AUTO_DRY_RUN", "1")
        original_content = tmp_dict_file.read_text()

        candidates = [
            {
                "incorrect_pattern": "テストパターン",
                "correct": "TestWord",
                "confidence": 0.9,
                "reason": "dry run test",
            }
        ]
        added = merge_into_user_dict(candidates, tmp_dict_file)
        assert added == 1  # 戻り値は正常

        # ファイルは変更されていない
        assert tmp_dict_file.read_text() == original_content
