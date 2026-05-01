"""Regression tests for Whisper prompt-echo detection.

背景: 2026-04-19 の実録誤爆
  STT: 'メイ、甲子スケジュール、スケジュールに入れ込んだ'
  → initial_prompt="ねぇメイ、メイ、今日のスケジュールは？" による幻覚。
    "スケジュール" 関連発話で "メイ、" 先頭幻覚 + "スケジュール" 重複。

Fix:
  1. initial_prompt を廃止し、hotwords="メイ" のみで語彙バイアス。
  2. _looks_like_initial_prompt_echo に "メイ + スケジュール重複" 検出を追加
     （過去の蓄積学習分 + 残留バイアスに対する safety net）。
"""
import app


class TestLegacyPromptEchoStillBlocked:
    def test_exact_prompt_echo(self):
        assert app._looks_like_initial_prompt_echo("メイ、今日のスケジュールは？") is True

    def test_duplicated_name_echo(self):
        assert app._looks_like_initial_prompt_echo("メイメイ今日のスケジュールは") is True

    def test_nee_prefix_echo(self):
        assert app._looks_like_initial_prompt_echo("ねぇメイメイ今日のスケジュールは？") is True


class TestRegression20260419:
    def test_duplicated_schedule_with_mei_prefix_blocked(self):
        """実録: STT 'メイ、甲子スケジュール、スケジュールに入れ込んだ' が prompt-echo 判定される"""
        text = "メイ、甲子スケジュール、スケジュールに入れ込んだ"
        assert app._looks_like_initial_prompt_echo(text) is True

    def test_mei_prefix_single_schedule_not_blocked(self):
        """正常: 'メイ、スケジュール教えて' は 'スケジュール' 1回のみ → prompt-echo 判定されない"""
        text = "メイ、スケジュール教えて"
        assert app._looks_like_initial_prompt_echo(text) is False

    def test_no_mei_prefix_not_blocked(self):
        """'メイ' 始まりでない限り prompt-echo 判定しない（co-view等の通常発話保護）"""
        text = "明日のスケジュールとスケジュール調整の件"
        assert app._looks_like_initial_prompt_echo(text) is False


class TestPromptRemoved:
    def test_hotwords_is_mei_only(self):
        """旧verbose prompt を撤去し、hotwords="メイ" のみであることを確認"""
        assert app._WHISPER_HOTWORDS == "メイ"

    def test_no_schedule_in_hotwords(self):
        """"スケジュール" が含まれないこと（幻覚源を混入しない）"""
        assert "スケジュール" not in app._WHISPER_HOTWORDS
