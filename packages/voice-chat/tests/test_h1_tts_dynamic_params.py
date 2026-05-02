"""Phase H1: TTS パラメータ動的調整のテスト

app.py の重い依存（numpy 等）を避けるため、ロジックをテスト内で再実装して検証する。
"""
import time
import pytest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# H1 定数（app.py の TTS_MOOD_PARAMS / TTS_TIME_PARAMS と同値を維持すること）
# ---------------------------------------------------------------------------

TTS_MOOD_PARAMS = {
    "excited":  {"speed_delta": +0.05, "intonation_mult": 1.20, "pitch_delta": +0.03},
    "stressed": {"speed_delta": -0.05, "intonation_mult": 0.90, "pitch_delta": -0.02},
    "calm":     {"speed_delta":  0.00, "intonation_mult": 1.00, "pitch_delta":  0.00},
    "focused":  {"speed_delta": -0.03, "intonation_mult": 0.95, "pitch_delta":  0.00},
    "neutral":  {"speed_delta":  0.00, "intonation_mult": 1.00, "pitch_delta":  0.00},
}
TTS_TIME_PARAMS = {
    "morning":   {"speed_delta": +0.03, "intonation_mult": 1.05, "pitch_delta":  0.00},
    "afternoon": {"speed_delta":  0.00, "intonation_mult": 1.00, "pitch_delta":  0.00},
    "evening":   {"speed_delta":  0.00, "intonation_mult": 1.00, "pitch_delta":  0.00},
    "night":     {"speed_delta": -0.08, "intonation_mult": 0.85, "pitch_delta": -0.03},
}
TTS_SPEED_MIN, TTS_SPEED_MAX = 0.5, 2.0
TTS_INTONATION_MIN, TTS_INTONATION_MAX = 0.5, 1.5
TTS_PITCH_MIN, TTS_PITCH_MAX = -0.15, 0.15
TTS_CONTEXT_MIN_CONF = 0.5
CONTEXT_SUMMARY_STALE_SEC = 600


# ---------------------------------------------------------------------------
# Pure-logic helpers that mirror synthesize_speech_voicevox internals
# ---------------------------------------------------------------------------

def _h1_apply_factor(conf: float) -> float:
    """app.py: _h1_apply_factor — linear interpolation for staged firing."""
    if conf >= 0.7:
        return 1.0
    if conf < 0.5:
        return 0.0
    return (conf - 0.5) / 0.2


def _compute_params(
    base_speed: float = 1.0,
    mood: str = "",
    time_context: str = "",
    default_intonation: float = 1.0,
    default_pitch: float = 0.0,
    conf: float = 1.0,
) -> dict:
    """app.py: synthesize_speech_voicevox 内のパラメータ計算ロジックを再現（段階発火対応）"""
    mood_p = TTS_MOOD_PARAMS.get(mood, {})
    time_p = TTS_TIME_PARAMS.get(time_context, {})
    factor = _h1_apply_factor(conf)

    raw_speed_delta = mood_p.get("speed_delta", 0.0) + time_p.get("speed_delta", 0.0)
    raw_intonation_mult = mood_p.get("intonation_mult", 1.0) * time_p.get("intonation_mult", 1.0)
    raw_pitch_delta = mood_p.get("pitch_delta", 0.0) + time_p.get("pitch_delta", 0.0)

    speed_delta = raw_speed_delta * factor
    intonation = default_intonation * (1.0 + (raw_intonation_mult - 1.0) * factor)
    pitch = default_pitch + raw_pitch_delta * factor

    return {
        "speed": max(TTS_SPEED_MIN, min(TTS_SPEED_MAX, base_speed + speed_delta)),
        "intonation": max(TTS_INTONATION_MIN, min(TTS_INTONATION_MAX, intonation)),
        "pitch": max(TTS_PITCH_MIN, min(TTS_PITCH_MAX, pitch)),
    }


def _resolve_tts_context(mood: str, time_context: str, confidence: float, updated_at: float) -> tuple[str, str]:
    """app.py: synthesize_speech 内のコンテキスト解決ロジックを再現"""
    is_stale = updated_at == 0.0 or (time.time() - updated_at) > CONTEXT_SUMMARY_STALE_SEC
    if not is_stale and confidence >= TTS_CONTEXT_MIN_CONF:
        return mood, time_context
    return "", ""


def _make_cache_key(tts_mood: str, tts_time: str, base_speed: float = 1.0, speaker: int = 2, text_hash: str = "abc") -> str:
    return f"voicevox:{speaker}:{base_speed}:{tts_mood}:{tts_time}:{text_hash}"


# ---------------------------------------------------------------------------
# Tests: パラメータ計算ロジック
# ---------------------------------------------------------------------------

class TestTTSMoodParams:
    def test_no_mood_no_time_uses_defaults(self):
        p = _compute_params()
        assert p["speed"] == pytest.approx(1.0)
        assert p["intonation"] == pytest.approx(1.0)
        assert p["pitch"] == pytest.approx(0.0)

    def test_excited_increases_speed_and_intonation(self):
        p = _compute_params(mood="excited")
        assert p["speed"] > 1.0
        assert p["intonation"] > 1.0
        assert p["pitch"] > 0.0

    def test_stressed_decreases_speed_and_intonation(self):
        p = _compute_params(mood="stressed")
        assert p["speed"] < 1.0
        assert p["intonation"] < 1.0
        assert p["pitch"] < 0.0

    def test_focused_slightly_decreases_speed(self):
        p = _compute_params(mood="focused")
        assert p["speed"] < 1.0
        assert p["intonation"] < 1.0

    def test_calm_keeps_defaults(self):
        p = _compute_params(mood="calm")
        assert p["speed"] == pytest.approx(1.0)
        assert p["intonation"] == pytest.approx(1.0)
        assert p["pitch"] == pytest.approx(0.0)

    def test_night_decreases_speed_and_intonation(self):
        p = _compute_params(time_context="night")
        assert p["speed"] < 1.0
        assert p["intonation"] < 1.0
        assert p["pitch"] < 0.0

    def test_morning_increases_speed_slightly(self):
        p = _compute_params(time_context="morning")
        assert p["speed"] > 1.0
        assert p["intonation"] > 1.0

    def test_excited_and_morning_accumulate(self):
        p_excited = _compute_params(mood="excited")
        p_both = _compute_params(mood="excited", time_context="morning")
        assert p_both["speed"] > p_excited["speed"]
        assert p_both["intonation"] > p_excited["intonation"]

    def test_stressed_and_night_accumulate_downward(self):
        p_stressed = _compute_params(mood="stressed")
        p_both = _compute_params(mood="stressed", time_context="night")
        assert p_both["speed"] < p_stressed["speed"]
        assert p_both["intonation"] < p_stressed["intonation"]

    def test_speed_clamp_lower(self):
        p = _compute_params(base_speed=0.5, mood="stressed", time_context="night")
        assert p["speed"] >= TTS_SPEED_MIN

    def test_speed_clamp_upper(self):
        p = _compute_params(base_speed=2.0, mood="excited", time_context="morning")
        assert p["speed"] <= TTS_SPEED_MAX

    def test_intonation_clamp_lower(self):
        p = _compute_params(mood="stressed", time_context="night")
        assert p["intonation"] >= TTS_INTONATION_MIN

    def test_intonation_clamp_upper(self):
        p = _compute_params(mood="excited", time_context="morning")
        assert p["intonation"] <= TTS_INTONATION_MAX

    def test_pitch_clamp_lower(self):
        p = _compute_params(mood="stressed", time_context="night")
        assert p["pitch"] >= TTS_PITCH_MIN

    def test_pitch_clamp_upper(self):
        p = _compute_params(mood="excited")
        assert p["pitch"] <= TTS_PITCH_MAX

    def test_unknown_mood_uses_defaults(self):
        p = _compute_params(mood="unknown_mood")
        assert p["speed"] == pytest.approx(1.0)
        assert p["intonation"] == pytest.approx(1.0)

    def test_unknown_time_context_uses_defaults(self):
        p = _compute_params(time_context="unknown_time")
        assert p["speed"] == pytest.approx(1.0)
        assert p["intonation"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Tests: cache_key の分離（confidence / stale 条件含む）
# ---------------------------------------------------------------------------

class TestCacheKeyIsolation:
    def test_cache_key_differs_by_mood(self):
        k1 = _make_cache_key("excited", "morning")
        k2 = _make_cache_key("stressed", "morning")
        k3 = _make_cache_key("excited", "night")
        assert k1 != k2
        assert k1 != k3
        assert k2 != k3

    def test_cache_key_same_for_same_mood_and_time(self):
        k1 = _make_cache_key("excited", "morning")
        k2 = _make_cache_key("excited", "morning")
        assert k1 == k2

    def test_context_empty_when_low_confidence(self):
        mood, tc = _resolve_tts_context("excited", "morning", confidence=0.4, updated_at=time.time())
        assert mood == ""
        assert tc == ""

    def test_context_empty_at_confidence_boundary(self):
        # 境界値: confidence == TTS_CONTEXT_MIN_CONF - epsilon → 空
        mood, tc = _resolve_tts_context("excited", "morning", confidence=0.499, updated_at=time.time())
        assert mood == ""
        assert tc == ""

    def test_context_used_at_min_confidence(self):
        # 境界値: confidence == TTS_CONTEXT_MIN_CONF → 使用
        mood, tc = _resolve_tts_context("excited", "morning", confidence=0.5, updated_at=time.time())
        assert mood == "excited"
        assert tc == "morning"

    def test_context_used_when_high_confidence(self):
        mood, tc = _resolve_tts_context("stressed", "night", confidence=0.9, updated_at=time.time())
        assert mood == "stressed"
        assert tc == "night"

    def test_context_empty_when_stale(self):
        stale_ts = time.time() - (CONTEXT_SUMMARY_STALE_SEC + 10)
        mood, tc = _resolve_tts_context("excited", "morning", confidence=0.9, updated_at=stale_ts)
        assert mood == ""
        assert tc == ""

    def test_context_empty_when_never_updated(self):
        mood, tc = _resolve_tts_context("excited", "morning", confidence=0.9, updated_at=0.0)
        assert mood == ""
        assert tc == ""

    def test_cache_key_empty_mood_differs_from_nonempty(self):
        k_no_context = _make_cache_key("", "")
        k_with_context = _make_cache_key("excited", "morning")
        assert k_no_context != k_with_context


# ---------------------------------------------------------------------------
# Tests: Phase H1 段階発火 (_h1_apply_factor)
# ---------------------------------------------------------------------------

def _approx(a: float, b: float, abs_tol: float = 1e-6) -> bool:
    return abs(a - b) <= abs_tol


class TestH1ApplyFactor:
    def test_factor_below_05_is_zero(self):
        assert _h1_apply_factor(0.0) == 0.0
        assert _h1_apply_factor(0.4) == 0.0
        assert _h1_apply_factor(0.499) == 0.0

    def test_factor_at_05_is_zero(self):
        assert _h1_apply_factor(0.5) == 0.0

    def test_factor_at_07_is_one(self):
        assert _h1_apply_factor(0.7) == 1.0

    def test_factor_above_07_is_one(self):
        assert _h1_apply_factor(0.8) == 1.0
        assert _h1_apply_factor(1.0) == 1.0

    def test_factor_at_06_is_half(self):
        assert _approx(_h1_apply_factor(0.6), 0.5)

    def test_factor_linear_between_05_and_07(self):
        assert _approx(_h1_apply_factor(0.55), 0.25)
        assert _approx(_h1_apply_factor(0.65), 0.75)


class TestH1StagedFiring:
    """速度・イントネーション・ピッチが confidence に応じて段階的に変わることを検証"""

    def test_conf_05_no_param_change(self):
        """conf=0.5: factor=0 → デフォルトパラメータと同じ"""
        p = _compute_params(mood="excited", time_context="morning", conf=0.5)
        assert _approx(p["speed"], 1.0)
        assert _approx(p["intonation"], 1.0)
        assert _approx(p["pitch"], 0.0)

    def test_conf_07_full_param_change(self):
        """conf=0.7: factor=1 → 完全にパラメータが適用される"""
        p_full = _compute_params(mood="excited", time_context="morning", conf=0.7)
        p_legacy = _compute_params(mood="excited", time_context="morning", conf=1.0)
        assert _approx(p_full["speed"], p_legacy["speed"])
        assert _approx(p_full["intonation"], p_legacy["intonation"])
        assert _approx(p_full["pitch"], p_legacy["pitch"])

    def test_conf_06_half_speed_delta(self):
        """conf=0.6: factor=0.5 → speed_delta が 50% 適用"""
        # excited: speed_delta=+0.05, morning: speed_delta=+0.03 → raw=+0.08
        # factor=0.5 → delta=+0.04 → speed=1.04
        p = _compute_params(mood="excited", time_context="morning", conf=0.6)
        assert _approx(p["speed"], 1.0 + 0.08 * 0.5)

    def test_conf_monotone_increasing(self):
        """confidence が上がるにつれ speed_delta が単調増加する"""
        speeds = [_compute_params(mood="excited", conf=c)["speed"] for c in [0.5, 0.55, 0.6, 0.65, 0.7, 0.8]]
        for i in range(len(speeds) - 1):
            assert speeds[i] <= speeds[i + 1] + 1e-9
