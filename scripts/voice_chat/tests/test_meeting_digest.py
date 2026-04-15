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
    app._meeting_digest_batch_task = None
    app._meeting_digest_idle_task = None
    app.SLACK_USER_TOKENS["mei"] = "token"
    app.SLACK_BOT_TOKENS["mei"] = "bot-token"
    app.SLACK_DM_CHANNELS["mei"] = "channel"
    app.MEETING_SUMMARY_TARGET_BOTS = ["mei"]
    yield
    app._media_ctx.reset()
    app._ambient_listener = None
    app._meeting_digest_batch_task = None
    app._meeting_digest_idle_task = None


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
async def test_meeting_digest_batch_accumulates_transcript():
    import app

    app._media_ctx.add_snippet("進捗を確認します")
    app._media_ctx.add_snippet("A案で進めることで合意しました")
    app._media_ctx.add_snippet("資料は今日中に更新します")
    app._media_ctx.add_snippet("夕方にお客さんへ確認します")

    sig1 = app._start_or_update_meeting_digest_batch()
    assert sig1
    first_transcript = app._media_ctx.meeting_digest_pending_transcript
    assert "A案で進めることで合意しました" in first_transcript

    app._media_ctx.add_snippet("次回までにTODOを整理します")
    sig2 = app._start_or_update_meeting_digest_batch()
    assert sig2
    assert app._media_ctx.meeting_digest_pending_signature == sig2
    assert "次回までにTODOを整理します" in app._media_ctx.meeting_digest_pending_transcript
    assert len(app._media_ctx.meeting_digest_pending_transcript) >= len(first_transcript)


@pytest.mark.asyncio
async def test_maybe_send_meeting_digest_posts_to_slack_once():
    import app

    app._media_ctx.add_snippet("進捗を確認します")
    app._media_ctx.add_snippet("A案で進めることで合意しました")
    app._media_ctx.add_snippet("資料は今日中に更新します")
    app._media_ctx.add_snippet("次回までにTODOを整理します")

    with mock.patch("app._fetch_current_gcal_meeting", return_value="週次定例"), \
         mock.patch("app._generate_meeting_digest", return_value="*会議メモ*\n- 進捗共有"), \
         mock.patch("app.slack_post_channel_message", return_value="123.456") as slack_post:
        await app._maybe_send_meeting_digest()
        await app._maybe_send_meeting_digest()

    assert slack_post.call_count == 1
    assert slack_post.call_args[0][0] == "mei"
    assert slack_post.call_args[0][1].startswith("<@U3SFGQXNH> ")
    assert "*会議メモ*" in slack_post.call_args[0][1]
    assert slack_post.call_args[0][2] == app.SLACK_MEETING_SUMMARY_CHANNEL
    assert app._media_ctx.last_meeting_digest_signature
    assert app._media_ctx.last_meeting_digest_at > 0


@pytest.mark.asyncio
async def test_maybe_send_meeting_digest_force_posts_after_meeting_end():
    import app

    app._media_ctx.meeting_digest_pending_signature = "digest-1"
    app._media_ctx.meeting_digest_pending_title = "週次定例"
    app._media_ctx.meeting_digest_pending_topic = "進捗共有"
    app._media_ctx.meeting_digest_pending_transcript = (
        "進捗を確認します。\n"
        "A案で進めることで合意しました。\n"
        "資料は今日中に更新します。\n"
        "夕方にお客さんへ確認します。"
    )
    app._media_ctx.meeting_digest_pending_keywords = ["進捗", "確認"]
    app._media_ctx.meeting_digest_pending_at = 0.0

    with mock.patch("app._resolve_meeting_summary_bot_id", return_value="mei"), \
         mock.patch("app.slack_post_channel_message", return_value="123.456") as slack_post:
        await app._maybe_send_meeting_digest(force=True)

    assert slack_post.call_count == 1
    assert slack_post.call_args[0][0] == "mei"
    assert slack_post.call_args[0][1].startswith("<@U3SFGQXNH> ")
    assert "*議事録*" in slack_post.call_args[0][1]
    assert "A案で進めることで合意しました" in slack_post.call_args[0][1]
    assert slack_post.call_args[0][2] == app.SLACK_MEETING_SUMMARY_CHANNEL
    assert app._media_ctx.last_meeting_digest_signature == "digest-1"
