from pathlib import Path

from tests.fixtures.audio.register_fixture import build_names, slugify


class TestAudioFixtureTooling:
    def test_slugify_normalizes_text(self):
        assert slugify("Schedule Planning") == "schedule_planning"

    def test_build_names_uses_expected_format(self):
        fixture_id, filename = build_names("question", "schedule_planning", "01")
        assert fixture_id == "question_schedule_planning"
        assert filename == "question__schedule_planning__01.wav"
