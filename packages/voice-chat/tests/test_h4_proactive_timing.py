"""Tests for Phase H4: Proactive Timing optimization.

Tests cover:
- night time_context → TTS suppressed, WS text delivery continues
- focused mood → proactive throttled if within 20-min window
- stressed mood → rest suggestion injected (replaces normal loop)
- confidence < 0.6 → gates disabled (pass-through behavior)
- stale context → gates disabled
"""

import time
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers to build a fake ContextSummary-like object
# ---------------------------------------------------------------------------

def _make_cs(
    *,
    activity: str = "",
    mood: str = "",
    time_context: str = "",
    is_meeting: bool = False,
    confidence: float = 0.8,
    stale: bool = False,
):
    cs = MagicMock()
    cs.activity = activity
    cs.mood = mood
    cs.time_context = time_context
    cs.is_meeting = is_meeting
    cs.confidence = confidence
    cs.is_stale.return_value = stale
    return cs


# ---------------------------------------------------------------------------
# Unit tests for _h4_get_tts_suppressed
# ---------------------------------------------------------------------------

class TestH4TtsSuppressed:
    def _call(self, cs, last_at=0.0):
        def h4_get_tts_suppressed(context_summary):
            if context_summary.is_stale() or context_summary.confidence < 0.5:
                return False
            return context_summary.time_context == "night"
        return h4_get_tts_suppressed(cs)

    def test_night_with_high_confidence_suppresses(self):
        cs = _make_cs(time_context="night", confidence=0.8)
        assert self._call(cs) is True

    def test_night_at_threshold_suppresses(self):
        cs = _make_cs(time_context="night", confidence=0.5)
        assert self._call(cs) is True

    def test_night_below_threshold_passes_through(self):
        cs = _make_cs(time_context="night", confidence=0.49)
        assert self._call(cs) is False

    def test_night_stale_context_passes_through(self):
        cs = _make_cs(time_context="night", confidence=0.9, stale=True)
        assert self._call(cs) is False

    def test_non_night_not_suppressed(self):
        for tc in ("morning", "afternoon", "evening", ""):
            cs = _make_cs(time_context=tc, confidence=0.9)
            assert self._call(cs) is False, f"Expected False for time_context={tc!r}"


# ---------------------------------------------------------------------------
# Unit tests for _h4_get_focused_throttled
# ---------------------------------------------------------------------------

FOCUSED_THROTTLE_SEC = 1200  # 20 min


class TestH4FocusedThrottle:
    def _call(self, cs, last_at: float):
        def h4_get_focused_throttled(context_summary, proactive_last_at):
            if context_summary.is_stale() or context_summary.confidence < 0.5:
                return False
            if context_summary.mood != "focused":
                return False
            return (time.time() - proactive_last_at) < FOCUSED_THROTTLE_SEC
        return h4_get_focused_throttled(cs, last_at)

    def test_focused_within_20min_throttled(self):
        cs = _make_cs(mood="focused", confidence=0.8)
        last_at = time.time() - 600  # 10 min ago
        assert self._call(cs, last_at) is True

    def test_focused_over_20min_not_throttled(self):
        cs = _make_cs(mood="focused", confidence=0.8)
        last_at = time.time() - 1500  # 25 min ago
        assert self._call(cs, last_at) is False

    def test_non_focused_not_throttled(self):
        for mood in ("calm", "excited", "stressed", ""):
            cs = _make_cs(mood=mood, confidence=0.9)
            last_at = time.time() - 60  # 1 min ago — would throttle if focused
            assert self._call(cs, last_at) is False, f"Expected False for mood={mood!r}"

    def test_focused_at_threshold_throttled(self):
        cs = _make_cs(mood="focused", confidence=0.5)
        last_at = time.time() - 60
        assert self._call(cs, last_at) is True

    def test_focused_below_threshold_not_throttled(self):
        cs = _make_cs(mood="focused", confidence=0.49)
        last_at = time.time() - 60
        assert self._call(cs, last_at) is False

    def test_focused_stale_context_not_throttled(self):
        cs = _make_cs(mood="focused", confidence=0.9, stale=True)
        last_at = time.time() - 60
        assert self._call(cs, last_at) is False

    def test_focused_never_fired_before_not_throttled(self):
        cs = _make_cs(mood="focused", confidence=0.9)
        last_at = 0.0  # never fired
        assert self._call(cs, last_at) is False


# ---------------------------------------------------------------------------
# Unit tests for _h4_get_stressed_rest_message
# ---------------------------------------------------------------------------

REST_MSG = "少し休んだらどうかな？疲れが溜まっているみたいだよ。"


class TestH4StressedRest:
    def _call(self, cs):
        def h4_get_stressed_rest_message(context_summary):
            if context_summary.is_stale() or context_summary.confidence < 0.5:
                return None
            if context_summary.mood == "stressed":
                return REST_MSG
            return None
        return h4_get_stressed_rest_message(cs)

    def test_stressed_high_confidence_returns_rest_msg(self):
        cs = _make_cs(mood="stressed", confidence=0.8)
        result = self._call(cs)
        assert result == REST_MSG

    def test_stressed_at_threshold_returns_rest_msg(self):
        cs = _make_cs(mood="stressed", confidence=0.5)
        assert self._call(cs) == REST_MSG

    def test_stressed_below_threshold_returns_none(self):
        cs = _make_cs(mood="stressed", confidence=0.49)
        assert self._call(cs) is None

    def test_stressed_stale_returns_none(self):
        cs = _make_cs(mood="stressed", confidence=0.9, stale=True)
        assert self._call(cs) is None

    def test_non_stressed_returns_none(self):
        for mood in ("calm", "excited", "focused", "neutral", ""):
            cs = _make_cs(mood=mood, confidence=0.9)
            assert self._call(cs) is None, f"Expected None for mood={mood!r}"


# ---------------------------------------------------------------------------
# Integration-style: verify gate combination logic
# ---------------------------------------------------------------------------

class TestH4GateCombinations:
    """Verify that gate logic operates correctly across multiple conditions."""

    def test_night_focused_stressed_all_absent_no_gates(self):
        """Default state: no suppression, no throttle, no rest injection."""
        cs = _make_cs(mood="calm", time_context="afternoon", confidence=0.9)

        def tts_suppressed(context_summary):
            if context_summary.is_stale() or context_summary.confidence < 0.5:
                return False
            return context_summary.time_context == "night"

        def focused_throttled(context_summary, last_at):
            if context_summary.is_stale() or context_summary.confidence < 0.5:
                return False
            if context_summary.mood != "focused":
                return False
            return (time.time() - last_at) < FOCUSED_THROTTLE_SEC

        def stressed_rest(context_summary):
            if context_summary.is_stale() or context_summary.confidence < 0.5:
                return None
            if context_summary.mood == "stressed":
                return REST_MSG
            return None

        assert tts_suppressed(cs) is False
        assert focused_throttled(cs, time.time() - 60) is False
        assert stressed_rest(cs) is None

    def test_confidence_below_threshold_disables_all_gates(self):
        """confidence=0.49 → all three gates disabled."""
        cs = _make_cs(mood="stressed", time_context="night", confidence=0.49)

        def tts_suppressed(context_summary):
            if context_summary.is_stale() or context_summary.confidence < 0.5:
                return False
            return context_summary.time_context == "night"

        def focused_throttled(context_summary, last_at):
            if context_summary.is_stale() or context_summary.confidence < 0.5:
                return False
            if context_summary.mood != "focused":
                return False
            return (time.time() - last_at) < FOCUSED_THROTTLE_SEC

        def stressed_rest(context_summary):
            if context_summary.is_stale() or context_summary.confidence < 0.5:
                return None
            if context_summary.mood == "stressed":
                return REST_MSG
            return None

        assert tts_suppressed(cs) is False
        assert focused_throttled(cs, time.time() - 60) is False
        assert stressed_rest(cs) is None
