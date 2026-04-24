"""Regression tests for wake-word speaker gating.

背景: 2026-04-19 の実録誤爆
  STT: 'メイ、甲子スケジュール、スケジュールに入れ込んだ' (ambient YouTube audio)
  → wake fired despite non-Akira audio

Root cause: app.py のゲート条件 `audio_duration >= 1.5` が壊れていた。
  audio_duration = len(audio_data) / 32000 は生PCM前提の計算だが、
  実際に流れるのは webm/Opus 圧縮音声。byte 数が小さくなるため、
  ほぼ常に 1.5 未満 → ゲート skip → ambient 音声が wake を通過。

Fix: speaker_id.identify() が返す all_scores の非空性でゲート判定する。
  all_scores 非空 = 識別が実際に走った（≥1.0s 実音声 + プロファイル存在）。
  このときは speaker == "akira" でなければ BLOCK。
"""
import app


class TestSpeakerIdentifiedNotAkira:
    def test_none_result_does_not_block(self):
        """speaker_id 未初期化 / プロファイル未登録 → ゲートスキップ"""
        assert app._speaker_identified_not_akira(None) is False

    def test_empty_all_scores_does_not_block(self):
        """audio 短すぎ / ffmpeg 失敗 → all_scores={} → ゲートスキップ（誤爆より取りこぼし回避）"""
        result = {"speaker": None, "display_name": "", "similarity": 0.0, "all_scores": {}}
        assert app._speaker_identified_not_akira(result) is False

    def test_akira_matched_does_not_block(self):
        """Akira 本人と判定 → PASS"""
        result = {"speaker": "akira", "display_name": "Akira",
                  "similarity": 0.82, "all_scores": {"akira": 0.82}}
        assert app._speaker_identified_not_akira(result) is False

    def test_other_speaker_blocks(self):
        """他人と判定 → BLOCK"""
        result = {"speaker": "bob", "display_name": "Bob",
                  "similarity": 0.71, "all_scores": {"akira": 0.22, "bob": 0.71}}
        assert app._speaker_identified_not_akira(result) is True

    def test_unknown_but_identified_blocks(self):
        """識別実行したが全プロファイル threshold 未満 (= ambient / TV) → BLOCK"""
        result = {"speaker": None, "display_name": "",
                  "similarity": 0.31, "all_scores": {"akira": 0.31}}
        assert app._speaker_identified_not_akira(result) is True

    def test_regression_2026_04_19_ambient_youtube(self):
        """2026-04-19 の実録ケース再現:
        ambient YouTube 音声が Akiraプロファイル閾値 (0.45) 未満でマッチ。
        識別は走った (all_scores 非空) が akira と判定されなかった → BLOCK すべき。
        """
        result = {"speaker": None, "display_name": "",
                  "similarity": 0.28, "all_scores": {"akira": 0.28}}
        assert app._speaker_identified_not_akira(result) is True
