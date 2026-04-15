import sys
import types
from unittest import mock

import pytest


for mod_name in [
    "faster_whisper", "faster_whisper.WhisperModel",
    "speechbrain", "speechbrain.inference", "speechbrain.inference.speaker",
    "torch", "torchaudio", "numpy",
    "uvicorn",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

_wm = types.ModuleType("faster_whisper")
_wm.WhisperModel = mock.MagicMock()
sys.modules["faster_whisper"] = _wm

_sb_inf_spk = types.ModuleType("speechbrain.inference.speaker")
_sb_inf_spk.SpeakerRecognition = mock.MagicMock()
sys.modules["speechbrain.inference.speaker"] = _sb_inf_spk
_sb_inf = types.ModuleType("speechbrain.inference")
_sb_inf.speaker = _sb_inf_spk
sys.modules["speechbrain.inference"] = _sb_inf
_sb = types.ModuleType("speechbrain")
_sb.inference = _sb_inf
sys.modules["speechbrain"] = _sb


@pytest.fixture(autouse=True)
def reset_meeting_state():
    import app

    app._media_ctx.reset()
    app._media_ctx.inferred_type = "meeting"
    app._media_ctx.inferred_topic = "定例進捗会議"
    app._media_ctx.confidence = 0.7
    app._media_ctx.keywords = ["進捗", "確認"]
    app._media_ctx.last_meeting_digest_signature = ""
    app._media_ctx.last_meeting_digest_at = 0.0
    app._ambient_listener = object()
    app.SLACK_USER_TOKENS["mei"] = "token"
    app.SLACK_DM_CHANNELS["mei"] = "channel"
    app.MEETING_SUMMARY_TARGET_BOTS = ["mei"]
    yield
    app._media_ctx.reset()
    app._ambient_listener = None


@pytest.mark.asyncio
async def test_format_meeting_digest_message_has_expected_sections():
    import app

    message = app._format_meeting_digest_message(
        meeting_title="週次定例",
        topic="進捗共有",
        payload={
            "summary": "進捗確認と次の作業を整理したよ",
            "minutes": ["A案で進める"],
            "decisions": ["A案で進める"],
            "todos": ["資料更新"],
            "next_actions": ["今日中に共有"],
        },
        transcript="A案で進めることになった",
    )

    assert "*会議メモ*" in message
    assert "*会議名:* 週次定例" in message
    assert "*議事録*" in message
    assert "*決定事項*" in message
    assert "*TODO*" in message
    assert "*NextAction*" in message


@pytest.mark.asyncio
async def test_format_meeting_digest_message_fills_minutes_from_transcript():
    import app

    message = app._format_meeting_digest_message(
        meeting_title="週次定例",
        topic="進捗共有",
        payload={
            "summary": "進捗確認と次の作業を整理したよ",
            "minutes": [],
            "decisions": ["A案で進める"],
            "todos": ["資料更新"],
            "next_actions": ["今日中に共有"],
        },
        transcript="進捗を確認します。A案で進めることで合意しました。資料は今日中に更新します。",
    )

    assert "*議事録*" in message
    assert "進捗を確認します" in message
    assert "A案で進めることで合意しました" in message
    assert "資料は今日中に更新します" in message


@pytest.mark.asyncio
async def test_format_meeting_digest_message_fills_all_sections_from_transcript():
    import app

    message = app._format_meeting_digest_message(
        meeting_title="週次定例",
        topic="進捗共有",
        payload={
            "summary": "進捗確認と次の作業を整理したよ",
            "minutes": [],
            "decisions": [],
            "todos": [],
            "next_actions": [],
        },
        transcript=(
            "進捗を確認します。"
            "A案で進めることで合意しました。"
            "資料は今日中に更新します。"
            "夕方にお客さんへ確認します。"
        ),
    )

    assert "*議事録*" in message
    assert "*決定事項*" in message
    assert "*TODO*" in message
    assert "*NextAction*" in message
    assert "進捗を確認します" in message
    assert "A案で進めることで合意しました" in message
    assert "資料は今日中に更新します" in message
    assert "夕方にお客さんへ確認します" in message


@pytest.mark.asyncio
async def test_maybe_send_meeting_digest_posts_to_slack_once():
    import app

    app._media_ctx.add_snippet("進捗を確認します")
    app._media_ctx.add_snippet("A案で進めることで合意しました")
    app._media_ctx.add_snippet("資料は今日中に更新します")
    app._media_ctx.add_snippet("次回までにTODOを整理します")

    with mock.patch("app._fetch_current_gcal_meeting", return_value="週次定例"), \
         mock.patch("app._generate_meeting_digest", return_value="*会議メモ*\n- 進捗共有"), \
         mock.patch("app.slack_post_message", return_value="123.456") as slack_post:
        await app._maybe_send_meeting_digest()
        await app._maybe_send_meeting_digest()

    assert slack_post.call_count == 1
    assert app._media_ctx.last_meeting_digest_signature
    assert app._media_ctx.last_meeting_digest_at > 0
