"""Pre-cached TTS responses for instant wake word acknowledgment."""
import logging
import random
from typing import Callable, Awaitable

logger = logging.getLogger("voice_chat")


# Default synthesize function — set at runtime by app.py
synthesize_speech: Callable[..., Awaitable[bytes]] | None = None


DEFAULT_RESPONSES = [
    "はい、何でしょう？",
    "なに？",
    "はい",
    "何かあった？",
    "聞いてるよ",
]


class WakeResponseCache:
    def __init__(self, responses: list[str] | None = None):
        self._responses = responses or DEFAULT_RESPONSES
        self._cache: dict[str, bytes] = {}

    @property
    def is_ready(self) -> bool:
        return len(self._cache) > 0

    async def warmup(self, speaker_id: str | int, speed: float) -> None:
        for text in self._responses:
            try:
                audio = await synthesize_speech(text, speaker_id, speed)
                self._cache[text] = audio
                logger.info(f"[WakeResponseCache] cached: '{text}' ({len(audio)} bytes)")
            except Exception as e:
                logger.warning(f"[WakeResponseCache] failed to cache '{text}': {e}")

    def get_random(self) -> tuple[str, bytes] | None:
        if not self._cache:
            return None
        text = random.choice(list(self._cache.keys()))
        return text, self._cache[text]
