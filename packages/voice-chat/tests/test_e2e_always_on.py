"""
E2E integration test for Always-On flow.
Tests the full pipeline: audio bytes → Whisper STT → wake word detect → response
"""
import pytest
from unittest.mock import AsyncMock, patch
from wake_detect import detect_wake_word
from wake_response import WakeResponseCache


class TestE2EAlwaysOnFlow:
    @pytest.mark.asyncio
    async def test_full_wake_word_flow(self, mock_synthesize):
        """Whisper結果 → wake word検出 → レスポンス取得の一連フロー"""
        # 1. Whisper がテキストを返す（モック）
        transcribed = "ねぇメイ、今日のスケジュール教えて"

        # 2. Wake word 検出
        result = detect_wake_word(transcribed)
        assert result.detected is True
        assert result.remaining_text == "今日のスケジュール教えて"

        # 3. ウェイクレスポンスキャッシュから取得
        cache = WakeResponseCache()
        with patch("wake_response.synthesize_speech", new_callable=AsyncMock, return_value=mock_synthesize):
            await cache.warmup(speaker_id="2", speed=1.0)

        resp = cache.get_random()
        assert resp is not None
        text, audio = resp
        assert isinstance(audio, bytes)
        assert len(audio) > 44

    @pytest.mark.asyncio
    async def test_non_wake_word_is_ignored(self):
        """ウェイクワードのない音声は無視される"""
        transcribed = "明日の天気はどうかな"
        result = detect_wake_word(transcribed)
        assert result.detected is False

    @pytest.mark.asyncio
    async def test_wake_word_only_returns_response_only(self, mock_synthesize):
        """「メイ」だけの呼びかけ → レスポンスのみ（LLMに渡さない）"""
        result = detect_wake_word("メイ")
        assert result.detected is True
        assert result.remaining_text == ""

        cache = WakeResponseCache()
        with patch("wake_response.synthesize_speech", new_callable=AsyncMock, return_value=mock_synthesize):
            await cache.warmup(speaker_id="2", speed=1.0)

        resp = cache.get_random()
        assert resp is not None
