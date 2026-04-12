import json
import wave
from pathlib import Path

import pytest

from ambient_listener import AmbientListener


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "audio"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"


@pytest.fixture
def fixture_cases():
    return json.loads(MANIFEST_PATH.read_text())


@pytest.fixture
def listener(tmp_path):
    rules_file = tmp_path / "ambient_rules.json"
    rules_file.write_text(json.dumps({"rules": [], "keywords": []}))
    examples_file = tmp_path / "ambient_examples.json"
    examples_file.write_text(json.dumps({"examples": []}))
    return AmbientListener(rules_path=rules_file, examples_path=examples_file, reactivity=3)


class TestAudioFixtureCatalog:
    def test_manifest_entries_have_existing_audio_files(self, fixture_cases):
        for case in fixture_cases:
            path = FIXTURE_ROOT / case["file"]
            assert path.exists(), case["id"]

    def test_audio_files_are_valid_wav(self, fixture_cases):
        for case in fixture_cases:
            path = FIXTURE_ROOT / case["file"]
            with wave.open(str(path), "rb") as wav_file:
                assert wav_file.getnchannels() == 1, case["id"]
                assert wav_file.getframerate() > 0, case["id"]
                assert wav_file.getnframes() > 0, case["id"]


class TestAudioFixtureExpectations:
    @pytest.mark.parametrize("case_id", ["keyboard_clicks", "desk_monologue", "direct_question", "tv_outro"])
    def test_fixture_transcript_maps_to_expected_policy(self, fixture_cases, listener, case_id):
        case = next(c for c in fixture_cases if c["id"] == case_id)
        source = listener.classify_source(case["transcript"])
        intervention = listener.decide_intervention(case["transcript"], source)

        assert source == case["expected_source"]
        assert intervention == case["expected_intervention"]
