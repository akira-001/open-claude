from wake_detect import detect_wake_word, WakeWordResult


class TestDetectWakeWord:
    def test_detects_nei_mei(self):
        result = detect_wake_word("ねぇメイ、今日の予定教えて")
        assert result.detected is True
        assert result.keyword == "メイ"
        assert result.remaining_text == "今日の予定教えて"

    def test_detects_mei_alone(self):
        result = detect_wake_word("メイ")
        assert result.detected is True
        assert result.keyword == "メイ"
        assert result.remaining_text == ""

    def test_detects_mei_with_comma(self):
        result = detect_wake_word("メイ、これ見て")
        assert result.detected is True
        assert result.remaining_text == "これ見て"

    def test_detects_katakana_nei_mei(self):
        result = detect_wake_word("ねえメイ、天気は？")
        assert result.detected is True

    def test_ignores_mei_in_middle_of_sentence(self):
        """文頭にない「メイ」は呼びかけではない"""
        result = detect_wake_word("今日はメイちゃんに聞いてみよう")
        assert result.detected is False

    def test_ignores_unrelated_text(self):
        result = detect_wake_word("今日の天気はどう？")
        assert result.detected is False

    def test_empty_text(self):
        result = detect_wake_word("")
        assert result.detected is False

    def test_detects_hey_mei_romaji(self):
        result = detect_wake_word("Mei、調べて")
        assert result.detected is True
        assert result.remaining_text == "調べて"
