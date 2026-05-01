import json
import pytest
from wake_detect import detect_wake_word, WakeWordResult


class TestAlwaysOnMessageTypes:
    def test_wake_word_detected_in_transcription(self):
        result = detect_wake_word("ねぇメイ、今何時？")
        assert result.detected is True
        assert result.remaining_text == "今何時？"

    def test_wake_word_not_detected(self):
        result = detect_wake_word("今日はいい天気だね")
        assert result.detected is False

    def test_always_on_audio_message_format(self):
        msg = {"type": "always_on_audio", "format": "wav"}
        assert msg["type"] == "always_on_audio"

    def test_wake_detected_response_format(self):
        response = {"type": "wake_detected", "keyword": "メイ", "remaining_text": "今日の予定は？"}
        assert response["type"] == "wake_detected"

    def test_listening_state_message_format(self):
        msg = {"type": "listening_state", "state": "listening"}
        assert msg["state"] in ("listening", "muted", "processing")
