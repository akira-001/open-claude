import json
import pytest
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from ambient_listener import AmbientListener, REACTIVITY_CONFIG


class TestReactivityConfig:
    def test_all_levels_defined(self):
        for level in range(1, 6):
            assert level in REACTIVITY_CONFIG

    def test_level_3_is_default(self):
        cfg = REACTIVITY_CONFIG[3]
        assert cfg["batch_interval_sec"] == 30
        assert cfg["keyword_ratio"] == 1.0

    def test_higher_level_shorter_interval(self):
        # Level 1 (静か) has batch_interval_sec=0 meaning disabled, not "shortest".
        # Among active levels (2-5), higher level means shorter interval.
        assert REACTIVITY_CONFIG[5]["batch_interval_sec"] < REACTIVITY_CONFIG[2]["batch_interval_sec"]


class TestAmbientListener:
    @pytest.fixture
    def rules_file(self, tmp_path):
        f = tmp_path / "ambient_rules.json"
        f.write_text(json.dumps({
            "rules": [{"id": "r001", "text": "テストルール", "enabled": True, "source": "test", "created_at": "2026-01-01T00:00:00"}],
            "keywords": [{"id": "k001", "category": "weather", "pattern": "天気|雨", "enabled": True}],
        }))
        return f

    @pytest.fixture
    def examples_file(self, tmp_path):
        f = tmp_path / "ambient_examples.json"
        f.write_text(json.dumps({
            "examples": [{"id": "e001", "context": "TVで天気予報", "response": "傘いるかも", "rating": "positive", "created_at": "2026-01-01T00:00:00"}],
        }))
        return f

    @pytest.fixture
    def listener(self, rules_file, examples_file):
        return AmbientListener(rules_path=rules_file, examples_path=examples_file, reactivity=3)

    def test_initial_state(self, listener):
        assert listener.reactivity == 3
        assert listener.override_level is None
        assert listener.state == "idle"
        assert len(listener.rules["keywords"]) == 1

    def test_set_reactivity_clamps(self, listener):
        listener.set_reactivity(7)
        assert listener.reactivity == 5
        listener.set_reactivity(-1)
        assert listener.reactivity == 1

    def test_override_sets_timer(self, listener):
        listener.apply_override(level_delta=-2, duration_sec=60)
        assert listener.override_level == 1  # 3 - 2 = 1
        assert listener.override_expires_at > time.time()

    def test_override_clamps_to_min_1(self, listener):
        listener.set_reactivity(1)
        listener.apply_override(level_delta=-2, duration_sec=60)
        assert listener.override_level == 1  # min is 1

    def test_effective_reactivity_uses_override(self, listener):
        listener.apply_override(level_delta=-2, duration_sec=60)
        assert listener.effective_reactivity == 1

    def test_effective_reactivity_after_expiry(self, listener):
        listener.apply_override(level_delta=-2, duration_sec=0)
        listener.override_expires_at = time.time() - 1  # expired
        assert listener.effective_reactivity == 3  # back to base

    def test_keyword_match(self, listener):
        result = listener.check_keywords("今日の天気はどうかな")
        assert result is not None
        assert result["category"] == "weather"

    def test_keyword_no_match(self, listener):
        result = listener.check_keywords("プログラミングの話")
        assert result is None

    def test_keyword_disabled(self, listener):
        listener.rules["keywords"][0]["enabled"] = False
        listener._compile_keywords()
        result = listener.check_keywords("天気の話")
        assert result is None

    def test_cooldown_blocks_same_category(self, listener):
        listener.check_keywords("天気の話")  # first match
        listener.record_cooldown("weather")
        result = listener.check_keywords("雨が降りそう")
        assert result is None  # blocked by cooldown

    def test_add_text_to_buffer(self, listener):
        listener.add_to_buffer("テスト1")
        listener.add_to_buffer("テスト2")
        assert len(listener.text_buffer) == 2

    def test_add_text_to_buffer_filters_duplicates(self, listener):
        assert listener.add_to_buffer("テスト1") is True
        assert listener.add_to_buffer("テスト1") is False
        assert listener.last_buffer_reject_reason == "repeat"

    def test_flush_buffer(self, listener):
        listener.add_to_buffer("テスト1")
        listener.add_to_buffer("テスト2")
        texts = listener.flush_buffer()
        assert len(texts) == 2
        assert len(listener.text_buffer) == 0

    def test_add_rule(self, listener):
        rule = listener.add_rule("新しいルール", source="explicit")
        assert rule["id"].startswith("r")
        assert len(listener.rules["rules"]) == 2

    def test_remove_rule(self, listener):
        listener.remove_rule("r001")
        assert len(listener.rules["rules"]) == 0

    def test_toggle_rule(self, listener):
        listener.toggle_rule("r001", enabled=False)
        assert listener.rules["rules"][0]["enabled"] is False

    def test_add_example(self, listener):
        ex = listener.add_example("状況", "反応", "positive")
        assert ex["id"].startswith("e")
        assert len(listener.examples["examples"]) == 2

    def test_remove_example(self, listener):
        listener.remove_example("e001")
        assert len(listener.examples["examples"]) == 0

    def test_get_stats(self, listener):
        stats = listener.get_stats()
        assert "judgments_today" in stats
        assert "speaks_today" in stats
        assert "speak_rate" in stats

    def test_record_judgment_updates_stats(self, listener):
        listener.record_judgment(method="keyword", result="speak")
        listener.record_judgment(method="keyword", result="skip")
        stats = listener.get_stats()
        assert stats["judgments_today"] == 2
        assert stats["speaks_today"] == 1

    def test_build_llm_prompt(self, listener):
        listener.add_to_buffer("天気予報やってるね")
        listener.add_to_buffer("明日は雨らしい")
        prompt = listener.build_llm_prompt()
        assert "リアクティビティレベル" in prompt
        assert "天気予報やってるね" in prompt
        assert "テストルール" in prompt

    def test_get_state_snapshot(self, listener):
        listener.record_judgment(method="keyword", result="speak", intervention="backchannel", source_hint="user_likely")
        snap = listener.get_state_snapshot()
        assert snap["reactivity"] == 3
        assert snap["override"] is None
        assert snap["listener_state"] == "idle"
        assert snap["last_judgment"]["intervention"] == "backchannel"
        assert snap["last_judgment"]["source_hint"] == "user_likely"

    def test_classify_source_marks_short_noise_as_fragmentary(self, listener):
        assert listener.classify_source("カタ") == "fragmentary"

    def test_classify_source_prefers_user_identified(self, listener):
        listener.current_speaker = "Akira"
        assert listener.classify_source("ちょっと疲れた") == "user_identified"

    def test_decide_intervention_skips_fragmentary(self, listener):
        assert listener.decide_intervention("カタ", "fragmentary") == "skip"

    def test_decide_intervention_uses_backchannel_for_uncertain_user_likely(self, listener):
        assert listener.decide_intervention("疲れたなあ", "user_likely") == "backchannel"

    def test_decide_intervention_uses_reply_for_clear_user_question(self, listener):
        assert listener.decide_intervention("今日の予定どうしようかな？", "user_likely") == "reply"

    def test_decide_intervention_skips_multi_speaker_without_direct_call(self, listener):
        assert listener.decide_intervention("それでさ", "user_in_conversation") == "skip"

    def test_decide_intervention_backchannels_multi_speaker_with_direct_call(self, listener):
        assert listener.decide_intervention("メイそれわかる？", "user_in_conversation") == "backchannel"

    def test_chotto_alone_does_not_promote_to_user_initiative(self, listener):
        # 'ちょっと' は USER_CALL_RE から除外。Whisper誤認識の偽呼びかけを防ぐ。
        # speaker未識別かつ Mei直前発話なしの状態で 'ちょっと...' 系が来ても
        # user_initiative には昇格しない（reply に直行しない）。
        text = "ちょっといけると言うかも 待ちてばっかり お疲れ様でした"
        source = listener.classify_source(text)
        assert source != "user_initiative"
        assert listener.decide_intervention(text, source) != "reply"

    def test_weak_call_without_name_downgrades_to_user_likely(self, listener):
        # 'ねえ' 単体は声紋未識別だと user_likely に格下げ。
        # 短文かつ質問形でないので backchannel 止まり、reply にはならない。
        source = listener.classify_source("ねえ、ちょっと")
        assert source == "user_likely"
        assert listener.decide_intervention("ねえ、ちょっと", source) == "backchannel"

    def test_explicit_name_call_keeps_user_initiative_without_speaker_id(self, listener):
        # 明示的な「メイ」呼びかけは声紋なしでも user_initiative を維持。
        # 名前は Whisper 幻聴で出にくい強いシグナルなので reply 確定でよい。
        source = listener.classify_source("メイ、おはよう。")
        assert source == "user_initiative"
        assert listener.decide_intervention("メイ、おはよう。", source) == "reply"


class FakeContextSummary:
    """ContextSummary の最小モック（H3テスト用）。"""
    def __init__(self, *, is_meeting=False, activity="", mood="", confidence=0.8, stale=False):
        self.is_meeting = is_meeting
        self.activity = activity
        self.mood = mood
        self.confidence = confidence
        self._stale = stale

    def is_stale(self):
        return self._stale


class TestDecideInterventionH3:
    """Phase H3: Ambient 静粛ルールのテスト。"""

    @pytest.fixture
    def listener(self, tmp_path):
        rules_file = tmp_path / "rules.json"
        examples_file = tmp_path / "examples.json"
        rules_file.write_text('{"rules": [], "keywords": []}')
        examples_file.write_text('{"examples": []}')
        return AmbientListener(rules_path=rules_file, examples_path=examples_file, reactivity=3)

    def test_is_meeting_high_confidence_returns_backchannel(self, listener):
        ctx = FakeContextSummary(is_meeting=True, confidence=0.7)
        result = listener.decide_intervention("それで次のアジェンダは", "user_identified", ctx)
        assert result == "backchannel"

    def test_is_meeting_low_confidence_not_suppressed(self, listener):
        # confidence < 0.5 では会議判定でも抑制しない（誤判定保護）
        ctx = FakeContextSummary(is_meeting=True, confidence=0.4)
        result = listener.decide_intervention("メイ、おはよう。", "user_initiative", ctx)
        assert result == "reply"

    def test_is_meeting_exactly_at_threshold_suppresses(self, listener):
        ctx = FakeContextSummary(is_meeting=True, confidence=0.5)
        result = listener.decide_intervention("どう思う？", "user_likely", ctx)
        assert result == "backchannel"

    def test_activity_idle_high_confidence_skips(self, listener):
        ctx = FakeContextSummary(activity="idle", confidence=0.7)
        result = listener.decide_intervention("ちょっと疲れた", "user_likely", ctx)
        assert result == "skip"

    def test_activity_idle_at_threshold_suppressed(self, listener):
        ctx = FakeContextSummary(activity="idle", confidence=0.5)
        result = listener.decide_intervention("ちょっと疲れた", "user_likely", ctx)
        assert result == "skip"

    def test_activity_idle_below_threshold_not_suppressed(self, listener):
        ctx = FakeContextSummary(activity="idle", confidence=0.4)
        result = listener.decide_intervention("今日の天気どうかな", "user_likely", ctx)
        # confidence が低いので抑制されず通常判定（user_likely + 質問形 → reply）
        assert result == "reply"

    def test_mood_stressed_downgrades_reply_to_backchannel(self, listener):
        ctx = FakeContextSummary(mood="stressed", confidence=0.8)
        result = listener.decide_intervention("メイ、おはよう。", "user_initiative", ctx)
        assert result == "backchannel"

    def test_mood_stressed_at_threshold_downgrades(self, listener):
        ctx = FakeContextSummary(mood="stressed", confidence=0.5)
        result = listener.decide_intervention("メイ、おはよう。", "user_initiative", ctx)
        assert result == "backchannel"

    def test_mood_stressed_below_threshold_keeps_reply(self, listener):
        ctx = FakeContextSummary(mood="stressed", confidence=0.4)
        result = listener.decide_intervention("メイ、おはよう。", "user_initiative", ctx)
        assert result == "reply"

    def test_stale_context_summary_ignored(self, listener):
        ctx = FakeContextSummary(is_meeting=True, confidence=0.9, stale=True)
        result = listener.decide_intervention("メイ、おはよう。", "user_initiative", ctx)
        # stale なので H3 ルールが適用されず reply のまま
        assert result == "reply"

    def test_no_context_summary_keeps_original_behavior(self, listener):
        result = listener.decide_intervention("メイ、おはよう。", "user_initiative")
        assert result == "reply"

    def test_meeting_suppression_takes_priority_over_mood(self, listener):
        # is_meeting かつ mood=stressed でも is_meeting が先にヒットして backchannel
        ctx = FakeContextSummary(is_meeting=True, mood="stressed", confidence=0.8)
        result = listener.decide_intervention("どう？", "user_identified", ctx)
        assert result == "backchannel"


class TestDecideInterventionK3:
    """Phase K3: 会議補助モード（reactivity=5 + is_meeting）のテスト。"""

    @pytest.fixture
    def listener_level5(self, tmp_path):
        rules_file = tmp_path / "rules.json"
        examples_file = tmp_path / "examples.json"
        rules_file.write_text('{"rules": [], "keywords": []}')
        examples_file.write_text('{"examples": []}')
        return AmbientListener(rules_path=rules_file, examples_path=examples_file, reactivity=5)

    @pytest.fixture
    def listener_level4(self, tmp_path):
        rules_file = tmp_path / "rules.json"
        examples_file = tmp_path / "examples.json"
        rules_file.write_text('{"rules": [], "keywords": []}')
        examples_file.write_text('{"examples": []}')
        return AmbientListener(rules_path=rules_file, examples_path=examples_file, reactivity=4)

    def test_reactivity5_meeting_true_returns_meeting_assist(self, listener_level5):
        ctx = FakeContextSummary(is_meeting=True, confidence=0.7)
        result = listener_level5.decide_intervention("それで次のアジェンダは", "user_identified", ctx)
        assert result == "meeting_assist"

    def test_reactivity4_meeting_true_returns_backchannel(self, listener_level4):
        # H3 維持: reactivity=4 は引き続き backchannel に降格
        ctx = FakeContextSummary(is_meeting=True, confidence=0.7)
        result = listener_level4.decide_intervention("それで次のアジェンダは", "user_identified", ctx)
        assert result == "backchannel"

    def test_reactivity5_meeting_false_returns_reply(self, listener_level5):
        ctx = FakeContextSummary(is_meeting=False, confidence=0.7)
        result = listener_level5.decide_intervention("メイ、今日どう？", "user_initiative", ctx)
        assert result == "reply"

    def test_reactivity5_meeting_true_low_conf_not_meeting_assist(self, listener_level5):
        # confidence < 0.5 では meeting_assist に昇格しない
        ctx = FakeContextSummary(is_meeting=True, confidence=0.4)
        result = listener_level5.decide_intervention("メイ、おはよう。", "user_initiative", ctx)
        assert result == "reply"

    def test_build_llm_prompt_meeting_assist_mode_contains_instruction(self, listener_level5, tmp_path):
        prompt = listener_level5.build_llm_prompt(source_hint="user_identified", mode="meeting_assist")
        assert "会議補助モード" in prompt

    def test_build_llm_prompt_normal_mode_no_meeting_assist_block(self, listener_level5, tmp_path):
        prompt = listener_level5.build_llm_prompt(source_hint="user_identified", mode="normal")
        assert "会議補助モード" not in prompt

    def test_build_llm_prompt_default_mode_no_meeting_assist_block(self, listener_level5, tmp_path):
        prompt = listener_level5.build_llm_prompt(source_hint="user_identified")
        assert "会議補助モード" not in prompt
