import app


def test_public_yomigana_entries_are_applied(monkeypatch):
    monkeypatch.setattr(app, "_settings", {}, raising=False)

    text = app._clean_text_for_tts("Claude Code と Slack Bot と VOICEVOX と 大谷 と Anthropic を使う")

    assert "クロード コード" in text
    assert "スラック ボット" in text
    assert "ボイスボックス" in text
    assert "おおたに" in text
    assert "アンソロピック" in text


def test_personal_yomigana_entries_override_public_entries(monkeypatch):
    monkeypatch.setattr(
        app,
        "_settings",
        {
            "yomiganaPersonalEntries": [
                {"from": "Slack", "to": "スラックさん"},
                {"from": "Memento", "to": "メメント"},
            ]
        },
        raising=False,
    )

    text = app._clean_text_for_tts("Slack で Memento の話をする")

    assert "スラックさん" in text
    assert "メメント" in text
