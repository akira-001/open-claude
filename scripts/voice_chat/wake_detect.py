"""Wake word detection from transcribed text."""
import re
from dataclasses import dataclass


@dataclass
class WakeWordResult:
    detected: bool
    keyword: str = ""
    remaining_text: str = ""


_WAKE_PATTERNS = [
    re.compile(r'^(?:ねぇ|ねえ|ねー|ね)\s*メイ[、,。．.\s]*(.*)$', re.DOTALL),
    re.compile(r'^メイ[、,。．.\s]+(.*)$', re.DOTALL),
    re.compile(r'^メイ$'),
    re.compile(r'^(?:ねぇ|ねえ|ねー|ね)\s*[Mm]ei[、,。．.\s]*(.*)$', re.DOTALL | re.IGNORECASE),
    re.compile(r'^[Mm]ei[、,。．.\s]+(.*)$', re.DOTALL | re.IGNORECASE),
    re.compile(r'^[Mm]ei$', re.IGNORECASE),
]


def detect_wake_word(text: str) -> WakeWordResult:
    text = text.strip()
    if not text:
        return WakeWordResult(detected=False)

    for pattern in _WAKE_PATTERNS:
        m = pattern.match(text)
        if m:
            remaining = m.group(1).strip() if m.lastindex and m.lastindex >= 1 else ""
            return WakeWordResult(detected=True, keyword="メイ", remaining_text=remaining)

    return WakeWordResult(detected=False)
