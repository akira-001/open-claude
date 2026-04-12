import json
import sys
import wave
from pathlib import Path

from tests.fixtures.audio.import_incoming import import_incoming, load_sidecar


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "audio"


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 160)


class TestAudioFixtureBulkImport:
    def test_load_sidecar_requires_expected_fields(self, tmp_path):
        sidecar = tmp_path / "sample.json"
        sidecar.write_text(json.dumps({"category": "question"}), encoding="utf-8")

        try:
            load_sidecar(sidecar)
        except SystemExit as exc:
            assert "missing required fields" in str(exc)
        else:
            raise AssertionError("expected SystemExit")

    def test_import_incoming_dry_run_reads_sidecars(self, tmp_path, monkeypatch):
        incoming_dir = tmp_path / "incoming"
        samples_dir = tmp_path / "samples"
        samples_dir.mkdir()
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("[]\n", encoding="utf-8")
        incoming_dir.mkdir()
        wav_path = incoming_dir / "question__schedule_planning__01.wav"
        _write_wav(wav_path)

        sidecar_path = incoming_dir / "question__schedule_planning__01.json"
        sidecar_path.write_text(
            json.dumps(
                {
                    "category": "question",
                    "scene": "schedule_planning",
                    "variant": "01",
                    "id": "question_schedule_planning_01",
                    "transcript": "今日の予定どうしようかな？",
                    "expected_source": "user_likely",
                    "expected_intervention": "reply",
                    "notes": "dry run import",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        monkeypatch.syspath_prepend(str(FIXTURE_ROOT))
        import register_fixture as register_fixture_module
        module = __import__("import_incoming")
        monkeypatch.setattr(module, "INCOMING_DIR", incoming_dir)
        monkeypatch.setattr(sys.modules["register_fixture"], "INCOMING_DIR", incoming_dir)
        monkeypatch.setattr(register_fixture_module, "INCOMING_DIR", incoming_dir)
        monkeypatch.setattr(register_fixture_module, "SAMPLES_DIR", samples_dir)
        monkeypatch.setattr(register_fixture_module, "MANIFEST_PATH", manifest_path)

        imported = module.import_incoming(dry_run=True)
        assert imported == 1
        assert wav_path.exists()
        assert sidecar_path.exists()

    def test_import_incoming_removes_processed_files(self, tmp_path, monkeypatch):
        incoming_dir = tmp_path / "incoming"
        samples_dir = tmp_path / "samples"
        samples_dir.mkdir()
        incoming_dir.mkdir()

        wav_path = incoming_dir / "question__schedule_planning__01.wav"
        _write_wav(wav_path)

        sidecar_path = incoming_dir / "question__schedule_planning__01.json"
        sidecar_path.write_text(
            json.dumps(
                {
                    "category": "question",
                    "scene": "schedule_planning",
                    "variant": "01",
                    "id": "question_schedule_planning_01",
                    "transcript": "今日の予定どうしようかな？",
                    "expected_source": "user_likely",
                    "expected_intervention": "reply",
                    "notes": "import and cleanup",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("[]\n", encoding="utf-8")

        monkeypatch.syspath_prepend(str(FIXTURE_ROOT))
        import register_fixture as register_fixture_module
        module = __import__("import_incoming")

        monkeypatch.setattr(module, "INCOMING_DIR", incoming_dir)
        monkeypatch.setattr(register_fixture_module, "INCOMING_DIR", incoming_dir)
        monkeypatch.setattr(register_fixture_module, "SAMPLES_DIR", samples_dir)
        monkeypatch.setattr(register_fixture_module, "MANIFEST_PATH", manifest_path)

        imported = module.import_incoming(dry_run=False)

        assert imported == 1
        assert not wav_path.exists()
        assert not sidecar_path.exists()
        assert (samples_dir / "question__schedule_planning__01.wav").exists()
