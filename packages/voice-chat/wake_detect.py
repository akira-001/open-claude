"""Wake word detection from transcribed text."""
import re
from dataclasses import dataclass


@dataclass
class WakeWordResult:
    detected: bool
    keyword: str = ""
    remaining_text: str = ""


_WAKE_PATTERNS = [
    # Standard patterns
    re.compile(r'^(?:ねぇ|ねえ|ねー|ね)[、,\s]*メイ[、,。．.\s]*(.*)$', re.DOTALL),
    re.compile(r'^メイ[、,。．.\s]+(.*)$', re.DOTALL),
    re.compile(r'^メイ[、,。．.\s]*$'),
    # No separator (e.g. "メイ聞こえる?") but avoid common non-wake words like "メイン"
    re.compile(r'^メイ(?!ン|ド|ク|カ|カー)([^\s、,。．.].+)$', re.DOTALL),
    # Romaji
    re.compile(r'^(?:ねぇ|ねえ|ねー|ね)[、,\s]*[Mm]ei[、,。．.\s]*(.*)$', re.DOTALL | re.IGNORECASE),
    re.compile(r'^[Mm]ei[、,。．.\s]+(.*)$', re.DOTALL | re.IGNORECASE),
    re.compile(r'^[Mm]ei[、,。．.\s]*$', re.IGNORECASE),
    # Common Whisper misrecognitions of "ねぇメイ"
    re.compile(r'^ねえねえ[、,。．.\s]*(.*)$', re.DOTALL),
    re.compile(r'^ねえ[、,\s]*めい[、,。．.\s]*(.*)$', re.DOTALL),
    re.compile(r'^ねぇ[、,\s]*めい[、,。．.\s]*(.*)$', re.DOTALL),
    re.compile(r'^ね[ぇえー][、,\s]*目[、,。．.\s]*(.*)$', re.DOTALL),
]

_FALSE_WAKE_PREFIX = re.compile(
    r'^(メイン|メイド|メイク|メイカー|メイプル|明治|名医)',
    re.IGNORECASE,
)


def detect_wake_word(text: str) -> WakeWordResult:
    text = text.strip()
    # Strip leading symbols that Whisper sometimes prepends (※, ♪, *, etc.)
    text = re.sub(r'^[※♪♫★☆●○◆◇■□▲△▼▽*#→←↑↓・]+\s*', '', text)
    if not text:
        return WakeWordResult(detected=False)
    if _FALSE_WAKE_PREFIX.match(text):
        return WakeWordResult(detected=False)

    for pattern in _WAKE_PATTERNS:
        m = pattern.match(text)
        if m:
            remaining = m.group(1).strip() if m.lastindex and m.lastindex >= 1 else ""
            return WakeWordResult(detected=True, keyword="メイ", remaining_text=remaining)

    return WakeWordResult(detected=False)
