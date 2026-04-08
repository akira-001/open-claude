import pytest
from unittest.mock import AsyncMock, patch
from wake_response import WakeResponseCache


RESPONSES = ["はい、何でしょう？", "なに？", "はい", "何かあった？", "聞いてるよ"]


class TestWakeResponseCache:
    @pytest.mark.asyncio
    async def test_warmup_generates_all_responses(self, mock_synthesize):
        cache = WakeResponseCache(responses=RESPONSES)
        with patch("wake_response.synthesize_speech", new_callable=AsyncMock, return_value=mock_synthesize):
            await cache.warmup(speaker_id="irodori-lora-emilia", speed=0)
        assert len(cache._cache) == len(RESPONSES)

    @pytest.mark.asyncio
    async def test_get_random_returns_audio(self, mock_synthesize):
        cache = WakeResponseCache(responses=RESPONSES)
        with patch("wake_response.synthesize_speech", new_callable=AsyncMock, return_value=mock_synthesize):
            await cache.warmup(speaker_id="irodori-lora-emilia", speed=0)
        text, audio = cache.get_random()
        assert text in RESPONSES
        assert isinstance(audio, bytes)
        assert len(audio) > 44

    @pytest.mark.asyncio
    async def test_get_random_before_warmup_returns_none(self):
        cache = WakeResponseCache(responses=RESPONSES)
        result = cache.get_random()
        assert result is None

    @pytest.mark.asyncio
    async def test_warmup_handles_tts_failure(self, mock_synthesize):
        cache = WakeResponseCache(responses=RESPONSES)
        call_count = 0

        async def flaky_tts(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                raise Exception("TTS failed")
            return mock_synthesize

        with patch("wake_response.synthesize_speech", side_effect=flaky_tts):
            await cache.warmup(speaker_id="2", speed=1.0)
        assert len(cache._cache) == 4

    def test_is_ready(self):
        cache = WakeResponseCache(responses=RESPONSES)
        assert cache.is_ready is False
