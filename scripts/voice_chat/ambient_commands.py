"""Ambient voice command detection — Stop, mode control, barge-in triggers."""
import re
from dataclasses import dataclass


@dataclass
class AmbientCommand:
    type: str  # "stop", "quiet", "talk_more", "none"
    level_delta: int = 0
    duration_sec: int = 0


# Priority order: stop > quiet/talk_more
_STOP_PATTERNS = [
    re.compile(r'(?:やめて|止めて|ストップ|とめて)', re.IGNORECASE),
    re.compile(r'\b[Ss]top\b'),
]

_QUIET_PATTERNS = [
    # -2 level, 15 min
    (re.compile(r'(?:静かにして|黙って|しずかにして|だまって)'), -2, 900),
    # -1 level, 10 min
    (re.compile(r'(?:うるさい|うっさい)'), -1, 600),
]

_TALK_MORE_PATTERNS = [
    (re.compile(r'(?:もっと話して|話しかけて|しゃべって|もっとしゃべって)'), 1, 900),
]


def detect_ambient_command(text: str) -> AmbientCommand:
    text = text.strip()
    if not text:
        return AmbientCommand(type="none")

    # Stop has highest priority
    for pattern in _STOP_PATTERNS:
        if pattern.search(text):
            return AmbientCommand(type="stop")

    for pattern, delta, duration in _QUIET_PATTERNS:
        if pattern.search(text):
            return AmbientCommand(type="quiet", level_delta=delta, duration_sec=duration)

    for pattern, delta, duration in _TALK_MORE_PATTERNS:
        if pattern.search(text):
            return AmbientCommand(type="talk_more", level_delta=delta, duration_sec=duration)

    return AmbientCommand(type="none")
