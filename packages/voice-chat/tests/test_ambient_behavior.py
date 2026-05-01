import re

from ambient_policy import normalize_ambient_reply, should_apply_stt_correction


INSTRUCTION_PATTERN = re.compile(
    r"(してください|を確認して|を調べて|を教えて|を開いて|を消して|を送って"
    r"|作り替えて|変更して|修正して|立ち上げて|実行して|作成して|まとめて|揃えて"
    r"|のせて|追加して|削除して|更新して|書いて|書き換えて|コミットして"
    r"|設定して|フィルター.*して|表示して|非表示.*して|読み込んで"
    r"|[てで]ください$|ます$"
    r"|(?:設定|ファイル|コード|関数|変数|API|CSS|HTML|パス|ディレクトリ|データベース|サーバー|エンドポイント|ブランド|ロゴ|デザイン|カレンダー|アカウント|ダッシュボード).*(?:どこ|どう|どれ|何|なに|ですか|ますか)"
    r"|(?:どこに|どうやって|どうすれば).*(?:ますか|ですか|する|した))",
)


class TestAmbientBehaviorHelpers:
    def test_should_apply_stt_correction_for_identified_speaker(self):
        assert should_apply_stt_correction(
            "ちょっと相談したいことがある",
            speaker_identified=True,
            wake_detected=False,
            in_conversation=False,
            instruction_pattern=INSTRUCTION_PATTERN,
        ) is True

    def test_should_skip_stt_correction_for_low_confidence_short_ambient_text(self):
        assert should_apply_stt_correction(
            "すご",
            speaker_identified=False,
            wake_detected=False,
            in_conversation=False,
            instruction_pattern=INSTRUCTION_PATTERN,
        ) is False

    def test_should_apply_stt_correction_for_clear_question_without_wake_word(self):
        assert should_apply_stt_correction(
            "今日の予定どうすればいいですか？",
            speaker_identified=False,
            wake_detected=False,
            in_conversation=False,
            instruction_pattern=INSTRUCTION_PATTERN,
        ) is True

    def test_normalize_ambient_reply_recognizes_skip(self):
        assert normalize_ambient_reply("SKIP", emoji_replacer=lambda text, replace="": text) == ("skip", "")

    def test_normalize_ambient_reply_extracts_backchannel(self):
        assert normalize_ambient_reply("BACKCHANNEL: うんうん", emoji_replacer=lambda text, replace="": text) == ("backchannel", "うんうん")

    def test_normalize_ambient_reply_treats_plain_text_as_reply(self):
        assert normalize_ambient_reply("それは大変だったね", emoji_replacer=lambda text, replace="": text) == ("reply", "それは大変だったね")
