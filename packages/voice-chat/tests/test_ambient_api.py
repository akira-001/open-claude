import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def mock_ambient():
    with patch("app._ambient_listener") as mock:
        mock.rules = {
            "rules": [{"id": "r001", "text": "テスト", "enabled": True, "source": "test", "created_at": "2026-01-01"}],
            "keywords": [{"id": "k001", "category": "weather", "pattern": "天気", "enabled": True}],
        }
        mock.examples = {
            "examples": [{"id": "e001", "context": "テスト状況", "response": "テスト反応", "rating": "positive", "created_at": "2026-01-01"}],
        }
        mock.reactivity = 3
        mock.get_stats.return_value = {"judgments_today": 10, "speaks_today": 3, "speak_rate": 0.3, "feedback_positive": 2, "feedback_negative": 1, "rules_count": 1, "examples_count": 1}
        mock.add_rule.return_value = {"id": "r002", "text": "新ルール", "enabled": True, "source": "manual", "created_at": "2026-04-09"}
        mock.add_example.return_value = {"id": "e002", "context": "新状況", "response": "新反応", "rating": "positive", "created_at": "2026-04-09"}
        mock.get_state_snapshot.return_value = {"state": "listening", "reactivity": 3, "effective_reactivity": 3, "buffer_size": 0}
        yield mock


class TestAmbientRulesAPI:
    def test_get_rules(self, client, mock_ambient):
        res = client.get("/api/ambient/rules")
        assert res.status_code == 200
        data = res.json()
        assert "rules" in data
        assert "keywords" in data

    def test_add_rule(self, client, mock_ambient):
        res = client.post("/api/ambient/rules", json={"text": "新ルール", "source": "manual"})
        assert res.status_code == 200
        mock_ambient.add_rule.assert_called_once_with("新ルール", source="manual")

    def test_delete_rule(self, client, mock_ambient):
        res = client.delete("/api/ambient/rules/r001")
        assert res.status_code == 200
        mock_ambient.remove_rule.assert_called_once_with("r001")

    def test_toggle_rule(self, client, mock_ambient):
        res = client.patch("/api/ambient/rules/r001", json={"enabled": False})
        assert res.status_code == 200
        mock_ambient.toggle_rule.assert_called_once_with("r001", enabled=False)


class TestAmbientExamplesAPI:
    def test_get_examples(self, client, mock_ambient):
        res = client.get("/api/ambient/examples")
        assert res.status_code == 200
        assert "examples" in res.json()

    def test_add_example(self, client, mock_ambient):
        res = client.post("/api/ambient/examples", json={"context": "新状況", "response": "新反応", "rating": "positive"})
        assert res.status_code == 200
        mock_ambient.add_example.assert_called_once()

    def test_delete_example(self, client, mock_ambient):
        res = client.delete("/api/ambient/examples/e001")
        assert res.status_code == 200
        mock_ambient.remove_example.assert_called_once_with("e001")


class TestAmbientReactivityAPI:
    def test_set_reactivity(self, client, mock_ambient):
        res = client.post("/api/ambient/reactivity", json={"level": 4})
        assert res.status_code == 200
        mock_ambient.set_reactivity.assert_called_once_with(4)

    def test_get_stats(self, client, mock_ambient):
        res = client.get("/api/ambient/stats")
        assert res.status_code == 200
        data = res.json()
        assert data["judgments_today"] == 10
