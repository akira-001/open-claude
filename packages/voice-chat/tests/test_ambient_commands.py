import pytest
from ambient_commands import detect_ambient_command, AmbientCommand


class TestDetectAmbientCommand:
    def test_stop_japanese(self):
        result = detect_ambient_command("やめて")
        assert result.type == "stop"

    def test_stop_english(self):
        result = detect_ambient_command("Stop")
        assert result.type == "stop"

    def test_stop_katakana(self):
        result = detect_ambient_command("ストップ")
        assert result.type == "stop"

    def test_quiet_down(self):
        result = detect_ambient_command("静かにして")
        assert result.type == "quiet"
        assert result.level_delta == -2
        assert result.duration_sec == 900

    def test_noisy(self):
        result = detect_ambient_command("うるさい")
        assert result.type == "quiet"
        assert result.level_delta == -1
        assert result.duration_sec == 600

    def test_talk_more(self):
        result = detect_ambient_command("もっと話して")
        assert result.type == "talk_more"
        assert result.level_delta == 1
        assert result.duration_sec == 900

    def test_talk_kakete(self):
        result = detect_ambient_command("話しかけて")
        assert result.type == "talk_more"
        assert result.level_delta == 1

    def test_shut_up(self):
        result = detect_ambient_command("黙って")
        assert result.type == "quiet"
        assert result.level_delta == -2

    def test_no_command(self):
        result = detect_ambient_command("今日はいい天気だね")
        assert result.type == "none"

    def test_empty_text(self):
        result = detect_ambient_command("")
        assert result.type == "none"

    def test_stop_has_highest_priority(self):
        """Stop が他のコマンドより優先されること"""
        result = detect_ambient_command("やめて静かにして")
        assert result.type == "stop"
