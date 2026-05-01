from types import SimpleNamespace
from unittest import mock

import pytest

import app


def test_normalize_text_signature_collapses_spacing_and_punctuation():
    assert app._normalize_text_signature("  進捗、確認！  ") == "進捗確認"


def test_dedupe_texts_for_batch_removes_duplicate_snippets():
    assert app._dedupe_texts_for_batch(["進捗確認", "進捗確認", "TODO確認"]) == ["進捗確認", "TODO確認"]


def test_low_value_backchannel_detection_distinguishes_short_acknowledgements():
    assert app._is_low_value_backchannel_text("うんうん") is True
    assert app._is_low_value_backchannel_text("次回までに資料を整理して共有するね") is False


def test_meeting_hint_score_rewards_calendar_and_meeting_language():
    score, reasons = app._meeting_hint_details(
        "進捗を共有します。決定事項は次回までに整理します。",
        gcal_title="週次定例",
        keywords=["進捗", "確認"],
    )
    assert score >= 6
    assert any(reason.startswith("gcal:") for reason in reasons)
    assert any(reason.startswith("text:") for reason in reasons)


def test_should_promote_to_meeting_accepts_strong_meeting_context():
    assert app._should_promote_to_meeting(
        "youtube_talk",
        0.52,
        "進捗を共有します。決定事項は次回までに整理します。",
        gcal_title="週次定例",
        keywords=["進捗", "確認"],
    ) is True


@pytest.mark.asyncio
async def test_infer_media_content_promotes_meeting_from_calendar_and_phrases():
    app._media_ctx.reset()
    app._media_ctx.add_snippet("進捗を共有します")
    app._media_ctx.add_snippet("決定事項は明日確認します")
    app._media_ctx.add_snippet("次回までにTODOを整理します")

    with mock.patch("app.chat_with_llm", return_value='{"content_type":"youtube_talk","topic":"雑談","matched_title":"","keywords":["進捗","確認"],"confidence":0.52}'), \
         mock.patch("app._fetch_current_gcal_meeting", return_value="週次定例"), \
         mock.patch("app._fetch_tv_guide", return_value=""):
        result = await app._infer_media_content()

    assert result["content_type"] == "meeting"
    assert result["topic"] == "週次定例"
    assert result["confidence"] >= 0.65


@pytest.mark.asyncio
async def test_meeting_debug_reports_hint_reasons():
    app._media_ctx.last_meeting_hint_score = 5
    app._media_ctx.last_meeting_hint_reasons = ["gcal:週次定例", "text:進捗", "text:確認"]
    app._media_ctx.last_meeting_hint_text = "進捗を共有します。"
    app._media_ctx.inferred_type = "youtube_talk"
    app._media_ctx.confidence = 0.52
    app._ambient_listener = SimpleNamespace(state="listening", is_llm_in_cooldown=lambda: False)
    payload = await app.get_meeting_debug()

    assert payload["meeting_hint_score"] == 5
    assert payload["meeting_hint_reasons"][0] == "gcal:週次定例"
    assert payload["inferred_type"] == "youtube_talk"
