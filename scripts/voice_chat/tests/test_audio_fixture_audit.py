from tests.fixtures.audio.audit_fixtures import audit_fixture_catalog


class TestAudioFixtureAudit:
    def test_audit_passes_for_current_catalog(self):
        report = audit_fixture_catalog()

        assert report.duplicate_ids == []
        assert report.duplicate_files == []
        assert report.missing_files == []
        assert report.unregistered_samples == []
        assert report.pending_incoming == []
        assert report.ok is True
