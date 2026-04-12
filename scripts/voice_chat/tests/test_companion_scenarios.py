import json
import pytest

from ambient_listener import AmbientListener


@pytest.fixture
def listener(tmp_path):
    rules_file = tmp_path / "ambient_rules.json"
    rules_file.write_text(json.dumps({
        "rules": [],
        "keywords": [
            {"id": "k001", "category": "weather", "pattern": "天気|雨", "enabled": True},
            {"id": "k002", "category": "emotion", "pattern": "疲れた|しんどい", "enabled": True},
        ],
    }))
    examples_file = tmp_path / "ambient_examples.json"
    examples_file.write_text(json.dumps({"examples": []}))
    return AmbientListener(rules_path=rules_file, examples_path=examples_file, reactivity=3)


class TestCompanionScenarios:
    def test_keyboard_like_fragment_is_skipped(self, listener):
        source = listener.classify_source("カタ")
        assert source == "fragmentary"
        assert listener.decide_intervention("カタ", source) == "skip"

    def test_short_monologue_prefers_backchannel(self, listener):
        source = listener.classify_source("疲れたなあ")
        assert source == "user_likely"
        assert listener.decide_intervention("疲れたなあ", source) == "backchannel"

    def test_clear_question_without_name_can_still_reply(self, listener):
        source = listener.classify_source("今日の予定どうしようかな？")
        assert source == "user_likely"
        assert listener.decide_intervention("今日の予定どうしようかな？", source) == "reply"

    def test_identified_user_question_replies_without_wake_word(self, listener):
        listener.current_speaker = "Akira"
        source = listener.classify_source("このあと何からやろうかな？")
        assert source == "user_identified"
        assert listener.decide_intervention("このあと何からやろうかな？", source) == "reply"

    def test_media_like_phrase_is_skipped(self, listener):
        source = listener.classify_source("この動画をご視聴いただきありがとうございました")
        assert source == "media_likely"
        assert listener.decide_intervention("この動画をご視聴いただきありがとうございました", source) == "skip"

    def test_multi_party_conversation_avoids_full_reply(self, listener):
        listener.record_speaker("Akira")
        listener.record_speaker("同僚")
        listener.current_speaker = "Akira"
        source = listener.classify_source("それでさ、明日の件どうする？")
        assert source == "user_in_conversation"
        assert listener.decide_intervention("それでさ、明日の件どうする？", source) == "skip"

    def test_multi_party_direct_call_allows_backchannel(self, listener):
        listener.record_speaker("Akira")
        listener.record_speaker("同僚")
        listener.current_speaker = "Akira"
        source = listener.classify_source("メイそれどう思う？")
        assert source == "user_in_conversation"
        assert listener.decide_intervention("メイそれどう思う？", source) == "backchannel"
